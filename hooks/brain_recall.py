#!/usr/bin/env python3
"""brain_recall — relevance retrieval inside the trunk.

The FOUNDATION of semantic recall: instead of loading all of MEMORY.md on every
session, we retrieve the top-k RELEVANT notes for a query.

Default backend = lexical BM25 (pure Python, ZERO dependencies, ZERO API, instant).
Architecture enfichable : un backend `Embedding` (sentence-transformers local) pourra
replace or complement BM25 without touching the caller — that is the "true semantic" upgrade.

Usage :
  brain_recall.py "rotation main capteur profondeur"        → top-k fiches
  brain_recall.py -k 8 "billing AI costs"
  brain_recall.py --json "..."                              → sortie machine
"""
import os, re, sys, json, math, glob, hashlib, unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ⚠️ THE CORPUS DEFINITION IS NOT WRITTEN HERE — it lives in brain_corpus.py, and the two
# engines (BM25 here, embeddings in brain_embed.py) IMPORT it. Two copies had already
# drifted by 5 documents under a comment claiming they were identical.
# The names are re-exported as-is: `br.SKIP_DIRS` stays valid for existing callers.
from brain_corpus import (  # noqa: E402
    BRAIN, SKIP_DIRS, SKIP_PREFIX, SKIP_FILES, skip as _skip, indexable as _indexable_from,
)
STOP = set("""
au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me meme
mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi
ton tu un une vos votre vous c d j l m n s t y est sont a as ai ont pas plus tres etre fait
le la les un une que qui pour dans sur avec sans est the and for with not are was you your
""".split())


