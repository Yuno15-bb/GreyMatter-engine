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
# And a third, found on a blank Mac on 2026-09-26, that no fixture could show:
# Claude Code runs the SessionEnd hooks when `claude plugin install` ITSELF
# exits. The maintenance writes state/ right then — so by the first SessionStart
# the trunk folder already existed, the bootstrap took it for a set-up trunk, and
# every plugin user got no index, no config, no history and no welcome line, and
# a `brain selftest` that stayed red. This bench now replays that order.
#
# Run: bash tests/plugin_install.sh [--sabotage folder-means-set-up|no-history]
#   folder-means-set-up — "the folder exists" counts as set up again; must go RED.
#   no-history          — the bootstrap stops starting the trunk's git history; must go RED.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
SABOTAGE=""
[ "${1:-}" = "--sabotage" ] && SABOTAGE="${2:-}"
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

# A sabotage puts back one of the two faults in the cached copy, the way an old
# release would ship it. It must turn this bench red, or the bench guards nothing.
if [ -n "$SABOTAGE" ]; then
  python3 - "$P/cbrain/plugin_bootstrap.py" "$SABOTAGE" <<'SAB' || { echo "  ❌ sabotage $SABOTAGE did not apply"; exit 1; }
import sys
path, which = sys.argv[1], sys.argv[2]
src = open(path).read()
swap = {
  "folder-means-set-up": ('    fresh = not os.path.exists(os.path.join(TRUNK, "MEMORY.md")) \\\n'
                          '        and not os.path.exists(os.path.join(TRUNK, ".git"))\n',
                          '    fresh = not os.path.isdir(TRUNK)\n'),
  "no-history": ("        start_history()\n", "        pass\n"),
}
if which not in swap or src.count(swap[which][0]) != 1:
    sys.exit(1)
open(path, "w").write(src.replace(*swap[which]))
SAB
  echo "  ⚠ sabotage $SABOTAGE applied to the cached plugin"
fi

export HOME="$H"
export CLAUDE_PLUGIN_ROOT="$P"

echo "▸ first session: the trunk has to appear"
# What `claude plugin install` leaves behind before any session has started:
# its own SessionEnd hooks ran, and the maintenance queued that CLI session.
# Observed on a blank Mac: trunk/state/pending-distill.json, and nothing else
# in the C Brain folder.
mkdir -p "$H/.c-brain/trunk/state"
printf '["install-cli-session"]' > "$H/.c-brain/trunk/state/pending-distill.json"
OUT="$(python3 "$P/cbrain/plugin_bootstrap.py" 2>&1)"
[ -d "$H/.c-brain/trunk" ];              check $? "the trunk exists"
[ -f "$H/.c-brain/trunk/MEMORY.md" ];    check $? "the index is there"
[ -L "$H/.c-brain/engine" ];             check $? "the engine is linked"
[ -L "$H/.c-brain/trunk/hooks" ];        check $? "hooks are linked into the trunk"
[ -L "$H/.c-brain/trunk/agents" ];       check $? "agents are linked into the trunk"
git -C "$H/.c-brain/trunk" rev-parse -q --verify HEAD >/dev/null 2>&1
check $? "the trunk keeps a local history, as install.sh's does" "no git history: the session-end auto-save does nothing"
ST="$("$P/bin/brain" selftest 2>&1)"
check $? "brain selftest is green on a plugin trunk" "$(printf '%s' "$ST" | grep '❌' | head -3 | tr '\n' ' ')"

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
