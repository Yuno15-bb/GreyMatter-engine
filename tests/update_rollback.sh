#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_rollback.sh — an update that cannot be undone is not an update.
#
# WHY THIS EXISTS. `brain update` swaps out the engine, runs migrations and
# replays the installer, on a machine where the user keeps notes they cannot
# afford to lose. Everything about that is testable and none of it was tested:
# the CI proved the FIRST install works, never the second one, and never the
# way back.
#
# It runs against a LOCAL fake upstream, not GitHub. A test that depends on the
# real remote fails when a tag moves or the network hiccups, and a test that
# fails for reasons unrelated to the code is a test people learn to ignore.
#
# The two things it must prove, in order of how much they cost when wrong:
#   1. the user's notes survive an update AND a rollback — a memory tool that
#      loses memory during a version change has no reason to exist;
#   2. the engine actually moves, and actually comes back.
#
# Run: bash tests/update_rollback.sh          (macOS: install.sh targets Darwin)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0

check() {  # check <label> <condition-as-exit-code> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

[ "$(uname)" = "Darwin" ] || { echo "⤳ skipped: install.sh targets macOS"; exit 0; }

H="$(mktemp -d)"
trap 'rm -rf "$H"' EXIT
export HOME="$H"

echo "▸ building a local upstream with two versions"
git clone -q "$ROOT" "$H/upstream"
cd "$H/upstream"
git config user.email cbrain-test
git config user.name cbrain-test
git checkout -q -B main

# ⚠ Overlay the WORKING TREE on top of the clone. `git clone` copies committed
# history, so without this the test silently exercises the last commit instead
# of the code on disk — which it did, and it is how this line came to exist: a
# mutation deliberately introduced into update.sh left the suite fully green.
# A test that reads different code than the one being changed proves nothing.
rsync -a --delete --exclude .git --exclude node_modules "$ROOT/" ./
git add -A
git diff --cached --quiet || git commit -q -m "test: working tree"

# The OLD version is whatever the working tree is. The NEW one adds a marker we
# can look for — proof the engine really moved, rather than reporting that it did.
git tag -a v9.9.0 -m "test: old" 2>/dev/null || { echo "❌ v9.9.0 already exists"; exit 1; }
echo "new-version-marker" > UPDATE_MARKER
git add UPDATE_MARKER && git commit -q -m "test: new"
git tag -a v9.9.1 -m "test: new"

echo "▸ installing the OLD version"
git clone -q "$H/upstream" "$H/engine-src"
cd "$H/engine-src"
git checkout -q v9.9.0
mkdir -p "$H/.claude"
printf '{"model": "opus"}\n' > "$H/.claude/settings.json"
"$H/engine-src/install.sh" --no-launchd --no-capsule --no-shortcut >"$H/install.log" 2>&1 \
  || { echo "❌ install failed:"; tail -20 "$H/install.log"; exit 1; }
export PATH="$H/.local/bin:$PATH"

TRUNK="$H/.c-brain/trunk"
# A note the user wrote. It must be untouched at every step below.
mkdir -p "$TRUNK/lessons"
printf -- "---\nname: mine\ndescription: \"my own note\"\n---\nwork I cannot lose\n" \
  > "$TRUNK/lessons/mine.md"
NOTE_SUM="$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)"

[ "$(brain version 2>/dev/null | tr -d '[:space:]')" ] || true
echo "  installed: $(basename "$(cd "$H/.c-brain/engine" && pwd -P)")"

echo "▸ brain update --check reports the newer version without applying it"
brain update --check >"$H/check.log" 2>&1; rc=$?
grep -q "v9.9.1" "$H/check.log"; check $? "--check names the new version" "$(tail -2 "$H/check.log")"
[ "$rc" = "10" ]; check $? "--check exits 10 (an update exists)" "got $rc"
[ ! -f "$H/.c-brain/engine/UPDATE_MARKER" ]; check $? "--check applied nothing"

# WHERE FROM, exactly. An update runs code on this machine; naming a version is
# not naming a source. Both lines are asserted because a disclosure nobody
# checks is one a refactor deletes in silence — it breaks nothing when it goes.
grep -q "from:.*upstream" "$H/check.log"
check $? "--check says which remote the code would come from" "$(tail -4 "$H/check.log")"
grep -qE "commit: [0-9a-f]{7,}" "$H/check.log"
check $? "--check names the exact commit it would move to" "$(tail -4 "$H/check.log")"

echo "▸ brain update moves the engine"
brain update >"$H/update.log" 2>&1 || { echo "❌ update failed:"; tail -20 "$H/update.log"; FAILS=$((FAILS+1)); }
[ -f "$H/.c-brain/engine/UPDATE_MARKER" ]; check $? "the new version is really on disk" "$(tail -3 "$H/update.log")"
[ "$(basename "$(cd "$H/.c-brain/engine" && pwd -P)")" = "v9.9.1" ]
check $? "the engine reports the new tag"
[ "$(cat "$H/.c-brain/state/previous-version" 2>/dev/null)" = "v9.9.0" ]
check $? "the previous version was recorded" "rollback would have nowhere to go"

echo "▸ brain update --rollback puts it back"
brain update --rollback >"$H/rollback.log" 2>&1 || { echo "❌ rollback failed:"; tail -20 "$H/rollback.log"; FAILS=$((FAILS+1)); }
[ ! -f "$H/.c-brain/engine/UPDATE_MARKER" ]; check $? "the new version is gone from disk"
[ "$(basename "$(cd "$H/.c-brain/engine" && pwd -P)")" = "v9.9.0" ]
check $? "the engine is back on the old tag"

echo "▸ and through all of it, the notes never moved"
[ -f "$TRUNK/lessons/mine.md" ]; check $? "the note still exists"
[ "$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)" = "$NOTE_SUM" ]
check $? "the note is byte-identical" "an update or a rollback rewrote the user's work"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ update and rollback both work, and neither touches a note"
  exit 0
fi
echo "❌ $FAILS failure(s) in the update/rollback path"
exit 1
