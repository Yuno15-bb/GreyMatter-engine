#!/usr/bin/env bash
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_ask.sh — by default, session start LOOKS for a new version and the
# agent ASKS the user before anything is installed.
#
# WHY THIS EXISTS. From v1.28.0 to v2.1.0 session start installed new versions
# on its own. Since v2.1.1 that is an opt-in (`brain update --auto-on`, measured
# by tests/update_auto.sh) and the default asks first. Four promises carry the
# default, and each one is measured on disk or on the hook's output:
#   1. the look never blocks a session start;
#   2. nothing is installed until somebody says yes;
#   3. the agent is told to ask — once per version per day, not at every start;
#   4. a yes (`brain update`) installs, and the question stops.
#
# Usage: bash tests/update_ask.sh [--sabotage installs|nags]
#   installs  the hook and update.sh install silently again: act 2 must go red
#   nags      the once-a-day limit is gone: act 4 must go red
set -uo pipefail
SABOTAGE=""
[ "${1:-}" = "--sabotage" ] && SABOTAGE="${2:-}"
case "$SABOTAGE" in ""|installs|nags) ;; *) echo "❌ unknown sabotage: $SABOTAGE (known: installs, nags)"; exit 2 ;; esac

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0
check() {
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

[ "$(uname)" = "Darwin" ] || { echo "⤳ skipped: install.sh targets macOS"; exit 0; }
[ "$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" = "$ROOT" ] \
  || { echo "⤳ skipped: $ROOT is not a Git checkout (a managed install ships none)"; exit 0; }

H="$(mktemp -d)"; H="$(cd "$H" && pwd -P)"
# Cleanup waits for the detached look and any install to finish: deleting under
# a process that is still writing leaves an orphan HOME.
cleanup() { local n=0
  while pgrep -f "$H/" >/dev/null 2>&1 && [ "$n" -lt 60 ]; do sleep 1; n=$((n+1)); done
  rm -rf "$H" 2>/dev/null || true; }
[ -n "${GREYMATTER_TEST_KEEP:-}" ] || trap cleanup EXIT
[ -n "${GREYMATTER_TEST_KEEP:-}" ] && echo "test HOME kept: $H"
export HOME="$H"
unset GREYMATTER_NO_AUTO_UPDATE CBRAIN_NO_AUTO_UPDATE 2>/dev/null || true   # pre-rename

STATE="$H/.greymatter/state"
AVAILABLE="$STATE/update-available"
hook() { python3 "$H/.greymatter/engine/greymatter/check_update.py" 2>&1; }
engine_tag() { basename "$(cd "$H/.greymatter/engine" && pwd -P)"; }
# The look is DETACHED: wait on the file it writes (or removes), never on a delay.
wait_for()  { local n=0; while [ ! -f "$1" ] && [ "$n" -lt 90 ]; do sleep 1; n=$((n + 1)); done; }
wait_gone() { local n=0; while [ -f "$1" ] && [ "$n" -lt 90 ]; do sleep 1; n=$((n + 1)); done; }

echo "▸ local upstream: one old version, one new"
git clone -q "$ROOT" "$H/upstream" && cd "$H/upstream" \
  || { echo "❌ could not enter $H/upstream, stopping before anything runs elsewhere"; exit 1; }
git config user.email greymatter-test
git config user.name greymatter-test
git checkout -q -B main
# The WORKING TREE, not the last commit: the change under test may be uncommitted.
rsync -a --delete --exclude .git --exclude node_modules "$ROOT/" "$H/upstream/"
if [ -n "$SABOTAGE" ]; then
  python3 - "$H/upstream/greymatter/check_update.py" "$SABOTAGE" <<'PY' || exit 2
import sys
p, which = sys.argv[1], sys.argv[2]; s = open(p).read()
old, new = {
    "installs": ("silent = os.path.exists(ON) and not (", "silent = True and not ("),
    "nags": ("ASK_EVERY = 24 * 3600", "ASK_EVERY = 0"),
}[which]
if old not in s: sys.exit("SABOTAGE DID NOT APPLY — the pattern matched nothing")
open(p, "w").write(s.replace(old, new, 1))
PY
  # "installs" has to open BOTH locks: update.sh refuses `--auto` without the
  # opt-in file too, and a sabotage that leaves it shut proves nothing.
  if [ "$SABOTAGE" = "installs" ]; then
    python3 - "$H/upstream/greymatter/update.sh" <<'PY' || exit 2
import sys
p = sys.argv[1]; s = open(p).read()
old = 'if [ ! -e "$AUTO_ON" ] || [ -n'
if old not in s: sys.exit("SABOTAGE DID NOT APPLY — the update.sh gate matched nothing")
open(p, "w").write(s.replace(old, 'if false || [ -n', 1))
PY
  fi
  echo "   SABOTAGE: $SABOTAGE"
fi
git add -A
git diff --cached --quiet || git commit -q -m "test: working tree"
git tag -a v9.9.0 -m "test: old"
echo "new-version-marker" > UPDATE_MARKER
git add UPDATE_MARKER && git commit -q -m "test: new"
git tag -a v9.9.1 -m "test: new"

echo "▸ installing the OLD version (v9.9.0)"
git clone -q "$H/upstream" "$H/engine-src" && cd "$H/engine-src" \
  || { echo "❌ could not enter $H/engine-src"; exit 1; }
git checkout -q v9.9.0
mkdir -p "$H/.claude"
printf '{"model": "opus"}\n' > "$H/.claude/settings.json"
"$H/engine-src/install.sh" --no-launchd --no-capsule --no-shortcut >"$H/install.log" 2>&1 \
  || { echo "❌ install failed:"; tail -20 "$H/install.log"; exit 1; }
export PATH="$H/.local/bin:$PATH"
TRUNK="$H/.greymatter/trunk"
# An update re-runs install.sh without the flags above, so --no-capsule alone
# does not hold: light mode does, or a live pill lands in the real menu bar.
mkdir -p "$TRUNK/state" && touch "$TRUNK/state/no-capsule"
mkdir -p "$TRUNK/lessons"
printf -- "---\nname: mine\ndescription: \"a note of my own\"\n---\nwork I cannot afford to lose\n" \
  > "$TRUNK/lessons/mine.md"
NOTE_SUM="$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)"

echo
echo "▸ 1. session start does NOT block, and says nothing it has not found yet"
T0=$(date +%s); OUT1="$(hook)"; T1=$(date +%s)
[ $((T1 - T0)) -le 5 ]; check $? "the hook returns in $((T1 - T0)) s (≤ 5)"
[ -z "$OUT1" ]; check $? "the first start asks nothing" "got: $OUT1"

echo
echo "▸ 2. the look finds the new version, and installs NOTHING"
wait_for "$AVAILABLE"
grep -q "^v9.9.1" "$AVAILABLE" 2>/dev/null; check $? "the background look recorded v9.9.1"
sleep 3   # a silent install, if one had been launched, would be under way by now
[ "$(engine_tag)" = "v9.9.0" ]; check $? "the engine is still v9.9.0" "got $(engine_tag)"
[ ! -e "$H/.greymatter/engine/UPDATE_MARKER" ] && [ ! -d "$H/.greymatter/versions/v9.9.1" ]
check $? "no new version was built or installed without a yes"

echo
echo "▸ 3. the next start tells the agent to ask"
OUT3="$(hook)"
printf '%s' "$OUT3" | grep -q "GreyMatter v9.9.1 is available"; check $? "it names the new version" "got: $OUT3"
printf '%s' "$OUT3" | grep -q "Ask the user"; check $? "it tells the agent to ask the user"
printf '%s' "$OUT3" | grep -q '`brain update`'; check $? "it names the command a yes runs"

echo
echo "▸ 4. not a nag: the start after that does not ask again"
OUT4="$(hook)"
[ -z "$OUT4" ]; check $? "no second question about v9.9.1 the same day" "got: $OUT4"

echo
echo "▸ 5. a yes installs, and the question stops"
brain update >"$H/update.log" 2>&1; check $? "brain update exits 0" "$(tail -3 "$H/update.log")"
[ "$(engine_tag)" = "v9.9.1" ]; check $? "the engine is on v9.9.1" "got $(engine_tag)"
rm -f "$STATE/update-asked"    # so only "already there" can keep the next start quiet
OUT5="$(hook)"
[ -z "$OUT5" ]; check $? "once on v9.9.1, nothing is asked" "got: $OUT5"
wait_gone "$AVAILABLE"
[ ! -f "$AVAILABLE" ]; check $? "and the next look clears the record"

echo
echo "▸ 6. the user's note never moved"
[ "$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)" = "$NOTE_SUM" ]
check $? "byte-identical"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ session start looks, the agent asks, and nothing installs without a yes"
  exit 0
fi
echo "❌ $FAILS failure(s) on the ask-first path"
exit 1