def fold(s):
    """lowercase + accent-stripped (so 'résumé' matches 'resume')."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Light French stemming. Without it, "ranger" and "rangement" are two tokens that are
# strangers to each other: the query "comment ranger une fiche du brain" never touched
# jardinage-regles.md, whose description says "rangement". BM25 was not missing the note
# for lack of subtlety, it was missing it for lack of lexical overlap.
#
# Two stages, and the ORDER is the heart of the fix:
#   1. the PLURAL first, otherwise "fiche" and "fiches" never meet ("fiches" fell on the
#      -es rule and gave "fich", while "fiche" stayed "fiche") — it is the most frequent
#      word in the trunk, missing it ruins everything;
#   2. then A SINGLE suffix, longest to shortest, and only if the stem keeps at least
#      4 letters.
# Deliberately conservative: a greedy stemmer manufactures silent collisions that damage
# every other query. Ambiguous suffixes are therefore absent — -re turned "mesure" into
# "mesu", and -es/-ee duplicate stage 1.
#
# The stemmer is French because the TRUNK is written in French: it runs against the
# user's notes, not against this package's own prose.
_SUFFIXES = sorted((
    "issement", "ellement", "ications", "ication", "atrice", "ateur", "ation",
    "ement", "ance", "ence", "isme", "iste", "euse", "able", "ible", "aire",
    "ite", "ive", "age", "ure", "eur",
    # common verb forms
    "eraient", "erions", "assent", "erais", "erait", "erons", "eront", "aient",
    "ant", "ent", "ons", "ier", "ez", "er", "ir",
), key=len, reverse=True)
_MIN_STEM = 4            # below this, the stem no longer means anything


# Memoised: a corpus repeats its vocabulary relentlessly — 835 distinct tokens for
# 8,013 occurrences in one file, so 90% of the calls below are redundant. The cost
# of stemming is paid on the COLD index build, which is the first prompt after any
# note changes, and tests/recall_benchmark.py gates that time. The dictionary is
# bounded by the trunk's vocabulary, not by its size in bytes: it stops growing
# long before the corpus does.
_STEM_CACHE = {}


def stem(t):
    cached = _STEM_CACHE.get(t)
    if cached is not None:
        return cached
    _STEM_CACHE[t] = s = _stem(t)
    return s


def _stem(t):
    if len(t) <= 4:
        return t
    # Plural: the "s" only. Stripping a trailing "x" targeted the French plurals in
    # -aux/-eux, but the trunk is bilingual and it MUTILATES English words:
    # "outbox" → "outbo", "index" → "inde". The gain on "journaux" is not worth that
    # damage; caught by this package's tests/recall_cache.py, which my own trials
    # had not seen.
    if t.endswith("s") and len(t) > 4:             # 1. plural
        t = t[:-1]
    for suf in _SUFFIXES:                          # 2. a single suffix
        if t.endswith(suf) and len(t) - len(suf) >= _MIN_STEM:
            return t[: -len(suf)]
    return t


# French ↔ English aliases. The trunk is written in both languages: "offline" is in 37
# notes, "queue" in 27, "deploy" in 54 — but people type "hors ligne", "file d'attente",
# "déploiement". NO stemmer crosses a TRANSLATION: measured, "l app terrain plante hors
# ligne" left offline-first-queue-pattern beyond rank 20 with or without stemming; with
# these aliases it climbs to rank 4.
# Applied BEFORE stemming, so that corpus and query are normalised the same way.
# The table is short and justified by the corpus: a pair is only added when both words
# are really present in it — no invented vocabulary.
_ALIAS = {
    r"hors[- ]ligne": "offline",
    r"file d[' ]attente": "queue",
    r"\bsauvegarde\w*": "backup",
    r"\bdeploiement\w*": "deploy",
    r"\bdeploy(?:er|ee?s?)\b": "deploy",
    r"mise en production": "deploy",
    r"\bmemoire cache\b": "cache",
}
# ONE pass, not one per pair. Seven separate `sub()` calls walked the whole
# document seven times; a single alternation walks it once and dispatches on the
# group that matched. The longest pattern still comes first — Python tries the
# alternatives left to right at each position, so the order that made the
# sequential version correct keeps the combined one correct.
_ALIAS_PAIRS = sorted(_ALIAS.items(), key=lambda kv: -len(kv[0]))
_ALIAS_RE = re.compile("|".join(f"({k})" for k, _ in _ALIAS_PAIRS))
_ALIAS_CANON = [v for _, v in _ALIAS_PAIRS]


def apply_aliases(txt):
    return _ALIAS_RE.sub(lambda m: _ALIAS_CANON[m.lastindex - 1], txt)


def tokenize(text):
    return [stem(t) for t in re.findall(r"[a-z0-9]+", apply_aliases(fold(text)))
            if len(t) > 2 and t not in STOP]


def strip_md(text):
    text = re.sub(r"^---\n.*?\n---", "", text, flags=re.S)   # frontmatter
    text = re.sub(r"```.*?```", " ", text, flags=re.S)        # blocs code
    return text


def _indexable():
    """The .md files recall considers, sorted — the input to the fingerprint."""
    return _indexable_from(BRAIN)


def _fingerprint(files):
    """Identity of the trunk's indexable content: path, mtime and size.

    A stat() per file, a few milliseconds — against the ~200 ms it takes to
    read and tokenize them. Content hashing would mean reading everything,
    which is the cost we are avoiding.
    """
    h = hashlib.sha256()
    for rel, p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        h.update(f"{rel}\0{st.st_mtime_ns}\0{st.st_size}\0".encode())
    # ⚠️ THE RANKING CONFIG DECIDES THE INDEXED TEXT, SO IT BELONGS IN THE FINGERPRINT.
    # Its `index` section (name, description and family-bridge weights) changes what gets
    # tokenised. Without this line, editing a weight would re-read the PREVIOUS cache and
    # the change would be ignored IN SILENCE — measured on a sister trunk on 2026-08-14:
    # two runs identical to the cent after changing both a lexicon and a weight, because
    # the old index was being served. We hash the WHOLE file rather than just the `index`
    # section: splitting the hash over part of the content is the kind of cleverness that
    # desynchronises the day someone moves a key. The cost is one index rebuild (~0.4 s)
    # after a weight change that did not need it — the right side to err on, since
    # rebuilding for nothing is free and serving a stale index is not.
    try:
        with open(os.path.join(BRAIN, "config", "ranking.json"), "rb") as f:
            h.update(b"\0ranking\0"); h.update(f.read())
    except OSError:
        h.update(b"\0ranking\0absent")
    return h.hexdigest()


def load_corpus():
    """Tokenized notes, from a cache when the trunk has not changed.

    WHY THIS IS CACHED. This runs on EVERY prompt, through the recall hook.
    Uncached it re-read and re-tokenized the whole trunk each time: 214 ms on a
    241-note trunk, and it grows linearly — about 1.6 s at 5000 notes. The user
    paid that on every single message, and nothing would ever have reported it,
    because recall stayed perfectly correct. It just got slower every week.
    Measured by tests/recall_benchmark.py, which now gates the build time.

    JSON rather than pickle: the cache is a file on disk, and a format that can
    execute code on load is not worth a few milliseconds.
    """
    files = _indexable()
    fp = _fingerprint(files)
    cache = os.path.join(BRAIN, "state", "recall-index.json")

    try:
        with open(cache, encoding="utf-8") as f:
            blob = json.load(f)
        if blob.get("fingerprint") == fp and blob.get("version") == _CACHE_VERSION:
            return blob["docs"]
    except Exception:
        pass        # absent, unreadable, truncated: rebuild, never fail

    docs = _read_corpus(files)

    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        # Atomic: a hook killed mid-write must not leave a half-file that the
        # next run reads as authoritative.
        tmp = f"{cache}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": _CACHE_VERSION, "fingerprint": fp, "docs": docs}, f)
        os.replace(tmp, cache)
    except Exception:
        pass        # read-only trunk, full disk: recall still works, just slower

    return docs


# Bumped whenever tokenisation or the document shape changes, so an old cache
# is discarded instead of silently serving notes scored under the previous rules.
#   v2 (2026-08-12): stemming + FR/EN aliases in tokenize().
#   v3 (2026-08-12): documents carry redirectsTo / relations.replaces.
#   v4 (2026-08-16): the indexing weights come from config/ranking.json, which is now part
#       of the fingerprint too. The VALUES did not move (3/3), so a v3 cache and a v4 cache
#       hold the same documents. We bump anyway, because a version number that stays put
#       when the SOURCE of the weights changes is a trap set for next time.
_CACHE_VERSION = 4


# ---------------------------------------------------------------- ranking configuration
# WHY THIS BLOCK. The weights lived hardcoded below: nobody could read them without reading
# the engine, and no result could say where its score came from. They move out into
# config/ranking.json — AT IDENTICAL BEHAVIOUR, which is the condition of the operation.
#
# The defaults below are not decorative: they are EXACTLY the previous hardcoded values.
# File absent, unreadable or truncated → recall ranks exactly as before. A configuration
# must never be able to break recall; at worst it does not apply.
_DEFAULTS = {
    "version": "ranking-v1-default",
    # family_bridge_weight is 0 ON PURPOSE. The mechanism is here and configurable, but it
    # is OFF until a measurement earns it: at weight 1, on a 15-case golden set over a real
    # trunk, it demoted the note that literally answers the query from 1st to 2nd place and
    # promoted an off-topic one (P@1 0.7333 → 0.6667, MRR 0.8000 → 0.7667). It also needs
    # meta/familles.json, which this package does not ship yet. Turning it on is a decision
    # backed by a measurement, not a default.
    "index": {"name_weight": 3, "description_weight": 3, "family_bridge_weight": 0},
    "bm25": {"k1": 1.5, "b": 0.75},
    "utility": {"alpha": 0.2},
    "exploration": {"denominator": 3, "rarely_suggested_threshold": 3},
}
_CONFIG_CACHE = None


def config():
    """Ranking weights, merged over the defaults. Loaded once per process.

    Merged KEY BY KEY rather than section by section: a file that only redefines
    `utility.alpha` must not make `bm25.k1` disappear. Keys starting with `_` are
    documentation (the file is meant to be read by a human), never parameters.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _DEFAULTS.items()}
    try:
        with open(os.path.join(BRAIN, "config", "ranking.json"), encoding="utf-8") as f:
            raw = json.load(f)
        for section, values in raw.items():
            if section.startswith("_"):
                continue
            if isinstance(values, dict) and isinstance(cfg.get(section), dict):
                for key, val in values.items():
                    if not key.startswith("_") and isinstance(val, (int, float)):
                        cfg[section][key] = val
            elif not isinstance(values, dict):
                cfg[section] = values
    except Exception:
        pass        # absent / unreadable / broken: rank with the defaults, without noise
    _CONFIG_CACHE = cfg
    return cfg


