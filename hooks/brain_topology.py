#!/usr/bin/env python3
"""brain_topology — the GLOBAL view of the trunk's cohesion, at graph level.

Where check_coherence looks at notes TWO BY TWO (local overlap) and
brain_doctor hunts individual defects (dead links, orphans), THIS module steps
back: it reads the WHOLE `[[...]]` graph plus content similarity, and computes
the **overall structure** to reveal what is only visible from a distance:

  - MISSING links    : two notes very close in content that do not cite each other
                       → the gold of cohesion (especially across different projects).
  - ISOLATED notes   : zero or one link in the whole tree (on the map but
                       disconnected from the knowledge fabric).
  - components       : connected components of the link graph — a detached island
                       = un pan de savoir qui ne dialogue avec rien.
  - ODD placement    : a note whose neighbours (links) mostly belong to
                       ANOTHER domain than its own → possibly misfiled.
  - per-domain health: internal density, cross-domain bridges (the cross-cutting value).

Separation of powers (as everywhere else here):
  - HERE (mechanical, cheap, zero LLM): MEASURE the topology → state/topology.json.
  - ARCHITECT (LLM): JUDGE which links to weave, which islands to reconnect, what to refile.

Usage :
  brain_topology.py            → rapport lisible (terminal)
  brain_topology.py --json     → state/topology.json + sortie machine
Sort toujours 0 (ne bloque jamais un hook).
"""
import os, re, sys, json, math, glob, time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import brain_recall as recall          # reuses fold/tokenize/STOP + the SKIP_PARTS rule
except Exception:
    recall = None

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
OUT = os.path.join(BRAIN, "state", "topology.json")
DOMAINS = ("projects", "lessons", "meta", "life", "agents")
STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}

LINK = re.compile(r"\[\[([^\]]+)\]\]")
# syntax placeholders present in the agent docs — never real links
# Bilingual on purpose (see brain_doctor.EXAMPLE_WHITELIST).
NOT_A_LINK = {"slug", "name", "link", "links", "another-note", "examples", "...",
              "lien", "liens", "exemples", "nom-du-fichier"}

MISS_MIN = 0.30     # TF-IDF cosine: above this = close enough to CITE each other (< 0.45 = duplicate threshold)
MISS_TOP = 25       # max number of link suggestions returned


def load():
    """Returns {name -> {domain, path, links:set, tokens:list}} for the knowledge notes."""
    fiches = {}
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if rel in STRUCTURAL_MAPS:
            continue
        zone = rel.split(os.sep)[0]
        if zone not in DOMAINS:
            continue
        if os.path.basename(p).lower() == "readme.md":
            continue
        try:
            raw = open(p, encoding="utf-8").read()
        except Exception:
            continue
        fm = re.match(r"^---\n(.*?)\n---", raw, re.S)
        if not fm:
            continue
        m = re.search(r"^\s*name:\s*(.+)$", fm.group(1), re.M)
        if not m:
            continue
        name = m.group(1).strip().strip('"\'')
        links = {t.strip() for t in LINK.findall(raw)} - NOT_A_LINK
        toks = recall.tokenize(recall.strip_md(raw)) if recall else []
        fiches[name] = {"domain": zone, "path": rel, "links": links, "tokens": toks}
    return fiches


def tfidf(fiches):
    df = Counter()
    for d in fiches.values():
        for t in set(d["tokens"]):
            df[t] += 1
    N = len(fiches) or 1
    idf = {t: math.log(1 + N / (n + 0.5)) for t, n in df.items()}
    vecs = {}
    for name, d in fiches.items():
        tf = Counter(d["tokens"])
        v = {t: (f / len(d["tokens"])) * idf.get(t, 0) for t, f in tf.items()} if d["tokens"] else {}
        norm = math.sqrt(sum(w * w for w in v.values())) or 1.0
        vecs[name] = {t: w / norm for t, w in v.items()}
    return vecs


def cosine(a, b):
    small, big = (a, b) if len(a) < len(b) else (b, a)
    return sum(w * big.get(t, 0) for t, w in small.items())


