#!/usr/bin/env bash
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_across_rename.sh — the last release under the old name, updated by its
# OWN updater to this tree, then rolled back, then updated again.
#
# WHY THIS EXISTS. v2.1.0 renames the root, the launchd jobs, the hooks, the
# Desktop app and the Home shortcut. The code that performs that update is not
# ours to change: it is the v2.0.x updater already on the user's disk. It builds
# the candidate with its own library, runs migrations from the old folder only,
# and replays our installer. Every one of those steps can leave a machine with
# two roots, doubled hooks or orphaned jobs, and no unit test sees it — only the
# real sequence does.
#
# The old release is the tag v2.0.4, read from this repository's own history.
# launchd is a text file (tests/_fake_launchd.py): $HOME does not isolate the
# real domain. npm is kept off PATH, so the capsule is skipped as on a Mac
# without Node.
#
# Run: bash tests/update_across_rename.sh          (macOS: install.sh targets Darwin)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
OLD_TAG=v2.0.4
FAILS=0

check() {  # check <exit-code> <label> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

[ "$(uname)" = "Darwin" ] || { echo "⤳ skipped: install.sh targets macOS"; exit 0; }
git -C "$ROOT" rev-parse -q --verify "refs/tags/$OLD_TAG" >/dev/null \
  || { echo "⤳ skipped: tag $OLD_TAG absent (shallow clone?)"; exit 0; }

H="$(mktemp -d)"
H="$(cd "$H" && pwd -P)"
trap 'rm -rf "$H"' EXIT
export HOME="$H"
unset GREYMATTER_NO_AUTO_UPDATE CBRAIN_NO_AUTO_UPDATE 2>/dev/null || true   # pre-rename

# ─── The fake launchd, node without npm, nothing from the host's PATH ───────
mkdir -p "$H/bin"
python3 -c "import sys; sys.path.insert(0, '$ROOT/tests'); import _fake_launchd as f; print(f.FAKE, end='')" \
  > "$H/bin/launchctl"
chmod +x "$H/bin/launchctl"
export FAKE_REG="$H/launchd-registry" FAKE_LOG="$H/launchd.log"
: > "$FAKE_REG"
NODE="$(command -v node || true)"
[ -n "$NODE" ] && ln -s "$NODE" "$H/bin/node"
export PATH="$H/.local/bin:$H/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# ─── A local upstream: the old tag, then this working tree on top ───────────
echo "▸ building a local upstream: $OLD_TAG, then this working tree"
# ⚠ Every step below runs from a `cd`. If the clone fails, the `cd` fails too,
# and without `set -e` the rest ran in the CALLER's directory: `git commit`,
# `git tag`, then `rsync --delete` emptied it (issue #3, a managed install has no
# .git). So: no checkout of its own, no test; and a failed `cd` stops everything.
[ "$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" = "$ROOT" ] \
  || { echo "⤳ skipped: $ROOT is not a Git checkout (a managed install ships none)"; exit 0; }
git clone -q "$ROOT" "$H/upstream" && cd "$H/upstream" \
  || { echo "❌ could not enter $H/upstream, stopping before anything runs elsewhere"; exit 1; }
git config user.email greymatter-test
git config user.name greymatter-test
git checkout -q -B main "$OLD_TAG"
git tag -a v9.8.0 -m "test: old name" 2>/dev/null || { echo "❌ v9.8.0 already exists"; exit 1; }
# Overlay the WORKING TREE, as update_rollback.sh does and for the same reason:
# a clone copies commits, and the change under test is not committed yet.
rsync -a --delete --exclude .git --exclude node_modules "$ROOT/" "$H/upstream/"
git add -A
git commit -q -m "test: working tree" || { echo "❌ nothing differs from $OLD_TAG"; exit 1; }
git tag -a v9.9.0 -m "test: new name"

OLD="$H/.c-brain"        # pre-rename
NEW="$H/.greymatter"
SETTINGS="$H/.claude/settings.json"

hooks_report() {  # prints: <total> <distinct> <with-old-root> <with-new-root>
  python3 - "$SETTINGS" <<'PY'
import json, sys
cmds = [h.get("command", "") for evs in json.load(open(sys.argv[1])).get("hooks", {}).values()
        for grp in evs for h in grp.get("hooks", [])]
print(len(cmds), len(set(cmds)), sum("/.c-brain/" in c for c in cmds),
      sum("/.greymatter/" in c for c in cmds))
PY
}
registered() { awk -F'\t' '{ print $1 }' "$FAKE_REG" | sort | tr '\n' ' '; }
engine_tag() { basename "$(cd "$NEW/engine" 2>/dev/null && pwd -P)"; }

echo "▸ installing $OLD_TAG, as a v2.0.x user has it"
git clone -q "$H/upstream" "$H/engine-src"
git -C "$H/engine-src" checkout -q v9.8.0
mkdir -p "$H/.claude" "$H/Desktop"
printf '{"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}\n' \
  > "$SETTINGS"
( cd "$H/engine-src" && ./install.sh ) >"$H/install.log" 2>&1 \
  || { echo "❌ old install failed:"; tail -20 "$H/install.log"; exit 1; }
[ -d "$OLD" ] && [ ! -L "$OLD" ]; check $? "the old install has its root at the old name"
[ -L "$H/C Brain" ]; check $? "…its Home shortcut"                         # pre-rename
[ -d "$H/Desktop/C Brain Planet.app" ]; check $? "…its Desktop app"         # pre-rename
case "$(registered)" in *com.claudebrain.resume*) r=0 ;; *) r=1 ;; esac      # pre-rename
check $r "…and its launchd jobs" "$(registered)"

