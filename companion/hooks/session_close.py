#!/usr/bin/env python3
"""SessionEnd — marks the end in the stream and cleans up before-images and totals.

The `sessions/<sid>.jsonl` stream stays on disk (purged after 7 days): it is the
re-readable archive of what was touched during the session.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


FEED_TTL_DAYS = 7


def prune_old_feeds():
    """Session streams are the re-readable archive; past a week they only
    serve to fill up the disk."""
    import time

    from companion_lib import SESSIONS

    cutoff = time.time() - FEED_TTL_DAYS * 86400
    try:
        names = os.listdir(SESSIONS)
    except OSError:
        return
    for name in names:
        p = os.path.join(SESSIONS, name)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass


def main():
    # ANTI-RECURSION (Phase 0 of the Brain V3 RFC, 2026-08-03): a headless
    # maintenance agent is not a work session — it must neither close a feed nor
    # prune the pre-images of the real session in progress.
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return

    from companion_lib import AGG, SNAP, append_event, read_hook_input

    data = read_hook_input()
    sid = data.get("session_id")
    if not sid:
        return

    append_event(sid, {"type": "end", "reason": data.get("reason") or "fin de session"})

    shutil.rmtree(os.path.join(SNAP, sid), ignore_errors=True)
    try:
        os.remove(os.path.join(AGG, sid + ".json"))   # totaux : la session est finie
    except OSError:
        pass
    prune_old_feeds()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