# ── the thematic family registry (label + lexicon). The TRUTH of membership lives in each
# note's `tags:`; this file carries only the vocabulary bridge. Absent here by design: this
# package does not ship meta/familles.json yet, so the axis is simply inactive.
def _load_families():
    try:
        with open(os.path.join(BRAIN, "meta", "familles.json"), encoding="utf-8") as f:
            return json.load(f).get("familles", {})
    except Exception:
        return {}          # registry absent = thematic axis inactive, never an exception


_FAMILIES = _load_families()


def _fm_tags(fm):
    m = re.search(r"^tags:\s*\[(.*?)\]", fm, re.M)
    return [t.strip() for t in m.group(1).split(",") if t.strip()] if m else []


def _read_corpus(files):
    docs = []
    for rel, p in files:
        try:
            raw = open(p, encoding="utf-8").read()
        except Exception:
            continue
        fm = re.match(r"^---\n(.*?)\n---", raw, re.S)
        name = re.search(r"^name:\s*(.+)$", fm.group(1), re.M) if fm else None
        desc = re.search(r'^description:\s*"?(.+?)"?\s*$', fm.group(1), re.M) if fm else None
        body = strip_md(raw)
        # title/description weigh more (×3): the densest signal
        # ── THEMATIC AXIS: a tag opens a VOCABULARY BRIDGE ──
        # `strip_md()` removes the whole frontmatter, so a `tags:` line was written by the
        # author and read by NOBODY. The bridge is not the tag itself — nobody types
        # "controle-qui-ment" — it is the family's LEXICON (meta/familles.json), the words
        # people actually type that the notes themselves do not use.
        # ⚠️ SHIPPED AT WEIGHT 0. Measured at weight 1 on a 15-case golden set over a real
        # trunk: a note that INHERITS a word from its family overtook the note that WRITES
        # it, demoting the literal answer from 1st to 2nd place. The bridge must catch what
        # the words miss, never cover what they find. The knob exists; turning it up is a
        # decision that owes a measurement.
        cfg_idx = config()["index"]
        bridge = ""
        for t in _fm_tags(fm.group(1) if fm else ""):
            fam = _FAMILIES.get(t)
            if fam:
                bridge += " " + fam["titre"] + " " + " ".join(fam["lexique"])
        bridge = (bridge + " ") * int(cfg_idx["family_bridge_weight"])
        boosted = ((name.group(1) + " ") * int(cfg_idx["name_weight"]) if name else "") + \
                  ((desc.group(1) + " ") * int(cfg_idx["description_weight"]) if desc else "") + \
                  bridge + " " + body
        docs.append({
            "path": rel,
            # succession: is this note an alias (redirectsTo) and/or does it
            # replace others (relations.replaces)? cf. _superseded()
            "redirects_to": _fm_field(raw, "redirectsTo"),
            "replaces": _fm_replaces(raw),
            "name": name.group(1).strip() if name else os.path.basename(rel)[:-3],
            "desc": desc.group(1).strip() if desc else "",
            "tokens": tokenize(boosted),
            # `bridge_words` serves --explain ONLY: whether a note owes its place to its
            # family's vocabulary rather than its own words is the first question asked
            # when a result surprises. It is not a term of the score.
            "bridge_words": sorted(set(tokenize(bridge))),
        })
    return docs