TRUNK="$OLD/trunk"
mkdir -p "$TRUNK/lessons"
printf -- "---\nname: mine\ndescription: \"my own note\"\n---\nwork I cannot lose\n" \
  > "$TRUNK/lessons/mine.md"
NOTE_SUM="$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)"

assert_new_name() {  # the state a v2.1.0 machine must be in
  [ -d "$NEW" ] && [ ! -L "$NEW" ]; check $? "the root is ~/.greymatter"
  [ -L "$OLD" ] && [ "$(cd "$OLD" && pwd -P)" = "$NEW" ]
  check $? "the old path is a link to it"
  [ "$(engine_tag)" = "v9.9.0" ]; check $? "the engine is the new tag" "got $(engine_tag)"
  read -r total distinct old new <<<"$(hooks_report)"
  [ "$old" = 0 ] && [ "$new" -gt 0 ]; check $? "every hook uses the new root" "old=$old new=$new"
  [ "$total" = "$distinct" ]; check $? "no hook is registered twice" "total=$total distinct=$distinct"
  grep -q '"echo mine"' "$SETTINGS"; check $? "the user's own hook is kept"
  case "$(registered)" in *com.claudebrain.*) r=1 ;; *) r=0 ;; esac          # pre-rename
  check $r "no launchd job keeps the old label" "$(registered)"
  case "$(registered)" in *com.greymatter.resume*) r=0 ;; *) r=1 ;; esac
  check $r "the jobs run under the new label" "$(registered)"
  [ ! -e "$H/C Brain" ]; check $? "the old Home shortcut is gone"             # pre-rename
  [ -L "$H/GreyMatter" ]; check $? "the new Home shortcut exists"
  [ ! -e "$H/Desktop/C Brain Planet.app" ]; check $? "the old Desktop app is gone"  # pre-rename
  [ -d "$H/Desktop/GreyMatter.app" ]; check $? "the new Desktop app exists"
  [ "$(shasum -a 256 "$NEW/trunk/lessons/mine.md" | cut -d' ' -f1)" = "$NOTE_SUM" ]
  check $? "the user's note is byte-identical"
}

echo "▸ the OLD updater brings in the renamed release"
brain update >"$H/update.log" 2>&1; check $? "brain update exits 0" "$(tail -3 "$H/update.log")"
assert_new_name

echo "▸ rolling back across the rename"
brain update --rollback >"$H/rollback.log" 2>&1
check $? "brain update --rollback exits 0" "$(tail -3 "$H/rollback.log")"
[ "$(engine_tag)" = "v9.8.0" ]; check $? "the engine is the old tag again" "got $(engine_tag)"
read -r total distinct old new <<<"$(hooks_report)"
[ "$new" = 0 ] && [ "$old" -gt 0 ]; check $? "the hooks are the old release's, only" "old=$old new=$new"
[ "$total" = "$distinct" ]; check $? "no hook is registered twice" "total=$total distinct=$distinct"
case "$(registered)" in *com.greymatter.*) r=1 ;; *) r=0 ;; esac
check $r "no new-label job is left running under the old engine" "$(registered)"
[ -L "$OLD" ] && [ -d "$OLD/trunk/lessons" ]; check $? "the old engine still reaches the trunk"

echo "▸ and forward again"
brain update >"$H/update2.log" 2>&1; check $? "the second update exits 0" "$(tail -3 "$H/update2.log")"
assert_new_name

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ a $OLD_TAG install crosses the rename, both ways, with one of everything"
  exit 0
fi
echo "❌ $FAILS failure(s) across the rename"
exit 1
