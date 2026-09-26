#!/usr/bin/env python3
"""
graph_export.py — exports the trunk as a graph for the knowledge PLANET.

Scanne toutes les fiches .md du tronc (projects/, lessons/, meta/, life/, agents/),
reads their front matter (`name`, `description`) and their `[[...]]` links, and writes
`planet/graph.json`: the raw material of the 3D visualizer (one note = one dot on the globe).

Designed to be called:
  - by hand: `python3 hooks/graph_export.py`
  - automatically by on_fiche_write.py on every note written (real-time growth).

Deterministic and free of external dependencies. Always exits 0 (never blocks a hook).
"""
import os, re, json, sys
from collections import Counter

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
OUT = os.path.join(BRAIN, "planet", "graph.json")
EMBED2 = os.path.join(BRAIN, "state", "embed2.json")   # SEMANTIC map, computed by brain_embed2.py
COACT = os.path.join(BRAIN, "state", "coactivation.json")  # working memory, computed by coactivation.py
CHALLENGES = os.path.join(BRAIN, "state", "challenges.json")  # the challenger's verdict (the map has an opinion)
BELIEFS = os.path.join(BRAIN, "meta", "beliefs.json")        # the author's dated convictions (the taste layer)
MEDIA = os.path.join(BRAIN, "meta", "media.json")            # REPLAYABLE nodes (a glb/clip/curve capture)


def load_media():
    """Replayable captures per note → { rel_path: {type, src, caption} }. Curated (meta/media.json). Stdlib."""
    out = {}
    try:
        for f, v in json.load(open(MEDIA, encoding="utf-8")).items():
            if f.startswith("_") or not isinstance(v, dict) or not v.get("src"):
                continue
            out[f] = {"type": v.get("type", "glb"), "src": v["src"], "caption": v.get("caption", "")}
    except Exception:
        return {}
    return out


def load_beliefs():
    """The author's dated convictions → { rel_path: "since <date> — <note>" }. Curated (meta/beliefs.json). Stdlib."""
    out = {}
    try:
        for f, v in json.load(open(BELIEFS, encoding="utf-8")).items():
            if f.startswith("_") or not isinstance(v, dict):
                continue
            since = v.get("since", "")
            out[f] = (f"depuis {since} — " if since else "") + v.get("note", "")
    except Exception:
        return {}
    return out


def load_challenges():
    """ACTIVE challenger verdicts per note → { rel_path: "verdict court" }. Les challenges
    marked STALE/resolved are ignored (the map only challenges what still stands). Stdlib."""
    out = {}
    try:
        for c in json.load(open(CHALLENGES, encoding="utf-8")):
            vp = (c.get("verdict_pair") or "")
            prob = (c.get("problem") or "")
            # BILINGUAL: the challenger writes these words itself, and its prompt
            # exists in both languages. Matching only one would keep dead
            # challenges alive on the map, marking notes as contested forever.
            dead = ("stale", "resolved", "périmé", "resolu", "résolu")
            blob = (prob + " " + vp).lower()
            if any(w in blob for w in dead):
                continue                                  # challenge extinguished → not a live verdict
            f = c.get("note")
            if not f:
                continue
            reason = vp or prob
            out.setdefault(f, reason[:200])               # 1 verdict (le 1er actif) par fiche
    except Exception:
        return {}
    return out


def load_embed2():
    """Semantic 3D positions { rel_path: [x,y,z] } — a cache produced offline (numpy).
    Read with NO dependency: graph_export stays pure stdlib (it runs on every note written).

    RETURNS (positions, state, detail) — AND THAT IS THE WHOLE POINT OF THIS SIGNATURE.
    It used to return `{}` on any exception, which conflated three situations a reader must
    be able to tell apart: the module was never installed (legitimate — embeddings are
    optional by design, docs/design-doc.md), the cache is there and unreadable (a real
    failure), and the cache is there and fine. The viewer then announced "MEANING IN VOLUME
    — proximity = meaning, every note" over a map where NOT ONE note had a vector, because
    an empty dict says nothing about why it is empty. Measured 2026-09-19 on the shipped
    package: 0 of 10 notes placed by meaning, and the map OPENS on that view.
    """
    if not os.path.exists(EMBED2):
        return {}, "absent", ("state/embed2.json has never been produced — the semantic "
                              "module is optional and was not run")
    try:
        pos = json.load(open(EMBED2, encoding="utf-8")).get("pos", {})
    except Exception as e:                      # unreadable, truncated, not JSON
        return {}, "broken", f"state/embed2.json is present but unreadable: {e}"
    if not isinstance(pos, dict):
        return {}, "broken", "state/embed2.json has no usable `pos` mapping"
    return pos, "ready", ""


