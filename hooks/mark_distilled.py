#!/usr/bin/env python3
"""Adds a session_id to sessions/.distilled.json — called by the wrapper
ONLY if the distillation agent succeeded (claude exit 0). Prevents marking a
session 'distilled' when it actually failed (e.g. a quota limit was hit)."""
import json, os, sys

DISTILLED = os.path.expanduser("~/.c-brain/trunk/sessions/.distilled.json")

def main():
    if len(sys.argv) < 2:
        return
    sid = sys.argv[1]
    try:
        cur = set(json.load(open(DISTILLED, encoding="utf-8")))
    except Exception:
        cur = set()
    cur.add(sid)
    try:
        json.dump(sorted(cur), open(DISTILLED, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass

if __name__ == "__main__":
    main()
