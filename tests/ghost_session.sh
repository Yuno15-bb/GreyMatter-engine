#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# ghost_session.sh — a command is not a session.
#
# WHY THIS EXISTS. `claude plugin install` runs the SessionEnd hooks when it
# exits — any plugin, not only this one. Observed on 2026-09-26 with Claude Code
# 2.1.283, in a throwaway HOME set up by install.sh: one install put a session id
# in state/pending-distill.json and wrote an archive note, "Messages: ?", subject
# "(not captured)". The payload is always the same shape: a fresh session id, a
# transcript_path Claude Code never writes, reason "other". Queued, that id is a
# headless distillation spent later on nothing.
#
# The fix must not reopen the hole it sits next to: a session whose transcript
# CANNOT be measured is still queued ("unable to measure" is not "trivial", C7).
# So the bench replays three SessionEnds, through the hooks as Claude Code runs
# them: the ghost, a session with no transcript_path at all, and a real one.
#
# No `claude` is on PATH here, so nothing can launch a real maintenance run.
#
# Run: bash tests/ghost_session.sh [--sabotage ghost-queued|ghost-archived]
#   ghost-queued   — the maintenance queues the ghost again; must go RED.
#   ghost-archived — the archive writes a note for the ghost again; must go RED.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
SABOTAGE=""
[ "${1:-}" = "--sabotage" ] && SABOTAGE="${2:-}"
APPLE_PATH="/usr/bin:/bin:/usr/sbin:/sbin"
FAILS=0

check() {  # check <exit-code> <label> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

H="$(mktemp -d)"
trap 'rm -rf "$H"' EXIT
P="$H/plugin-cache/c-brain"
mkdir -p "$(dirname "$P")"
rsync -a --exclude .git --exclude node_modules "$ROOT/" "$P/"

if [ -n "$SABOTAGE" ]; then
  python3 - "$P" "$SABOTAGE" <<'SAB' || { echo "  ❌ sabotage $SABOTAGE did not apply"; exit 1; }
import sys, os
root, which = sys.argv[1], sys.argv[2]
swap = {
  "ghost-queued": ("hooks/auto_maintain.py",
                   "    if wrote_nothing(sid, tp):\n", "    if False:\n"),
  "ghost-archived": ("hooks/archive_session.py",
                     "    if sid and tp and not os.path.exists(tp) \\\n",
                     "    if False and sid and tp and not os.path.exists(tp) \\\n"),
}
if which not in swap:
    sys.exit(1)
rel, old, new = swap[which]
path = os.path.join(root, rel)
src = open(path).read()
if src.count(old) != 1:
    sys.exit(1)
open(path, "w").write(src.replace(old, new))
SAB
  echo "  ⚠ sabotage $SABOTAGE applied to the cached plugin"
fi

# The trunk as a plugin user has it; its hooks/ is a link into the copy above.
env -i HOME="$H" CLAUDE_PLUGIN_ROOT="$P" PATH="$APPLE_PATH" \
  python3 "$P/cbrain/plugin_bootstrap.py" >/dev/null 2>&1
T="$H/.c-brain/trunk"
[ -L "$T/hooks" ] || { echo "  ❌ no trunk to run the hooks against"; exit 1; }
QUEUE="$T/state/pending-distill.json"
# Where Claude Code puts a transcript for a session run from /tmp.
TDIR="$H/.claude/projects/-private-tmp"
mkdir -p "$TDIR"

session_end() {  # session_end <payload-json> — both SessionEnd hooks, as Claude Code runs them
  for hook in archive_session.py auto_maintain.py; do
    printf '%s' "$1" | env -i HOME="$H" PATH="$APPLE_PATH" LANG=en_US.UTF-8 \
      python3 "$T/hooks/$hook" >/dev/null 2>&1
  done
}
queued() { python3 -c 'import json,sys; sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1])) else 1)' "$QUEUE" "$1" 2>/dev/null; }
archived() { ls "$T/sessions/archive/" 2>/dev/null | grep -q "${1:0:8}"; }

echo "▸ the ghost: what \`claude plugin install\` sends when it exits"
G="aaaa1111-0000-4000-8000-000000000001"
[ ! -e "$TDIR/$G.jsonl" ] || { echo "  ❌ the ghost's transcript exists — the bench is aimed wrong"; exit 1; }
session_end "{\"session_id\":\"$G\",\"transcript_path\":\"$TDIR/$G.jsonl\",\"cwd\":\"/private/tmp\",\"hook_event_name\":\"SessionEnd\",\"reason\":\"other\"}"
queued "$G"; [ $? -ne 0 ]
check $? "it is not queued for distillation" "pending-distill.json: $(cat "$QUEUE" 2>/dev/null)"
archived "$G"; [ $? -ne 0 ]
check $? "no archive note is written for it" "$(ls "$T/sessions/archive/" 2>/dev/null | grep "${G:0:8}")"

echo "▸ control: a session Claude Code gave no transcript path for"
# Unmeasurable is not trivial: this one has to stay queued, or the fix above
# has quietly become "drop what we cannot read".
U="bbbb2222-0000-4000-8000-000000000002"
session_end "{\"session_id\":\"$U\",\"cwd\":\"/private/tmp\",\"hook_event_name\":\"SessionEnd\",\"reason\":\"other\"}"
queued "$U"
check $? "it is still queued — unable to measure is not the same as empty"

echo "▸ control: a real session, with a transcript on disk"
R="cccc3333-0000-4000-8000-000000000003"
for i in 1 2 3; do printf '{"type":"user","sessionId":"%s","message":{"role":"user","content":"hello %s"}}\n' "$R" "$i"; done > "$TDIR/$R.jsonl"
session_end "{\"session_id\":\"$R\",\"transcript_path\":\"$TDIR/$R.jsonl\",\"cwd\":\"/private/tmp\",\"hook_event_name\":\"SessionEnd\",\"reason\":\"prompt_input_exit\"}"
archived "$R"
check $? "it is archived, as every session is"
queued "$R"; [ $? -ne 0 ]
check $? "and, at 3 messages, measured as trivial rather than queued"

if [ "$FAILS" -eq 0 ]; then
  echo "✅ a command leaves no session behind; an unmeasurable session is still kept"
  exit 0
fi
echo "❌ $FAILS check(s) failed"
exit 1