def load_coact():
    """Heat (usage recency) per id + usage links + LIVE ACTIVITY. Stdlib.

    `live` = { path: ts } for the notes read within the sliding window (a few minutes), plus the
    window itself: the visualizer needs it to fade a ring out on its own, continuously, even when
    the graph is not regenerated in between."""
    try:
        c = json.load(open(COACT, encoding="utf-8"))
        lv = c.get("live") or {}
        live = {p: ts for p, ts in lv.get("items", [])}
        return c.get("heat_id", {}), c.get("edges", []), live, int(lv.get("window_min", 10))
    except Exception:
        return {}, [], {}, 10
# dossiers de premier niveau = « domaines » (couleurs sur le globe)
DOMAINS = ["projects", "lessons", "meta", "life", "agents"]

FM_NAME = re.compile(r'^\s*name:\s*["\']?([^"\'\n]+)["\']?\s*$', re.M)
FM_TITLE = re.compile(r'^\s*title:\s*["\']?(.+?)["\']?\s*$', re.M)  # a descriptive human label (not the stable slug)
FM_DESC = re.compile(r'^\s*description:\s*["\']?(.+?)["\']?\s*$', re.M)
FM_BORN = re.compile(r'^\s*born_from:\s*(.+?)\s*$', re.M)   # born_from: <projet>[, autre]
FM_SCALE = re.compile(r'^\s*scale:\s*([0-9](?:\.[0-9])?)\s*$', re.M)  # scale: 1..4 (city centre → outskirts)
LINK = re.compile(r'\[\[([^\]]+)\]\]')          # [[nom-de-fiche]]
# BILINGUAL on purpose: it scans the USER's notes, in whatever language they write.
RESUME_RE = re.compile(r'RESUME HERE|resume point|pick up here'
                       r'|REPRENDRE ICI|point de reprise|à reprendre', re.I)   # ↻ badge
DASH = re.compile(r'\s+[—–]\s+')                # em/en dash surrounded by spaces

# membership weights (continent / city / frontier model)
W_PRIMARY = 1.00     # dossier d'origine (un projet) = appartenance forte
W_BORN    = 0.70     # born of a project (born_from) but filed elsewhere (e.g. a reusable lesson)
W_LINK    = 0.18     # lien [[...]] vers/depuis une fiche de projet = appartenance douce
HOME_MIN  = 0.50     # appartenance mini pour avoir une VILLE maison (dossier/born_from, pas un simple lien)
FRONTIER_MIN = 0.30  # threshold for a second membership to count as a "frontier"

# scale heuristic when `scale:` is absent: city centre (vision/project) → outskirts (detail)
def guess_scale(nid):
    s = nid.lower()
    if s.startswith("project-") or "vision" in s:
        return 1.0                                   # cœur : le projet, sa vision
    if any(k in s for k in ("audit", "naming", "precision", "couts", "labo", "lab")):
        return 3.0                                   # outskirts: detail / appendix
    return 2.0                                        # ville standard


def clean_desc(raw):
    """A short clean summary for the panel: the hook sentence before the first ' — ',
    otherwise the whole description; never cut mid-word."""
    full = (raw or "").strip()
    summary = DASH.split(full, 1)[0].strip()
    if len(summary) < 35:                       # accroche trop maigre → on garde tout
        summary = full
    if len(summary) > 180:                       # coupe nette au mot + …
        summary = summary[:180].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return summary


