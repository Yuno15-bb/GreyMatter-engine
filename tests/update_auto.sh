#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_auto.sh — does the automatic update really do what it says?
#
# WHY THIS EXISTS. Since v1.28.0 session start no longer announces a new
# version: it INSTALLS it, in the background, without being asked. That is
# remote code running on somebody's machine. Three promises carry that decision,
# and an untested promise is only an intention:
#   1. it really APPLIES (otherwise we only removed the notice that worked);
#   2. it NEVER blocks the start of a session;
#   3. if the new version breaks the tool, it comes back on its own — because in
#      automatic mode nobody reads the screen.
#
# ⚠ THIS FILE IS PACKAGE-ONLY and lives in `tests/`, synced with
# `rsync --delete`: it MUST stay in the `sync_dir tests` exclusions. Written
# without the exclusion on 2026-08-16, it was wiped by the very next sync.
#
# Sibling of update_rollback.sh, same local fake upstream, same reason: a test
# that depends on the real GitHub fails for reasons unrelated to the code.
#
# Run: bash tests/update_auto.sh   (macOS: install.sh targets Darwin)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0

check() {  # check <code> <label> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

[ "$(uname)" = "Darwin" ] || { echo "⤳ skipped: install.sh targets macOS"; exit 0; }

H="$(mktemp -d)"
# Cleanup waits for the detached work to finish: deleting under a process that
# is still writing leaves "Directory not empty" and an orphan HOME.
cleanup() { local n=0
  while [ -d "$H/.c-brain/state/auto-update.lock" ] && [ "$n" -lt 60 ]; do sleep 1; n=$((n+1)); done
  rm -rf "$H" 2>/dev/null || true; }
# CBRAIN_TEST_KEEP=1 keeps the test HOME for an autopsy. Without it, diagnosing
# a failure means re-running the harness blind.
[ -n "${CBRAIN_TEST_KEEP:-}" ] || trap cleanup EXIT
[ -n "${CBRAIN_TEST_KEEP:-}" ] && echo "test HOME kept: $H"
export HOME="$H"

# The hook leaves DETACHED: it returns before the work is done. Everything below
# must therefore wait on an observable, never "sleep a bit and hope".
#
# ⚠ AND THE LOCK HAS TO BE AWAITED TWICE. First draft of this harness: waiting
# only for it to DISAPPEAR returned immediately, because the detached process
# had not had time to TAKE it yet. The harness was measuring the state from
# before the update and calling it the result — three red assertions for one
# cause, and none of them pointing at the real one.
# Waiting for it to appear THEN disappear is waiting for a piece of work;
# waiting for absence alone confuses "not started yet" with "already done".
wait_done() {  # wait_done [seconds]
  local n=0 max="${1:-180}" lock="$H/.c-brain/state/auto-update.lock"
  while [ ! -d "$lock" ] && [ "$n" -lt 15 ]; do sleep 1; n=$((n + 1)); done
  n=0
  while [ -d "$lock" ] && [ "$n" -lt "$max" ]; do sleep 1; n=$((n + 1)); done
  sleep 1   # let the report land after the lock is released
}

hook() { python3 "$H/.c-brain/engine/cbrain/check_update.py" 2>&1; }

echo "▸ local upstream: one old version, one new"
git clone -q "$ROOT" "$H/upstream"
cd "$H/upstream"
git config user.email cbrain-test
git config user.name cbrain-test
git checkout -q -B main
# We overlay the WORKING TREE: without this the test exercises the last commit
# instead of the code just written (cf. update_rollback.sh, same trap).
rsync -a --delete --exclude .git --exclude node_modules "$ROOT/" ./
git add -A
git diff --cached --quiet || git commit -q -m "test: working tree"
git tag -a v9.9.0 -m "test: old"

echo "new-version-marker" > UPDATE_MARKER
git add UPDATE_MARKER && git commit -q -m "test: new"
git tag -a v9.9.1 -m "test: new"

# ⚠ LATER VERSIONS ARE CREATED IN THEIR OWN ACT, never here. First draft of this
# harness: all three tags were laid down up front, and the engine clone carried
# them all. `git fetch --tags` does NOT remove a tag that vanished upstream (that
# would take `--prune-tags`), so deleting v9.9.2 upstream did not delete it in
# the engine, which jumped straight to the broken version in act 2. The harness
# was measuring a scenario other than the one it describes.

echo "▸ installing the OLD version (v9.9.0)"
git clone -q "$H/upstream" "$H/engine-src"
cd "$H/engine-src"
git checkout -q v9.9.0
mkdir -p "$H/.claude"
printf '{"model": "opus"}\n' > "$H/.claude/settings.json"
"$H/engine-src/install.sh" --no-launchd --no-capsule --no-shortcut >"$H/install.log" 2>&1 \
  || { echo "❌ install failed:"; tail -20 "$H/install.log"; exit 1; }
export PATH="$H/.local/bin:$PATH"

TRUNK="$H/.c-brain/trunk"
mkdir -p "$TRUNK/lessons"
printf -- "---\nname: mine\ndescription: \"a note of my own\"\n---\nwork I cannot afford to lose\n" \
  > "$TRUNK/lessons/mine.md"
NOTE_SUM="$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)"

echo
echo "▸ 1. session start does NOT block"
T0=$(date +%s)
OUT1="$(hook)"
T1=$(date +%s)
[ $((T1 - T0)) -le 5 ]
check $? "the hook returns in $((T1 - T0)) s (≤ 5)" "a session start was waiting on the network"
[ -z "$OUT1" ]
check $? "it announces nothing on the first pass" "got: $OUT1"

echo
echo "▸ 2. and yet the update REALLY applies, on its own"
wait_done
[ -f "$H/.c-brain/engine/UPDATE_MARKER" ]
check $? "the new version is on disk, without anyone typing anything" \
  "$(tail -5 "$H/.c-brain/state/auto-update.log" 2>/dev/null)"
[ "$(basename "$(cd "$H/.c-brain/engine" && pwd -P)")" = "v9.9.1" ]
check $? "the engine is on v9.9.1"

echo
echo "▸ 3. the report arrives at the NEXT session, and only once"
OUT2="$(hook)"
printf '%s' "$OUT2" | grep -q "v9.9.1"
check $? "the next session announces the installed version" "got: $OUT2"
printf '%s' "$OUT2" | grep -q "itself"
check $? "it says the update was automatic" "got: $OUT2"
wait_done
OUT3="$(hook)"
[ -z "$OUT3" ]
check $? "it does not repeat it the time after" "got: $OUT3"

echo
echo "▸ 4. the switch really switches off"
wait_done
brain update --auto-off >/dev/null 2>&1
( cd "$H/upstream" && echo "even-newer" > OTHER_MARKER \
  && git add OTHER_MARKER && git commit -q -m "test: newer" && git tag -a v9.9.2 -m "test: newer" )
OUT4="$(hook)"
sleep 3
[ ! -f "$H/.c-brain/engine/OTHER_MARKER" ]
check $? "switched off, it installs nothing"
printf '%s' "$OUT4" | grep -q "v9.9.2"
check $? "but it still REPORTS the available version" "got: $OUT4"

echo
echo "▸ 5. a version that breaks the tool is NEVER ACTIVATED"
brain update --auto-on >/dev/null 2>&1
rm -f "$H/.c-brain/state/last-auto-update"
# The BROKEN version: its selftest exits red. That is the only way to prove the
# refusal — faking it with a flag would only prove the flag.
#
# ⚠ WHAT THIS ACT NOW PROVES CHANGED, and for the better (chantier #9). It used
# to assert an automatic ROLLBACK: the updater checked the broken version out
# over the live engine, discovered it was broken, and went back. That works, but
# it means the active engine spends a moment being a version nobody has checked —
# and sessions start in that moment. Versions now live side by side, so the
# candidate is selftested while INACTIVE and simply never becomes the engine.
# There is nothing to roll back from, which is a stronger property than rolling
# back well.
( cd "$H/upstream" \
  && printf '#!/usr/bin/env bash\necho "selftest broken on purpose"\nexit 1\n' > hooks/selftest.sh \
  && git add hooks/selftest.sh && git commit -q -m "test: broken selftest" \
  && git tag -a v9.9.3 -m "test: broken" )
hook >/dev/null
wait_done
[ "$(basename "$(cd "$H/.c-brain/engine" && pwd -P)")" = "v9.9.1" ]
check $? "the engine STAYED on v9.9.1 — the broken version was never activated"
# And the broken candidate must not be left lying about: a half-installed version
# on disk is a rollback target that would break the tool if anyone reached it.
[ ! -d "$H/.c-brain/versions/v9.9.3" ]
check $? "the broken candidate was deleted, not kept beside the good one"
OUT5="$(hook)"
printf '%s' "$OUT5" | grep -qi "was NOT applied"
check $? "and the next session says the update did not happen" "got: $OUT5"
# ⚠ AND IT MUST NOT INVENT A CAUSE. The message used to blame "uncommitted local
# changes" for every blocked update, which was the only possible cause when the
# engine was the user's clone and is now almost never the real one. Sending a
# reader to look for local changes they do not have costs them the evening.
printf '%s' "$OUT5" | grep -qvi "uncommitted local changes"
check $? "and does not blame a cause it has not established" "got: $OUT5"

echo
echo "▸ 6. through all five acts, the user's note never moved"
[ -f "$TRUNK/lessons/mine.md" ]; check $? "the note still exists"
[ "$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)" = "$NOTE_SUM" ]
check $? "byte-identical" "an automatic update rewrote the user's work"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ automatic updates apply, switch off, undo themselves, and touch no note"
  exit 0
fi
echo "❌ $FAILS failure(s) on the automatic path"
exit 1