# ---------------------------------------------------------------- usage → ranking loop
# What has ALREADY served climbs. The recall log had existed for months and nobody read it
# back: `inject_recall.py` opened it in "a" mode and nothing ever read it — 2.3% of the
# suggested notes were actually opened, and nothing corrected that rate.
# The multiplier is logarithmic: 1 hit weighs a lot, the 10th almost nothing. A note used
# 3 times must not crush lexical relevance, only break its ties.
# α IS MEASURED, NOT PICKED AT RANDOM. There is no ground truth to optimise it against, so
# we measure its SENSITIVITY instead. Over 10 queries, the share of the top-3 held by notes
# with a history: α=0 → 3/30 · 0.2 → 8/30 · 0.5 → 12/30 · 1.0 → 15/30 (and only one query
# in ten keeps its original top-3). Past ~0.3 the history dictates the ranking and the
# lexical score is no longer the judge. 0.2 = usage breaks ties without dominating.
# Both values now live in config/ranking.json, with their justification. The defaults are
# these exact numbers, so a trunk without that file ranks exactly as it did before.
ALPHA = config()["utility"]["alpha"]
RARELY_SUGGESTED = config()["exploration"]["rarely_suggested_threshold"]
_UTILITY_CACHE = None


def _utility():
    """{path: {sugg, hit}} produced by recall_feedback.py. Loaded once per process.
    Absent = recall behaves exactly as before: this file never causes a failure."""
    global _UTILITY_CACHE
    if _UTILITY_CACHE is None:
        try:
            with open(os.path.join(BRAIN, "state", "recall-utility.json"), encoding="utf-8") as f:
                _UTILITY_CACHE = json.load(f)
        except Exception:
            _UTILITY_CACHE = {}
    return _UTILITY_CACHE


