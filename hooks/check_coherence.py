#!/usr/bin/env python3
"""check_coherence — mechanical detection of overlapping notes.

When a note is written, we look for its nearest neighbours (through brain_recall).
Si une voisine la recouvre FORTEMENT, on flague la PAIRE dans state/coherence.json
as "to check: contradiction?" — without judging ourselves.

Separation of roles (as everywhere else here):
  - HERE (mechanical, cheap): find the heavily overlapping pairs.
  - GARDENER (LLM): judge whether there really is a contradiction, and resolve it.

Le cerveau cesse de laisser deux fiches se contredire en silence.
Usage: check_coherence.py <path-to-note.md>   (launched detached by on_fiche_write)
Sort toujours 0.
"""
import os, sys, json, time, re, math
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import brain_recall as recall
except Exception:
    recall = None

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
FLAGS = os.path.join(BRAIN, "state", "coherence.json")
SIM_MIN = 0.45   # TF-IDF cosine (0–1): above this = real heavy overlap → check duplicate/contradiction


def is_pair(f):
    """An ACTIONABLE entry = an (a,b) pair to arbitrate. The file may also carry
    arbitration notes left by an agent: those are not work."""
    return isinstance(f, dict) and isinstance(f.get("a"), str) and isinstance(f.get("b"), str)


def existing_pairs(flags):
    """Pairs already known, tolerant of legacy/annotated entries (never a KeyError:
    this module runs DETACHED, so an exception here is invisible and freezes detection)."""
    return {tuple(sorted((f["a"], f["b"]))) for f in flags if is_pair(f)}


def tfidf_vec(tokens, idf):
    tf = Counter(tokens)
    vec = {t: (f / len(tokens)) * idf.get(t, 0) for t, f in tf.items()} if tokens else {}
    norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
    return {t: w / norm for t, w in vec.items()}


def cosine(a, b):
    small, big = (a, b) if len(a) < len(b) else (b, a)
    return sum(w * big.get(t, 0) for t, w in small.items())


def main():
    if recall is None or len(sys.argv) < 2:
        return
    target = os.path.realpath(sys.argv[1])
    if not target.startswith(BRAIN + os.sep) or not target.endswith(".md"):
        return
    rel = os.path.relpath(target, BRAIN)
    zone = rel.split(os.sep)[0]
    if zone not in ("projects", "lessons", "life", "meta"):
        return

    # shared corpus + idf
    docs = recall.load_corpus()
    if len(docs) < 2:
        return
    df = Counter()
    for d in docs:
        for t in set(d["tokens"]):
            df[t] += 1
    N = len(docs)
    idf = {t: math.log(1 + N / (n + 0.5)) for t, n in df.items()}

    me = next((d for d in docs if d["path"] == rel), None)
    if me is None:
        return
    name = me["name"]
    my_vec = tfidf_vec(me["tokens"], idf)

    # normalized cosine similarity against every other note
    neighbours = []
    for d in docs:
        if d["path"] == rel:
            continue
        sim = cosine(my_vec, tfidf_vec(d["tokens"], idf))
        if sim >= SIM_MIN:
            neighbours.append((sim, d))
    neighbours.sort(key=lambda x: x[0], reverse=True)
    if not neighbours:
        return

    try:
        flags = json.load(open(FLAGS, encoding="utf-8"))
    except Exception:
        flags = []
    existing = existing_pairs(flags)
    changed = False
    for s, d in neighbours[:2]:
        key = tuple(sorted((name, d["name"])))
        if key in existing:
            continue
        flags.append({"a": name, "b": d["name"], "sim": round(s, 2),
                      "ts": int(time.time()),
                      "status": "heavy overlap → check for a duplicate OR a contradiction"})
        existing.add(key)
        changed = True
    if changed:
        try:
            os.makedirs(os.path.dirname(FLAGS), exist_ok=True)
            json.dump(flags, open(FLAGS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
