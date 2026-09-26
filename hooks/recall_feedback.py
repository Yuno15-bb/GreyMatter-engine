#!/usr/bin/env python3
"""recall_feedback — closes the usage → ranking loop.

THE PROBLEM IT SOLVES. `inject_recall.py` appends to `state/recall_log.jsonl` and
**nobody ever reads that file back**. Same for `state/read_log.jsonl`, read only by the
3D visualisation. So for months the Brain had been logging what served and what never
served, and drawing nothing from it: 2.3% of suggested notes are actually opened, and
nothing corrected that rate.

WHAT IT COMPUTES. For each note, the number of times it was **suggested and then
actually opened within the same session**. That is the only honest signal available:
"suggested" alone proves nothing, "opened" alone can come from a manual search.

WHAT IT DELIBERATELY DOES NOT DO.
  • No penalty for notes that are never opened. A note can be excellent and badly
    described; punishing it in the ranking buries it for good and nobody ever sees it.

    ⚠️ AND ABOVE ALL: "often suggested, never opened" IS NOT a defect.
    Checked by hand over the 50 notes concerned — **exactly one** had a genuinely vague
    description. The others are the opposite case: their description ALREADY answers the
    question, so not opening the note is a SUCCESS.
    Example: `separation-pouvoirs-agent-teams`, suggested 73 times, never opened — its
    description says everything in one line.
    The output file used to be called `descriptions-to-rewrite.json`: that name presumed
    the defect and would have pushed someone to rewrite 50 notes, that is, to destroy
    what works. It now describes the OBSERVATION, not a verdict. It is a starting point
    for an investigation, to be read note by note.
  • No deletion. This file touches no note.

Outputs:
  state/recall-utility.json                  {path: {sugg, hit, last}} — read by brain_recall
  state/often-suggested-never-opened.json  raw observation, NOT a verdict (see above)

Usage:
  recall_feedback.py           recompute both files
  recall_feedback.py --report  recompute and print a readable summary
"""
import os, sys, json, collections, datetime

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
STATE = os.path.join(BRAIN, "state")
UTILITY = os.path.join(STATE, "recall-utility.json")
OFTEN_NEVER = os.path.join(STATE, "often-suggested-never-opened.json")

# A read that slightly precedes its suggestion still counts: the hook's timestamp and the
# read tool's timestamp are not written at the same instant.
TOLERANCE_S = 60
# Past this, "often suggested, never opened" stops being chance.
REVIEW_THRESHOLD = 8


def _read(name):
    p = os.path.join(STATE, name)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue                      # line truncated by a killed hook: skip it
            if d.get("path") and d.get("sid"):
                out.append(d)
    return out


def compute():
    suggestions, first = collections.defaultdict(set), {}
    for d in _read("recall_log.jsonl"):
        suggestions[d["path"]].add(d["sid"])
        key = (d["path"], d["sid"])
        first[key] = min(first.get(key, d["ts"]), d["ts"])

    reads = collections.defaultdict(list)
    for d in _read("read_log.jsonl"):
        reads[(d["path"], d["sid"])].append(d["ts"])

    # ADR-0018 / M5 (2026-09-19): usage no longer ranks, it ANNOTATES. An annotation that
    # does not say WHEN is worthless — "opened 5 times" may date from three months ago. The date
    # is computed here, in the loop that already holds the timestamps: recall itself reads
    # a number already written and pays nothing more on each prompt.
    utility = {}
    for path, sids in suggestions.items():
        derniers = []
        for sid in sids:
            vues = [ts for ts in reads.get((path, sid), ())
                    if ts >= first[(path, sid)] - TOLERANCE_S]
            if vues:                          # same rule as before: at least one read
                derniers.append(max(vues))    # following the suggestion, within tolerance
        utility[path] = {"sugg": len(sids), "hit": len(derniers)}
        if derniers:
            utility[path]["last"] = datetime.datetime.fromtimestamp(
                max(derniers)).strftime("%Y-%m-%d")

    to_review = sorted(
        ({"path": p, "sugg": v["sugg"]} for p, v in utility.items()
         if v["hit"] == 0 and v["sugg"] >= REVIEW_THRESHOLD),
        key=lambda x: -x["sugg"])
    return utility, to_review


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"            # atomic: never a half-written file
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    utility, to_review = compute()
    write(UTILITY, utility)
    write(OFTEN_NEVER, to_review)

    if "--report" not in sys.argv:
        return 0
    sugg = sum(v["sugg"] for v in utility.values())
    hit = sum(v["hit"] for v in utility.values())
    print(f"{len(utility)} notes suggested · {sugg} (note, session) pairs")
    print(f"suggested THEN opened: {hit} ({hit / sugg * 100:.1f}%)" if sugg else "no suggestion")
    carrying = sorted((v["hit"], v["sugg"], p) for p, v in utility.items() if v["hit"])
    print(f"\nnotes that really serve ({len(carrying)}):")
    for h, s, p in sorted(carrying, reverse=True)[:8]:
        print(f"  {h:3d}/{s:<3d}  {p}")
    print(f"\nsuggested ≥{REVIEW_THRESHOLD}× and never opened ({len(to_review)}) — an observation,")
    print("not a defect: a description that already answers makes the read pointless.")
    for x in to_review[:8]:
        print(f"  {x['sugg']:3d}×  {x['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