# ---------------------------------------------------------------- note succession
# `redirectsTo:` ALREADY existed in the frontmatter (1 note) and was read by NOBODY: a
# merged note therefore stayed the equal of the one replacing it in recall, and could come
# out ahead of it. It is the same relation as `relations.replaces` in the gardening rules
# §4 bis, seen from the other end — we read both rather than invent a competing convention.
_FM_REPLACES = re.compile(r"^\s+replaces\s*:\s*\[([^\]]*)\]", re.M)


def _header(raw):
    m = re.match(r"^---\n(.*?)\n---", raw, re.S)
    return m.group(1) if m else ""


def _fm_field(raw, field):
    m = re.search(rf"^\s*{field}\s*:\s*[\"']?([^\"'\n]+)[\"']?\s*$", _header(raw), re.M)
    return m.group(1).strip() if m else None


def _fm_replaces(raw):
    m = _FM_REPLACES.search(_header(raw))
    return [c.strip().strip("\"'") for c in m.group(1).split(",") if c.strip()] if m else []


def _superseded(docs):
    """Names of notes replaced by another — removed from recall, never from disk.
    We only set one aside if the note that succeeds it is really present in the index:
    otherwise a broken redirect would erase the knowledge instead of redirecting it."""
    present = {d["name"] for d in docs}
    dead = set()
    for d in docs:
        if d.get("redirects_to") and d["redirects_to"] in present:
            dead.add(d["name"])                  # this note is an alias
        for target in d.get("replaces") or ():
            if target in present and d["name"] in present:
                dead.add(target)                 # this note replaces another one
    return dead


