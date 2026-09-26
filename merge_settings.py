#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""C Brain — wiring the hooks into ~/.claude/settings.json.

NON-DESTRUCTIVE, and that is the whole point: this file belongs to the user.
It may already hold their model, theme, permissions and their own hooks.
We ADD ours; we never rewrite the rest.

Idempotent: ownership is judged on the exact command. Re-running adds no
duplicate. Uninstalling removes ONLY our entries.

Usage:
  python3 merge_settings.py install [--settings <path>]
  python3 merge_settings.py remove  [--settings <path>]
"""

import json
import os
import shutil
import sys
import time

HOME = os.path.expanduser("~")
DEFAULT_SETTINGS = os.path.join(HOME, ".claude", "settings.json")
BRAIN = os.path.join(HOME, ".c-brain", "trunk")
CB = os.path.join(HOME, ".c-brain")

# (event, matcher or None, script path, timeout, status message)
HOOKS = [
    ("SessionStart", None, "hooks/brain_anticipate.py --hook", 10, None),
    # Reports a new version, installs nothing. Throttled to 1×/24 h in the script.
    ("SessionStart", None, "@cbrain/check_update.py", 20, None),
    ("UserPromptSubmit", None, "hooks/inject_recall.py", 10, None),
    ("PostToolUse", "Write|Edit", "hooks/on_fiche_write.py", 15, None),
    ("PostToolUse", "Read", "hooks/track_read.py", 10, None),
    ("PostToolUse", "Write|Edit|MultiEdit|NotebookEdit",
     "companion/hooks/post_diff.py", 8, None),
    ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit",
     "companion/hooks/pre_snapshot.py", 5, None),
    ("SessionEnd", None, "hooks/archive_session.py", 30,
     "Archiving the session into the trunk..."),
    ("SessionEnd", None, "hooks/auto_maintain.py", 15,
     "Autonomous trunk maintenance (distill + file)..."),
    ("SessionEnd", None, "companion/hooks/session_close.py", 5, None),
]

# What identifies OUR commands at uninstall time. Two roots:
# the trunk (~/.c-brain/trunk/...) and the engine (~/.c-brain/engine/...).
#
# `claude-brain` is kept ON PURPOSE, even though no path uses it any more: an
# installation predating migration 001 wrote commands that still carry it.
# Dropping the marker would leave those lines in settings.json forever — an
# uninstall that calls itself complete while forgetting half of what it put
# there. This marker is never coming out.
MARKERS = ("claude-brain", ".c-brain")

# The status line is COPIED into ~/.claude, but it only shows if it is DECLARED
# here. Copying the file without writing this key produced a status line that
# was installed and invisible — the textbook silent failure.
STATUSLINE_CMD = f"python3 {os.path.join(HOME, '.claude', 'statusline.py')}"


def command_for(script):
    """Two possible origins. A script prefixed with `@` lives in the ENGINE
    (specific to C Brain, absent from the original Brain); the others live in
    the trunk, where the symlinks make them visible."""
    if script.startswith("@"):
        return f"python3 {os.path.join(CB, 'engine', script[1:])}"
    return f"python3 {os.path.join(BRAIN, script)}"


def load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"❌ {path} is invalid JSON ({e}).\n"
                 f"   Fix it by hand: we do not rewrite a file we cannot parse.")


def backup(path, tag):
    if not os.path.exists(path):
        return None
    dest = f"{path}.bak-c-brain-{tag}"
    shutil.copy2(path, dest)
    return dest


def entries_of(settings, event):
    return settings.setdefault("hooks", {}).setdefault(event, [])


def install(settings):
    added = 0
    for event, matcher, script, timeout, status in HOOKS:
        cmd = command_for(script)
        groups = entries_of(settings, event)

        # Already wired? We compare the exact command, not the file's presence.
        if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
            continue

        hook = {"type": "command", "command": cmd, "timeout": timeout}
        if status:
            hook["statusMessage"] = status

        # We graft onto a group with the same matcher if one exists (that is the
        # shape Claude Code expects), otherwise we create one.
        target = next((g for g in groups if g.get("matcher") == matcher), None)
        if target is None:
            target = {"hooks": []}
            if matcher:
                target["matcher"] = matcher
            groups.append(target)
        target["hooks"].append(hook)
        added += 1

    # Status line: we impose it ONLY if the user has none already.
    # Overwriting theirs would be inviting ourselves onto their screen.
    if "statusLine" not in settings:
        settings["statusLine"] = {"type": "command", "command": STATUSLINE_CMD}
        added += 1
    return added


def remove(settings):
    dropped = 0
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        groups = hooks[event]
        for g in groups:
            before = len(g.get("hooks", []))
            g["hooks"] = [h for h in g.get("hooks", [])
                          if not any(m in h.get("command", "") for m in MARKERS)]
            dropped += before - len(g["hooks"])
        hooks[event] = [g for g in groups if g.get("hooks")]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)

    # We remove the status line only if it really is ours. If the user replaced
    # it with their own in the meantime, it stays.
    if settings.get("statusLine", {}).get("command") == STATUSLINE_CMD:
        settings.pop("statusLine")
        dropped += 1
    return dropped


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("install", "remove"):
        sys.exit(__doc__)
    action = sys.argv[1]
    path = DEFAULT_SETTINGS
    if "--settings" in sys.argv:
        path = sys.argv[sys.argv.index("--settings") + 1]

    settings = load(path)
    tag = time.strftime("%Y%m%d-%H%M%S")
    n = install(settings) if action == "install" else remove(settings)

    if n == 0:
        print(f"   settings.json — nothing to do ({'already wired' if action == 'install' else 'nothing of ours'})")
        return 0

    b = backup(path, tag)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")

    verb = "wired" if action == "install" else "removed"
    print(f"   settings.json — {n} hook(s) {verb}" + (f" · backup: {os.path.basename(b)}" if b else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
