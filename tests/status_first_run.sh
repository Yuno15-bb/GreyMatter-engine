#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# status_first_run.sh — `brain status` before the first session.
#
# WHY THIS EXISTS. The install's last screen offers `brain status` first, and a
# new user runs it right away — before any Claude Code session. The status file
# is written by the hooks while Claude Code works, so it did not exist yet, and
# the answer was "(no status: state/status.json is missing)". True, and read as a
# broken install: the first word the tool said about itself was "missing".
# Found on a blank Mac on 2026-09-26.
#
# The bench sets a trunk up the way the plugin does (a copy of the plugin, a
# fresh HOME), asks `brain status` before any session, then writes a status the
# way the PostToolUse heartbeat does and asks again: the calm first answer must
# not hide a real one.
#
# Run: bash tests/status_first_run.sh [--sabotage status-missing]
#   status-missing — the first answer says "missing" again; must go RED.
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
P="$H/plugin-cache/c-brain"
mkdir -p "$(dirname "$P")"
rsync -a --exclude .git --exclude node_modules "$ROOT/" "$P/"

if [ "$SABOTAGE" = "status-missing" ]; then
  python3 - "$P/hooks/brain_status.py" <<'SAB' || { echo "  ❌ sabotage did not apply"; exit 1; }
import sys
path = sys.argv[1]
src = open(path).read()
old = '        print("state    : not started yet")\n'
if src.count(old) != 1:
    sys.exit(1)
open(path, "w").write(src.replace(old, '        print("(no status: state/status.json is missing)")\n'))
SAB
  echo "  ⚠ sabotage status-missing applied to the cached plugin"
elif [ -n "$SABOTAGE" ]; then
  echo "unknown sabotage: $SABOTAGE"; exit 2
fi

export HOME="$H" CLAUDE_PLUGIN_ROOT="$P"
python3 "$P/cbrain/plugin_bootstrap.py" >/dev/null 2>&1
STATUS_FILE="$H/.c-brain/trunk/state/status.json"

echo "▸ before the first session"
[ ! -e "$STATUS_FILE" ]
check $? "no status file yet (the bench is aimed at the right case)"
OUT="$("$P/bin/brain" status 2>&1)"; rc=$?
check "$rc" "brain status exits 0"
printf '%s' "$OUT" | grep -qiE "missing|absent|unreadable|error"
[ $? -ne 0 ]; check $? "it does not read as a broken install" "said: $(printf '%s' "$OUT" | head -2 | tr '\n' ' ')"
printf '%s' "$OUT" | grep -q "not started yet"
check $? "it says why there is nothing yet"
[ ! -e "$STATUS_FILE" ]
check $? "asking wrote nothing (brain status only reads)"

echo "▸ once a hook has written a status"
python3 "$H/.c-brain/trunk/hooks/brain_status.py" heartbeat >/dev/null 2>&1
[ -e "$STATUS_FILE" ]; check $? "the heartbeat wrote the status, as it does during a session"
OUT="$("$P/bin/brain" status 2>&1)"
printf '%s' "$OUT" | grep -qE "^state +: (busy|idle)"
check $? "brain status now shows the real state" "said: $(printf '%s' "$OUT" | head -2 | tr '\n' ' ')"
printf '%s' "$OUT" | grep -q "not started yet"
[ $? -ne 0 ]; check $? "the first-run answer is gone"

if [ "$FAILS" -eq 0 ]; then
  echo "✅ brain status is calm before the first session, and truthful after it"
  exit 0
fi
echo "❌ $FAILS check(s) failed"
exit 1
