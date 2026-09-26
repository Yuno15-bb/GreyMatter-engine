#!/usr/bin/env python3
"""PostToolUse (Write|Edit|MultiEdit|NotebookEdit) — computes the real diff and pushes it
to the tracker. Starts on the FIRST code modification of the session.
"""

import difflib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def kick_browser(sid):
    """Wakes the tab reloader, detached: the hook never waits for it."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_reload.py")
    try:
        dn = open(os.devnull, "wb")
        subprocess.Popen(["python3", script, sid], stdout=dn, stderr=dn, stdin=dn,
                         start_new_session=True)
    except Exception:
        pass


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except Exception:
        return None


def main():
    from companion_lib import (MAX_DIFF_LINES, MAX_FILE_BYTES, append_event,
                               is_secret_path, mask_line, project_name,
                               read_hook_input, snap_path, target_path)

    data = read_hook_input()
    sid = data.get("session_id")
    cwd = data.get("cwd") or ""
    tool = data.get("tool_name") or "?"
    fpath = target_path(data.get("tool_input"))
    if not sid or not fpath:
        return

    rel = os.path.relpath(fpath, cwd) if cwd and fpath.startswith(cwd) else fpath
    base = {
        "type": "diff",
        "tool": tool,
        "file": fpath,
        "rel": rel,
        "project": project_name(cwd),
        "cwd": cwd,
    }

    # 1. Fichier sensible : on signale la modification, on ne montre RIEN.
    if is_secret_path(fpath):
        base.update({"masked": True, "note": "sensitive file — content not shown",
                     "added": 0, "removed": 0, "diff": []})
        append_event(sid, base)
        return

    snap = snap_path(sid, fpath)
    created = os.path.exists(snap + ".new")
    too_big = os.path.exists(snap + ".big")

    if too_big or (os.path.exists(fpath) and os.path.getsize(fpath) > MAX_FILE_BYTES):
        base.update({"truncated": True, "note": "file too large — diff not computed",
                     "added": 0, "removed": 0, "diff": []})
        append_event(sid, base)
        return

    before = read_text(snap) if os.path.exists(snap) else []
    after = read_text(fpath)
    if after is None:                     # file deleted, or an unreadable binary
        after = []
    if before is None:
        before = []

    diff = list(difflib.unified_diff(before, after, lineterm="", n=3,
                                     fromfile="before", tofile="after"))[2:]
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

    truncated = len(diff) > MAX_DIFF_LINES
    if truncated:
        diff = diff[:MAX_DIFF_LINES]
    diff = [mask_line(l) for l in diff]

    if not diff:
        return                            # an edit with no effect: nothing to show

    base.update({"created": created, "added": added, "removed": removed,
                 "truncated": truncated, "diff": diff})
    append_event(sid, base)
    kick_browser(sid)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
