#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# plugin_install.sh — the path a stranger actually takes.
#
# WHY THIS EXISTS. The CI proved `install.sh` works, and `install.sh` is the
# LONG path — clone the repo, run a script, get launchd jobs and an Electron
# window. Anyone arriving from the marketplace takes the other one: Claude Code
# copies the plugin into a cache and runs `plugin_bootstrap.py` at SessionStart.
# That path was never executed by anything.
#
# It was not broken, but it was WRONG in two ways nobody could have seen from
# the outside, and both were on the first screen a new user ever gets:
#   · the welcome line promised a `C Brain` shortcut in the home folder. That
#     folder is created by install.sh, which a plugin install never runs.
#   · `brain version` answered "(unknown version)", because only install.sh
#     wrote the VERSION file — and version is the first thing anyone is asked
#     for when something goes wrong.
#
# Neither would have failed a test. They would have been read, once, by every
# person who installed it.
#
# Run: bash tests/plugin_install.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0

check() {  # check <exit-code> <label> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

H="$(mktemp -d)"
trap 'rm -rf "$H"' EXIT

# Claude Code copies the plugin into a cache directory rather than running it
# from the repo, so the fixture does the same. Running from the repo would hide
# any path that only resolves because it happens to sit next to a .git.
P="$H/plugin-cache/c-brain"
mkdir -p "$(dirname "$P")"
rsync -a --exclude .git --exclude node_modules "$ROOT/" "$P/"

export HOME="$H"
export CLAUDE_PLUGIN_ROOT="$P"

echo "▸ first session: the trunk has to appear"
OUT="$(python3 "$P/cbrain/plugin_bootstrap.py" 2>&1)"
[ -d "$H/.c-brain/trunk" ];              check $? "the trunk exists"
[ -f "$H/.c-brain/trunk/MEMORY.md" ];    check $? "the index is there"
[ -L "$H/.c-brain/engine" ];             check $? "the engine is linked"
[ -L "$H/.c-brain/trunk/hooks" ];        check $? "hooks are linked into the trunk"
[ -L "$H/.c-brain/trunk/agents" ];       check $? "agents are linked into the trunk"

echo "▸ what it says must be true"
printf '%s' "$OUT" | grep -q "~/.c-brain/trunk"
check $? "the welcome line names where the trunk actually is"
# The promise that was not kept. If the shortcut is ever mentioned again here,
# it has to be because something in this path creates it.
if printf '%s' "$OUT" | grep -qi "shortcut"; then
  [ -e "$H/C Brain" ]
  check $? "a promised shortcut exists" "the first line a new user reads points at nothing"
else
  echo "  ✅ nothing is promised that this path does not create"
fi

echo "▸ the commands a plugin user can type"
V="$(HOME="$H" "$P/bin/brain" version 2>&1)"
printf '%s' "$V" | grep -qv "unknown"
check $? "brain version answers something" "got: $V"
printf '%s' "$V" | grep -q "$(python3 -c "import json;print(json.load(open('$P/.claude-plugin/plugin.json'))['version'])")"
check $? "and it matches the manifest" "got: $V"

HOME="$H" "$P/bin/brain" demo >/dev/null 2>&1
HOME="$H" "$P/bin/brain" recall cache deploy 2>/dev/null | grep -q "cache"
check $? "recall returns something on the demo trunk"

echo "▸ every session after the first is a non-event"
BEFORE="$(find "$H/.c-brain" -newer "$P/cbrain/plugin_bootstrap.py" 2>/dev/null | wc -l)"
OUT2="$(python3 "$P/cbrain/plugin_bootstrap.py" 2>&1)"
[ -z "$OUT2" ];                          check $? "it says nothing the second time" "printed: $OUT2"
[ -d "$H/.c-brain/trunk/lessons" ];      check $? "it did not wipe the trunk"

echo "▸ a real hooks/ folder is somebody's older install, and is left alone"
rm "$H/.c-brain/trunk/hooks"
mkdir -p "$H/.c-brain/trunk/hooks"
touch "$H/.c-brain/trunk/hooks/their-own-file.py"
python3 "$P/cbrain/plugin_bootstrap.py" >/dev/null 2>&1
[ -f "$H/.c-brain/trunk/hooks/their-own-file.py" ]
check $? "a real directory is never replaced by a link"

echo "▸ and it never takes the session down with it"
CLAUDE_PLUGIN_ROOT="/nonexistent/path" python3 "$P/cbrain/plugin_bootstrap.py" >/dev/null 2>&1
check $? "it exits 0 even pointed at nothing"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ the plugin path works, and says only true things"
  exit 0
fi
echo "❌ $FAILS failure(s) on the path most new users take"
exit 1