def frontmatter(text):
    """Returns the front-matter block (between the leading ---) or ''."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end]
    return ""


FM_TYPE = re.compile(r"^\s*type:\s*(\S+)\s*$", re.M)
EN_CLAIR = re.compile(r'^##[ \t]+En clair[ \t]*$(.*?)(?=^## |\Z)', re.M | re.S)  # i18n-ok


def extract_en_clair(text):
    """The note's "## En clair" block — the plain-language register, jargon-free.

    ONE file, not two. Two hand-maintained files always drift; after a month there are two
    truths, therefore none. The block lives INSIDE the note and the viewer decides what to
    show first: the panel shows the whole block, the hover shows its first paragraph.

    Returns None when a note has no such block — the panel then falls back on `desc`, which
    is what the viewer already does.

    The heading stays in French because it is the convention of the NOTES themselves, not a
    string of this codebase; the notes are the user's, in the user's language.
    """
    m = EN_CLAIR.search(text)
    if not m:
        return None
    txt = re.sub(r"\[\[([^\]]+)\]\]", r"\1", m.group(1))
    txt = txt.replace("**", "").replace("`", "")
    # The file's line breaks serve reading the .md, not the display: re-join paragraphs and
    # keep only the real breaks (a blank line).
    paras = [" ".join(p.split()) for p in re.split(r"\n[ \t]*\n", txt) if p.strip()]
    return "\n\n".join(paras) or None


def clean_body(text):
    """The note body stripped of markdown → a long readable explanation for the expanded panel."""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:]
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)        # images
    body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)          # [[lien]] → lien
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)     # [texte](url) → texte
    out = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            out.append("")
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)                     # titres
        s = re.sub(r"^[-*]\s+", "• ", s)                      # puces
        s = re.sub(r"^\d+\.\s+", "• ", s)                     # numbered lists
        s = re.sub(r"^>\s?", "", s)                           # citations
        s = s.replace("**", "").replace("`", "").replace("*", "")
        out.append(s)
    txt = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    if len(txt) > 1600:                                       # coupe nette au mot + …
        txt = txt[:1600].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return txt


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # CODE_ROOT, legitimate
import topics_fiche  # noqa: E402
# A trunk without `meta/topics.json` (the benches' mini-trunks) exports its topics as None;
# a real trunk has its source, and `tests/topics_canoniques.py` locks that it exists.
TOPICS = ({t["id"]: t.get("name", t["id"])
           for t in json.load(open(topics_fiche.SOURCE, encoding="utf-8"))["topics"]}
          if os.path.exists(topics_fiche.SOURCE) else {})


def scan():
    nodes = {}      # id -> {id, name, domain, group, desc, file}
    raw_links = []   # (src_id, target_name)
    link_types = {}  # (src_id, target_name) -> one of RELATION_TYPES
    unknown_relations = 0   # qualifications lost to a type outside RELATION_TYPES
    embed2, sem_state, sem_detail = load_embed2()   # semantic positions + WHY, keyed by note path
    heat, coact_edges, live, live_window_min = load_coact()   # heat + usage links + live activity
    challenges = load_challenges()             # the challenger's verdict per note
    beliefs = load_beliefs()                   # the author's dated convictions (the taste layer)
    media = load_media()                       # replayable captures per note

    for domain in DOMAINS:
        root = os.path.join(BRAIN, domain)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                # on ne garde QUE des fiches de savoir : pas les README ni les docs
                if fn.lower() == "readme.md":
                    continue
                low = dirpath.lower()
                if os.sep + "documentation" in low or os.sep + "docs" in low:
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    text = open(path, encoding="utf-8").read()
                except Exception:
                    continue
                fm = frontmatter(text)
                m = FM_NAME.search(fm)
                if not m:
                    continue                     # pas de `name:` → ce n'est pas une fiche, on saute
                nid = m.group(1).strip()
                dm = FM_DESC.search(fm)
                desc = clean_desc(dm.group(1) if dm else "")
                tm = FM_TITLE.search(fm)
                title = tm.group(1).strip() if tm else nid.replace("-", " ")
                # sous-groupe = sous-dossier de projet (ex. mon-projet) sinon = domaine
                rel = os.path.relpath(dirpath, root)
                group = rel.split(os.sep)[0] if rel != "." else domain
                # declared membership: born_from (one or more projects), scale (centre ↔ outskirts)
                bm = FM_BORN.search(fm)
                born = [b.strip().strip("[]\"'") for b in bm.group(1).split(",")] if bm else []
                born = [b for b in born if b]
                sm = FM_SCALE.search(fm)
                scale = float(sm.group(1)) if sm else guess_scale(nid)
                rel_file = os.path.relpath(path, BRAIN)
                # ── THE TOPIC (N1, 09/23): `topic:` and its values from `meta/topics.json`, read
                # by `topics_fiche` — the trunk's only definition, not a seventh dialect. A value
                # outside the source (old vocabulary) is exported as None: the map must not
                # invent an extra topic that the `topics_canoniques` bench refuses.
                topic, _secondary = topics_fiche.lire(text)
                topic = topic if isinstance(topic, str) and topic in TOPICS else None
                nodes[nid] = {"id": nid, "name": nid, "title": title, "domain": domain,
                              "group": group, "desc": desc,
                              "born_from": born, "scale": scale,
                              # The plain-language register, shown FIRST by the viewer: the
                              # panel renders the whole block, the hover its first paragraph.
                              # It was read at five sites in planet/index.html and produced
                              # nowhere, so the register was invisible in the map.
                              # read to decide `regle` below, then dropped: not exported.
                              "_type": (FM_TYPE.search(fm).group(1)
                                        if fm and FM_TYPE.search(fm) else None),
                              "en_clair": extract_en_clair(text),
                              "long": clean_body(text),
                              "embed2": embed2.get(rel_file),   # semantic [x,y] or None
                              "heat": heat.get(nid, 0.0),        # usage heat 0..1
                              "active": rel_file in live,        # READ just now (sliding window)
                              "active_ts": live.get(rel_file),   # timestamp of that read → fade-out in the visualizer
                              "challenge": challenges.get(rel_file),   # the challenger's verdict, or None
                              "conviction": beliefs.get(rel_file),     # a dated conviction, or None
                              "media": media.get(rel_file),            # a replayable capture, or None
                              "resume": bool(RESUME_RE.search(text)),  # carries a resume point (↻ badge)
                              "topic": topic,
                              "file": rel_file}
                # outgoing links (deduplicated below)
                for tgt in set(LINK.findall(text)):
                    raw_links.append((nid, tgt.strip()))
                # TYPED relations from the frontmatter (cf. gardening rules §4 bis).
                # They add no edge: they QUALIFY the one that already exists, since the
                # convention requires keeping the [[slug]] in the body.
                # An unrecognized type costs the QUALIFICATION, never the edge: the link
                # comes from the [[slug]] in the body, so it survives untyped. The counter
                # says how many qualifications were lost, and says it in graph.json — the
                # only place the automatic path (on_fiche_write → export → Planet) passes
                # through. A warning printed here would be invisible: that path has no tty.
                recognized, unknown = _relations(text)
                unknown_relations += unknown
                for typ, targets in recognized.items():
                    for c in targets:
                        link_types[(nid, c)] = typ

    # keep only links whose target is a known note (not [[yet-to-write]] ones)
    ids = set(nodes)
    seen = set()
    links = []
    for src, tgt in raw_links:
        if tgt in ids and src != tgt and (src, tgt) not in seen and (tgt, src) not in seen:
            seen.add((src, tgt))
            edge = {"source": src, "target": tgt}
            typ = link_types.get((src, tgt)) or link_types.get((tgt, src))
            if typ:
                edge["type"] = typ
            links.append(edge)

    # ---------- RULE NOTES (the orange badge the viewer already draws) ----------
    # A `type: feedback` note wired to at least this many others is a RULE: something the
    # whole trunk leans on. The viewer draws a badge for it and explains, in its own
    # comment, why such a point has no visible children. It read `nd.regle` and nothing
    # ever wrote it, so that badge could never appear — the same silent shape as en_clair,
    # found by widening the contract test to the viewer's second accessor.
    # The type is read here and NOT exported: the viewer never reads `type`, so shipping it
    # would be bytes in every graph for nobody.
    RULE_DEGREE = 20                     # ~5% of a trunk; past that "rule" means nothing
    degrees = Counter()
    for l in links:
        degrees[l["source"]] += 1
        degrees[l["target"]] += 1
    rules = {nid for nid, n in nodes.items()
             if n.pop("_type", None) == "feedback" and degrees[nid] >= RULE_DEGREE}
    for nid, n in nodes.items():
        n.pop("_type", None)
        n["regle"] = nid in rules
    for l in links:
        if l["source"] in rules or l["target"] in rules:
            l["regle"] = True

    # ---------- MEMBERSHIP (continent / city / frontier model) ----------
    # « villes » = les sous-dossiers du domaine projects (chaque projet est une ville).
    projects = sorted({n["group"] for n in nodes.values() if n["domain"] == "projects"})
    proj_set = set(projects)
    # undirected neighbourhood towards project notes (for the soft membership of lessons)
    proj_of = {nid: n["group"] for nid, n in nodes.items() if n["domain"] == "projects"}
    adj_proj = {nid: [] for nid in nodes}       # nid -> [connected project groups]
    for l in links:
        s, t = l["source"], l["target"]
        if s in proj_of and t not in proj_of:
            adj_proj[t].append(proj_of[s])
        elif t in proj_of and s not in proj_of:
            adj_proj[s].append(proj_of[t])

    for nid, n in nodes.items():
        m = {}
        if n["domain"] == "projects":                       # note already inside a city
            m[n["group"]] = m.get(n["group"], 0.0) + W_PRIMARY
        for b in n["born_from"]:                              # born of a project, filed elsewhere
            if b in proj_set:
                m[b] = m.get(b, 0.0) + W_BORN
        for g in adj_proj[nid]:                               # pulled by links towards a project
            m[g] = m.get(g, 0.0) + W_LINK
        if not m:
            n["membership"] = {}                             # out of town (pure meta/life)
            n["primary_project"] = None
            n["frontier"] = False
            continue
        # ABSOLUTE weights anchored on W_PRIMARY=1.0 (no normalization by the max:
        # a plain link stays faint ~0.20, it must not inflate into full membership)
        m = {k: round(min(v, 1.0), 3) for k, v in m.items()}
        n["membership"] = dict(sorted(m.items(), key=lambda kv: -kv[1]))
        mx = max(m.values())
        # une fiche n'a une VILLE que si son appartenance est FORTE (dossier d'origine ou born_from).
        # A plain link (~0.18) is not enough → an agent or meta note mentioning a project is not filed there.
        n["primary_project"] = max(m, key=m.get) if mx >= HOME_MIN else None
        # frontier = has a real home city AND a second city above the threshold
        n["frontier"] = (n["primary_project"] is not None
                         and sum(1 for v in m.values() if v >= FRONTIER_MIN) >= 2)

    # THE COVERAGE IS COUNTED ON THE NOTES, not on the size of the cache: an entry that
    # matches no current note places nobody, and a cache of 400 stale keys would otherwise
    # read as full health.
    sem_covered = sum(1 for n in nodes.values() if n.get("embed2"))
    return {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "counts": {"nodes": len(nodes), "links": len(links),
                   "projects": len(projects),
                   "frontier": sum(1 for n in nodes.values() if n.get("frontier")),
                   "challenged": sum(1 for n in nodes.values() if n.get("challenge")),
                   "convictions": sum(1 for n in nodes.values() if n.get("conviction")),
                   "media": sum(1 for n in nodes.values() if n.get("media")),
                   "active": sum(1 for n in nodes.values() if n.get("active")),
                   "resume": sum(1 for n in nodes.values() if n.get("resume")),
                   "en_clair": sum(1 for n in nodes.values() if n.get("en_clair")),
                   # Relation TYPES this exporter did not recognize. The links are all
                   # still there and still drawn — only their qualification is gone.
                   # `brain doctor` says which notes and which types; this only says
                   # how many, so the loss is visible without a second validator.
                   "unknown_relations": unknown_relations},
        "domains": DOMAINS,
        # the topics and their names, in the source's order: the map copies no list
        "topics": TOPICS,
        # LIVE ACTIVITY window (minutes): the visualizer fades out a ring whose `active_ts`
        # has left the window on its own, without waiting for a graph regeneration.
        "live_window_min": live_window_min,
        "projects": projects,
        "nodes": sorted(nodes.values(), key=lambda n: (n["domain"], n["group"], n["id"])),
        "links": links,
        # USAGE links (co-activation): notes activated together in a session, unlike declared links
        "coact": [e for e in coact_edges if e[0] in ids and e[1] in ids],
        # THE SEMANTIC CAPACITY, DECLARED — not assumed. The viewer used to read the
        # absence of vectors as "nothing to say" and kept its nominal wording; from here
        # it is told, in so many words, how many notes are actually placed by meaning and
        # why the others are not. `covered == 0` WITH a readable cache is not "in
        # progress": the cache exists and matches none of the current notes (stale keys,
        # a moved trunk), which is a failure a reader must see, not a silence.
        "semantic": {
            "state": (sem_state if sem_state != "ready" else
                      "ready" if nodes and sem_covered == len(nodes) else
                      "partial" if sem_covered else "broken"),
            "covered": sem_covered,
            "total": len(nodes),
            "detail": (sem_detail if sem_detail else
                       "" if sem_covered == len(nodes) else
                       f"state/embed2.json matches none of the {len(nodes)} notes — stale cache"
                       if not sem_covered else
                       f"{len(nodes) - sem_covered} note(s) written since the last indexing pass"),
        },
    }


# ── THE RELATION VOCABULARY — closed, decided by the author on 2026-09-17 (ADR-0019) ──
# Four types that each say one precise thing, plus ONE catch-all that must say why.
# The catch-all exists because refusing it does not remove the need, it pushes it towards
# invented words the export drops silently: measured on 09/17, a made-up "neighbour of"
# type — in no vocabulary — carried 239 links, 42 % of the total, and vanished without a word.
#   based_on     this note PRESUPPOSES the other
#   refines      this note sharpens the other without contradicting it
#   contradicts  the two cannot both be true
#   replaces     the other is dead, this one takes over (the ONLY active type: leaves recall)
#   related_to   everything else — only complete with its reason, in one sentence
RELATION_TYPES = ("based_on", "refines", "contradicts", "replaces", "related_to")

# TWO FORMS, because both were already written in the trunk on 09/17:
#     based_on: [a, b]         the short form;
#     based_on:                the block form (a YAML list) — it used to be dropped
#       - a                    SILENTLY, the parser only accepting brackets;
#     related_to:              the block form also carries the reason, after a colon.
#       - a: because …
# `- a: reason` is valid YAML (a list of mappings), so a real YAML reader does not choke
# on it the day one goes through.
_REL_BLOCK = re.compile(r"^relations:\s*$(.*?)(?=^\S|\Z)", re.M | re.S)
_REL_LINE = re.compile(r"^\s+(\w+)\s*:\s*\[([^\]]*)\]", re.M)
_REL_HEAD = re.compile(r"^\s+(\w+)\s*:\s*$")
_REL_ITEM = re.compile(r"""^\s+-\s+["']?([^:"'\n]+?)["']?\s*(?::\s*(\S.*?))?\s*$""")


def raw_relations(block):
    """[(type, target, reason|None)] for EVERYTHING written under `relations:`, without
    filtering on RELATION_TYPES. It is what the doctor reads to NAME the types the export
    will drop: it can only say so if it first sees what is written, the unknown included."""
    out, current = [], None
    for line in block.split("\n"):
        m = _REL_LINE.match(line)
        if m:
            current = None
            for c in m.group(2).split(","):
                c = c.strip().strip('"\'')
                if c:
                    out.append((m.group(1), c, None))
            continue
        m = _REL_HEAD.match(line)
        if m:
            current = m.group(1)
            continue
        m = _REL_ITEM.match(line) if current else None
        if m:
            out.append((current, m.group(1).strip(), (m.group(2) or "").strip() or None))
        elif line.strip():
            current = None
    return out


def _relations(text):
    """Reads the frontmatter's `relations:` block → (recognized, unknown_count).

    Silent when absent or malformed — a wobbly frontmatter must never bring the graph
    export down. But silent about DROPPING was a different thing: a type outside
    RELATION_TYPES used to vanish without a word, and 58 `base_sur` in the private trunk
    would come out unqualified under this exporter with no error and no log.

    What is counted is the unrecognized TYPE, once per note, not its targets — whether it
    is written as a bracket line or as a block list — for two reasons: it is
    what the viewer's wording says ("relation types were not recognized"), and it makes
    this count comparable to `brain_doctor`'s `unknown_relation`, which lists one entry per
    (note, type) — the two read the same block with the same parser and must agree.

    The count is NOT a validation verdict. Nothing here decides that `base_sur` or
    `illustre` should become valid: that is a vocabulary decision, and it lives elsewhere.
    """
    fm = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not fm:
        return {}, 0
    block = _REL_BLOCK.search(fm.group(1) + "\n")
    if not block:
        return {}, 0
    out, unknown_types = {}, set()
    for typ, target, _reason in raw_relations(block.group(1)):
        if typ in RELATION_TYPES:
            out.setdefault(typ, []).append(target)
        else:
            unknown_types.add(typ)
    return out, len(unknown_types)


def main():
    try:
        data = scan()
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        if sys.stdout.isatty():
            c = data["counts"]
            print(f"🪐 graph.json written: {c['nodes']} dots, {c['links']} links → {os.path.relpath(OUT, BRAIN)}")
    except Exception as e:
        if sys.stdout.isatty():
            print(f"graph_export: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
    sys.exit(0)