class BM25:
    """Lexical backend — Okapi BM25. Swappable for an embeddings backend."""
    def __init__(self, docs, k1=None, b=None):
        cfg = config()["bm25"]
        k1 = cfg["k1"] if k1 is None else k1
        b = cfg["b"] if b is None else b
        self.docs, self.k1, self.b = docs, k1, b
        self.N = len(docs)
        self.dl = [len(d["tokens"]) for d in docs]
        self.avgdl = (sum(self.dl) / self.N) if self.N else 0
        self.tf = [Counter(d["tokens"]) for d in docs]
        df = Counter()
        for d in docs:
            for t in set(d["tokens"]):
                df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def _contrib(self, i, t):
        """BM25 contribution of term `t` to document `i`.

        THE FORMULA IS WRITTEN ONLY HERE. The ranking that is served and the explanation
        of the score call the same function, so it is impossible for recall to explain one
        calculation and serve another. Two writings of the same formula always drift, and
        the drift is invisible.
        """
        f = self.tf[i].get(t, 0)
        if not f:
            return 0.0
        denom = f + self.k1 * (1 - self.b + self.b * self.dl[i] / (self.avgdl or 1))
        return self.idf.get(t, 0) * (f * (self.k1 + 1)) / denom

    def rank(self, query, k=5, feedback=True):
        """The ranking WITH its decomposition — the single source of search() and --explain.

        Returns an ordered list of dicts, one per kept result:
          doc · bm25 · bm25_detail · hits · utility_factor · score · exploration · rank

        `search()` keeps only (score, doc) so its callers see no change.
        """
        q = tokenize(query)
        scored = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                s += self._contrib(i, t)
            if s > 0:
                scored.append((s, d, i))
        if not scored:
            return []
        dead = _superseded(self.docs)
        if dead:
            alive = [t for t in scored if t[1]["name"] not in dead]
            scored = alive or scored          # never an empty result because of the filter
        util = _utility() if feedback else {}
        alpha = config()["utility"]["alpha"]
        adjusted = []
        for s, d, i in scored:
            hits = util.get(d["path"], {}).get("hit", 0)
            factor = 1 + alpha * math.log(1 + hits)
            adjusted.append({"doc": d, "idx": i, "bm25": s, "hits": hits,
                             "utility_factor": factor, "score": s * factor,
                             "exploration": False})
        adjusted.sort(key=lambda r: r["score"], reverse=True)

        def finish(kept):
            """Per-term detail computed ONLY on the kept results.

            Doing it for the hundreds of notes that score a point would cost on every
            prompt for information nobody reads. It is the same `_contrib`, so the detail
            cannot tell a different story from the score.
            """
            for rank_, r in enumerate(kept, start=1):
                r["rank"] = rank_
                r["bm25_detail"] = {t: round(self._contrib(r["idx"], t), 4)
                                    for t in q if self._contrib(r["idx"], t) > 0}
            return kept

        if not util:
            return finish(adjusted[:k])

        # EXPLORATION QUOTA — 1 slot in 3. Without it the loop reinforces itself: a note
        # already opened climbs, so it is suggested more often, so it is opened more
        # often. Rare but right notes would vanish from recall without anything ever
        # reporting it. So we reserve slots for the SELDOM suggested.
        cfg_ex = config()["exploration"]
        n_explore = k // int(cfg_ex["denominator"])
        threshold = cfg_ex["rarely_suggested_threshold"]
        kept = adjusted[:k - n_explore]
        seen = {id(r["doc"]) for r in kept}
        fresh = [r for r in adjusted[k - n_explore:]
                 if id(r["doc"]) not in seen
                 and util.get(r["doc"]["path"], {}).get("sugg", 0) < threshold]
        for r in fresh[:n_explore]:
            r["exploration"] = True               # this slot is owed to the quota, not the score
            kept.append(r); seen.add(id(r["doc"]))
        for r in adjusted[k - n_explore:]:         # not enough fresh ones: fill in normally
            if len(kept) >= k:
                break
            if id(r["doc"]) not in seen:
                kept.append(r); seen.add(id(r["doc"]))
        return finish(kept[:k])

    def search(self, query, k=5, feedback=True):
        """(score, doc) — the historic shape, so callers see no change."""
        return [(r["score"], r["doc"]) for r in self.rank(query, k, feedback)]