def analyze():
    fiches = load()
    names = set(fiches)
    # --- undirected link graph (resolved links only) ---
    adj = defaultdict(set)
    for name, d in fiches.items():
        for tgt in d["links"]:
            if tgt in names and tgt != name:
                adj[name].add(tgt)
                adj[tgt].add(name)

    degree = {n: len(adj.get(n, ())) for n in names}
    isolated = sorted([n for n in names if degree[n] == 0])
    weak = sorted([n for n in names if degree[n] == 1])

    # --- connected components (disconnected subsets) ---
    seen, components = set(), []
    for n in names:
        if n in seen:
            continue
        stack, comp = [n], []
        seen.add(n)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in adj.get(cur, ()):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        components.append(sorted(comp))
    components.sort(key=len, reverse=True)

    # --- missing links: close in content but not connected ---
    vecs = tfidf(fiches)
    ordered = sorted(names)
    missing = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b in adj.get(a, ()):
                continue
            sim = cosine(vecs[a], vecs[b])
            if sim >= MISS_MIN:
                cross = fiches[a]["domain"] != fiches[b]["domain"]
                # score = similarity + a small "cross-domain bridge" bonus (without crushing a strong pair)
                missing.append({"a": a, "b": b, "sim": round(sim, 3), "cross_domain": cross,
                                "score": round(sim + (0.08 if cross else 0), 3)})
    missing.sort(key=lambda x: x["score"], reverse=True)
    missing = missing[:MISS_TOP]

    # --- odd placement: neighbours mostly from another domain ---
    # We IGNORE the patterns that are LEGITIMATE by construction (otherwise it is all false positives):
    #   a lesson or a life goal points at ITS originating project; a project points at the
    #   lessons it produced; meta points at its agents. The rest is a real question.
    EXPECTED = {("lessons", "projects"), ("life", "projects"), ("projects", "lessons"),
                ("life", "meta"), ("meta", "agents"), ("agents", "meta"), ("meta", "projects")}
    misfiled = []
    for n in names:
        nbs = adj.get(n, ())
        if len(nbs) < 2:
            continue
        own = fiches[n]["domain"]
        ext = Counter(fiches[x]["domain"] for x in nbs)
        dom_voisin, cnt = ext.most_common(1)[0]
        if dom_voisin != own and cnt > len(nbs) / 2 and (own, dom_voisin) not in EXPECTED:
            misfiled.append({"note": n, "domain": own, "neighbours_mostly": dom_voisin,
                             "ratio": f"{cnt}/{len(nbs)}"})

    # --- per-domain health: internal density + cross-domain bridges ---
    intra, cross = 0, 0
    bridges = []
    edges = set()
    for a in names:
        for b in adj.get(a, ()):
            e = tuple(sorted((a, b)))
            if e in edges:
                continue
            edges.add(e)
            if fiches[a]["domain"] == fiches[b]["domain"]:
                intra += 1
            else:
                cross += 1
                bridges.append({"a": e[0], "b": e[1],
                                "da": fiches[e[0]]["domain"], "db": fiches[e[1]]["domain"]})
    dom_counts = Counter(d["domain"] for d in fiches.values())

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_notes": len(fiches), "n_links": len(edges),
        "liens_intra_domaine": intra, "cross_domain_bridges": cross,
        "domains": dict(dom_counts),
        "isolated": isolated, "faiblement_liees": weak,
        "n_components": len(components),
        "components": [c for c in components if len(c) < len(fiches)],  # tout sauf le continent principal
        "missing_links": missing,
        "odd_placement": misfiled,
        "ponts_existants": bridges,
    }


def main():
    as_json = "--json" in sys.argv[1:]
    data = analyze()
    if as_json:
        try:
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception:
            pass
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    # rapport lisible
    print(f"🕸️  TRUNK TOPOLOGY — {data['n_notes']} notes, {data['n_links']} links "
          f"({data['liens_intra_domaine']} internes, {data['cross_domain_bridges']} ponts inter-domaines)\n")
    if data["isolated"]:
        print(f"🏝️  ISOLATED ({len(data['isolated'])}) — no link anywhere in the tree:")
        for n in data["isolated"]:
            print(f"     · {n}")
    if len(data["components"]):
        print(f"\n🧩 DETACHED COMPONENTS ({len(data['components'])} outside the main continent):")
        for c in data["components"][:8]:
            print(f"     · {{{', '.join(c)}}}")
    print(f"\n🔗 SUGGESTED MISSING LINKS (close but not citing each other) — top {len(data['missing_links'])}:")
    for m in data["missing_links"]:
        tag = " 🌉 PONT" if m["cross_domain"] else ""
        print(f"     [{m['sim']:.2f}]{tag}  {m['a']}  ⇄  {m['b']}")
    if data["odd_placement"]:
        print(f"\n📍 PLACEMENT WORTH QUESTIONING ({len(data['odd_placement'])}):")
        for x in data["odd_placement"]:
            print(f"     · {x['note']} (in {x['domain']}) — neighbours mostly {x['neighbours_mostly']} ({x['ratio']})")
    print("\n→ state/topology.json written. The ARCHITECT judges and weaves.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        if sys.stdout.isatty():
            print(f"brain_topology: {e}", file=sys.stderr)
    sys.exit(0)
