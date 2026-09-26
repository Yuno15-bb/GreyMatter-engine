#!/usr/bin/env python3
"""brain_utility — the truth loop: measures the real USEFULNESS of each note.

Cross-references state/recall_log.jsonl (notes surfaced by recall) with
state/read_log.jsonl (notes actually read). Derives, per note:
  - surfaced  : how many times the retriever surfaced it
  - read      : nb de fois lue
  - hit       : surfaced AND read in the SAME session (recall actually paid off)
And sorts the notes into categories the gardener can act on:
  - 💀 dead weight : never surfaced, never read (an archiving candidate — A PROPOSAL)
  - 🔇 ignored     : surfaced ≥3× but never read (weak description? low value?)
  - ⭐ pillar      : read a lot (keep it, perhaps split it)

A signal grounded in USAGE, not introspection. Honestly: a note can be useful
without being *read* (the pointer in context was enough) → "ignored" is a hint, not a verdict.

Usage : brain_utility.py [--json]   (exit 0)
"""
import os, sys, json, glob, time
from collections import defaultdict

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
RECALL = os.path.join(BRAIN, "state", "recall_log.jsonl")
READ = os.path.join(BRAIN, "state", "read_log.jsonl")
DEAD_AGE_DAYS = 30      # a note is only "dead weight" once it is at least this old
STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}


def all_fiches():
    out = {}
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        # the area allowlist (first segment) is enough and SAFE: the old `any(part in rel ...)`
        # (substring) wrongly excluded notes named "capsule-…" / "corpus-…".
        if rel == "MEMORY.md" or rel in STRUCTURAL_MAPS:
            continue
        if rel.split(os.sep)[0] in ("projects", "lessons", "life", "meta"):
            out[rel] = os.path.getmtime(p)
    return out


def read_log(path):
    rows = []
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    except Exception:
        pass
    return rows


def main():
    fiches = all_fiches()
    recalls, reads = read_log(RECALL), read_log(READ)

    surfaced = defaultdict(int); read_n = defaultdict(int)
    surf_sids = defaultdict(set); read_sids = defaultdict(set)
    for r in recalls:
        surfaced[r["path"]] += 1; surf_sids[r["path"]].add(r.get("sid", ""))
    for r in reads:
        read_n[r["path"]] += 1; read_sids[r["path"]].add(r.get("sid", ""))

    now = time.time()
    stats = []
    for rel, mtime in fiches.items():
        hits = len((surf_sids[rel] & read_sids[rel]) - {""})
        stats.append({"path": rel, "surfaced": surfaced[rel], "read": read_n[rel],
                      "hits": hits, "age_days": int((now - mtime) / 86400)})

    dead = [s for s in stats if s["surfaced"] == 0 and s["read"] == 0
            and s["age_days"] >= DEAD_AGE_DAYS]
    ignored = [s for s in stats if s["surfaced"] >= 3 and s["read"] == 0]
    pillars = sorted([s for s in stats if s["read"] > 0], key=lambda x: -x["read"])[:5]

    report = {"ts": int(now), "notes": len(stats),
              "events": {"surfaced": len(recalls), "read": len(reads)},
              "poids_mort": [s["path"] for s in dead],
              "ignorees": [s["path"] for s in ignored],
              "piliers": [{"path": s["path"], "read": s["read"]} for s in pillars]}

    if "--json" in sys.argv:
        os.makedirs(os.path.join(BRAIN, "state"), exist_ok=True)
        json.dump(report, open(os.path.join(BRAIN, "state", "utility.json"), "w"),
                  ensure_ascii=False, indent=2)
        return

    print(f"📊 Usefulness — {len(stats)} notes | {len(recalls)} surfaced, {len(reads)} read")
    if len(recalls) + len(reads) < 5:
        print("  ⏳ Not enough usage history yet (the signal builds up "
              "over the sessions).")
    if pillars:
        print("\n  ⭐ Pillars (the most read):")
        for s in pillars:
            print(f"     {s['read']:3}×  {s['path']}")
    if ignored:
        print("\n  🔇 Surfaced but never read (description worth revisiting?):")
        for s in ignored[:8]:
            print(f"     {s['surfaced']:3}↑  {s['path']}")
    if dead:
        print(f"\n  💀 Dead weight (never surfaced nor read, ≥{DEAD_AGE_DAYS}d) "
              f"→ PROPOSER l'archivage :")
        for s in dead[:8]:
            print(f"        {s['path']}")
    if not (pillars or ignored or dead):
        print("  (nothing notable — usage is still young)")


if __name__ == "__main__":
    main()