def _print_explanation(records, query, as_json):
    """"Why this note, and why in this position?"

    HONESTY OF THE SCHEMA. We do not invent components that do not exist in the
    calculation. The score is MULTIPLICATIVE today (bm25 × utility factor), not a sum of
    bonuses — so `utility` is published as the DELTA it actually adds, and its nature is
    named. Likewise:
      • the family bridge is NOT a term of the score: it is folded into the indexed text,
        therefore into `bm25`. We publish which of the query's words came from it, which
        answers the real question ("does this note owe its place to its own words or to
        its family's?") without fabricating a number.
      • exploration is NOT a numeric bonus: it is a RESERVED SLOT. We publish a boolean,
        because that is what it is.
    Publishing `"family": 0.70` when nothing in the code computes 0.70 would be a false
    explanation — worse than no explanation, because it would be trusted.
    """
    cfg = config()
    out = []
    for r in records:
        d = r["doc"]
        bridge = sorted(set(d.get("bridge_words") or []) & set(r["bm25_detail"]))
        out.append({
            "note": d["name"],
            "path": d["path"],
            "rank": r["rank"],
            "final_score": round(r["score"], 4),
            "components": {
                "bm25": round(r["bm25"], 4),
                "utility": round(r["score"] - r["bm25"], 4),
            },
            "nature": {
                "utility": f"MULTIPLICATIVE x{r['utility_factor']:.4f} "
                           f"(alpha={cfg['utility']['alpha']}, hits={r['hits']})",
                "family_bridge": "folded into bm25, never a separate term",
                "exploration": "reserved slot, never a score bonus",
            },
            "bm25_detail": dict(sorted(r["bm25_detail"].items(),
                                       key=lambda kv: kv[1], reverse=True)),
            "words_from_bridge": bridge,
            "exploration_slot": r["exploration"],
            "config_version": cfg.get("version"),
        })
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"🔬 Score breakdown for \"{query}\"\n")
    for e in out:
        flag = "  <- exploration slot" if e["exploration_slot"] else ""
        print(f"  #{e['rank']}  [{e['final_score']:6.2f}] {e['note']}{flag}")
        c = e["components"]
        print(f"        bm25 {c['bm25']:6.2f}   utility {c['utility']:+6.2f}"
              f"   ({e['nature']['utility']})")
        if e["bm25_detail"]:
            terms = "  ".join(f"{t} {v:.2f}" for t, v in list(e["bm25_detail"].items())[:6])
            print(f"        terms: {terms}")
        if e["words_from_bridge"]:
            print(f"        ⚠️  owes the family bridge: {', '.join(e['words_from_bridge'])}")
        print()
    print(f"  config: {out[0]['config_version'] if out else '—'}"
          f"  (config/ranking.json)")


def main():
    args = [a for a in sys.argv[1:]]

    # --semantic mode: delegates to the embeddings backend (venv model2vec) when available.
    # Default = BM25 (instant, and better than static embeddings at small scale).
    if "--semantic" in args:
        args.remove("--semantic")
        venv_py = os.path.join(BRAIN, ".venv", "bin", "python")
        embed = os.path.join(BRAIN, "hooks", "brain_embed.py")
        if os.path.exists(venv_py) and os.path.exists(embed):
            import subprocess
            os.execv(venv_py, [venv_py, embed, "query"] + args)
        # sinon : repli silencieux sur BM25

    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    explain = "--explain" in args
    if explain:
        args.remove("--explain")
    k = 5
    if "-k" in args:
        i = args.index("-k")
        try:
            k = int(args[i + 1]); del args[i:i + 2]
        except Exception:
            pass
    query = " ".join(args).strip()
    if not query:
        print('Usage: brain_recall.py [-k N] [--json] [--explain] "your query"'); sys.exit(1)

    engine = BM25(load_corpus())
    if explain:
        records = engine.rank(query, k)
        if not records:
            print(f"No relevant note for: {query}"); return
        _print_explanation(records, query, as_json)
        return
    results = engine.search(query, k)
    if as_json:
        print(json.dumps([{"path": d["path"], "name": d["name"],
                           "desc": d["desc"], "score": round(s, 3)}
                          for s, d in results], ensure_ascii=False, indent=2))
        return
    if not results:
        print(f"No relevant note for: {query}"); return
    print(f"🔎 Top {len(results)} for '{query}':\n")
    for s, d in results:
        print(f"  [{s:5.2f}] {d['name']}  ({d['path']})")
        if d["desc"]:
            print(f"          {d['desc'][:110]}")


if __name__ == "__main__":
    main()
