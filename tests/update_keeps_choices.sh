#!/usr/bin/env bash
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_keeps_choices.sh — what a user declined at install stays declined,
# through an update, a rollback, and the update after it.
#
# WHY THIS EXISTS. Every updater up to v2.1.1 ends by replaying the installer
# with no option at all, so each update put back the scheduled jobs, the Desktop
# app, the shortcut and the pill a user had turned down with --no-launchd,
# --no-planet, --no-shortcut or --no-capsule. Those updaters are already on
# users' disks: the fix has to live in the installer they replay, which reads the
# choices from the disk when it finds no record of them. The rollback runs the
# OLD installer, which knows nothing of a record, so the updater must hand it the
# choices as flags.
#
# The old release is the tag v2.1.1, read from this repository's own history.
# launchd is a text file (tests/_fake_launchd.py): $HOME does not isolate the real
# domain. npm is kept off PATH, so v2.1.1 has no Electron orb; light mode
# (state/no-capsule) is set before anything runs, so no pill can reach the real
# menu bar even if a sabotage builds one.
#
# Usage: bash tests/update_keeps_choices.sh [--sabotage <name>]
#   replay-ignores-record   the replay installs every piece again
#   rollback-without-flags  the rollback runs the old installer bare
#   orb-survives            the Electron orb outlives the update in light mode
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
OLD_TAG=v2.1.1
FAILS=0
SABOTAGES="replay-ignores-record rollback-without-flags orb-survives"
SABOTAGE=""
[ "${1:-}" = "--sabotage" ] && SABOTAGE="${2:-}"
if [ -n "$SABOTAGE" ]; then
  case " $SABOTAGES " in
    *" $SABOTAGE "*) : ;;
    *) echo "❌ unknown sabotage: $SABOTAGE (known: $SABOTAGES)"; exit 2 ;;
  esac
fi

check() {  # check <exit-code> <label> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

[ "$(uname)" = "Darwin" ] || { echo "⤳ skipped: install.sh targets macOS"; exit 0; }
git -C "$ROOT" rev-parse -q --verify "refs/tags/$OLD_TAG" >/dev/null \
  || { echo "⤳ skipped: tag $OLD_TAG absent (shallow clone?)"; exit 0; }
[ "$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" = "$ROOT" ] \
  || { echo "⤳ skipped: $ROOT is not a Git checkout (a managed install ships none)"; exit 0; }

H="$(mktemp -d)"
H="$(cd "$H" && pwd -P)"
ORB_PID=""
trap '[ -n "$ORB_PID" ] && kill "$ORB_PID" 2>/dev/null; rm -rf "$H"' EXIT
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
git clone -q "$ROOT" "$H/upstream" && cd "$H/upstream" \
  || { echo "❌ could not enter $H/upstream, stopping before anything runs elsewhere"; exit 1; }
git config user.email greymatter-test
git config user.name greymatter-test
git checkout -q -B main "$OLD_TAG"
git tag -a v9.8.0 -m "test: before the record" 2>/dev/null || { echo "❌ v9.8.0 already exists"; exit 1; }
rsync -a --delete --exclude .git --exclude node_modules "$ROOT/" "$H/upstream/"

# A sabotage goes into the version under test before it is committed: patched
# afterwards, it would never reach the engine the updater builds from the tag.
sabotage_patch() {   # sabotage_patch <file> <old> <new>
  python3 - "$1" "$2" "$3" <<'PY' || exit 1
import sys
path, old, new = sys.argv[1:]
s = open(path).read()
if old not in s:
    sys.exit("SABOTAGE DID NOT APPLY to %s — the pattern matched nothing" % path)
open(path, "w").write(s.replace(old, new, 1))
PY
  echo "   SABOTAGE: $SABOTAGE"
}
case "$SABOTAGE" in
  replay-ignores-record)
    sabotage_patch install.sh 'if [ "$CHOSEN_BY_HAND" = "0" ]; then' 'if false; then' ;;
  rollback-without-flags)
    sabotage_patch greymatter/update.sh 'install.sh" $(choices_flags) >' 'install.sh" >' ;;
  orb-survives)
    sabotage_patch install.sh 'pkill -f "$orb_trunk/capsule/node_modules/electron"' ': "$orb_trunk"' ;;
esac

git add -A
git commit -q -m "test: working tree" || { echo "❌ nothing differs from $OLD_TAG"; exit 1; }
git tag -a v9.9.0 -m "test: the record"

GM="$H/.greymatter"
engine_tag() { basename "$(cd "$GM/engine" 2>/dev/null && pwd -P)"; }
registered() { awk -F'\t' '{ print $1 }' "$FAKE_REG" | sort | tr '\n' ' '; }

# ─── A v2.1.1 user who turned three pieces down ─────────────────────────────
echo "▸ installing $OLD_TAG with --no-launchd --no-planet --no-capsule (the shortcut is kept)"
git clone -q "$H/upstream" "$H/engine-src"
git -C "$H/engine-src" checkout -q v9.8.0
mkdir -p "$H/.claude" "$H/Desktop"
( cd "$H/engine-src" && ./install.sh --no-launchd --no-planet --no-capsule ) >"$H/install.log" 2>&1 \
  || { echo "❌ old install failed:"; tail -20 "$H/install.log"; exit 1; }
TRUNK="$(cd "$GM/trunk" && pwd -P)"
# Light mode before any replay: whatever a sabotage builds, it never starts.
mkdir -p "$TRUNK/state" && touch "$TRUNK/state/no-capsule"
[ ! -e "$GM/state/install-choices" ]; check $? "the old release wrote no record (the case the disk reading exists for)"

assert_declined() {  # assert_declined <moment>
  local plists
  plists="$(ls "$H/Library/LaunchAgents" 2>/dev/null | grep -i greymatter | tr '\n' ' ')"
  [ -z "$plists" ]; check $? "$1: no LaunchAgent plist" "$plists"
  case "$(registered)" in *com.greymatter.*) r=1 ;; *) r=0 ;; esac
  check $r "$1: no scheduled job registered" "$(registered)"
  [ ! -e "$H/Desktop/GreyMatter.app" ]; check $? "$1: no Desktop app"
  [ -L "$H/GreyMatter" ]; check $? "$1: the Home shortcut, which was accepted, is still there"
}
assert_record() {    # assert_record <moment>
  local want got
  want="$(printf 'launchd=0\ncapsule=0\nplanet=0\nshortcut=1')"
  got="$(cat "$GM/state/install-choices" 2>/dev/null)"
  [ "$got" = "$want" ]; check $? "$1: the record holds the three refusals and the one yes" "$(echo "$got" | tr '\n' ' ')"
}
assert_declined "after the $OLD_TAG install"

# A v2.1.x orb, running when the update comes: named like the real one, so the
# installer's pattern matches it, and nothing else on this Mac can.
( exec -a "$TRUNK/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" sleep 600 ) &
ORB_PID=$!
disown "$ORB_PID" 2>/dev/null || true   # its death is checked below, not announced
sleep 0.3

echo "▸ the OLD updater brings in the release under test"
brain update >"$H/update.log" 2>&1; check $? "brain update exits 0" "$(tail -3 "$H/update.log")"
[ "$(engine_tag)" = "v9.9.0" ]; check $? "the engine is the new tag" "got $(engine_tag)"
assert_declined "after the update"
assert_record "after the update"
ls "$GM"/runtime/capsule-native-*/release/Capsule >/dev/null 2>&1
[ $? -ne 0 ]; check $? "after the update: the declined pill was not built"
if kill -0 "$ORB_PID" 2>/dev/null; then r=1; else r=0; ORB_PID=""; fi
check $r "after the update: the Electron orb is gone, light mode or not"
# What the user reads on asking for the pill. Only while none is built: an
# explicit `brain capsule` starts a built pill, light mode or not.
if ! ls "$GM"/runtime/capsule-native-*/release/Capsule >/dev/null 2>&1; then
  brain capsule >"$H/capsule.log" 2>&1
  grep -q 'install choices mark it as declined' "$H/capsule.log" && grep -q 'delete that file first' "$H/capsule.log"
  check $? "brain capsule says the pill was declined, and how to add it" "$(head -2 "$H/capsule.log")"
fi

echo "▸ rolling back: the NEW updater runs the OLD installer"
brain update --rollback >"$H/rollback.log" 2>&1
check $? "brain update --rollback exits 0" "$(tail -3 "$H/rollback.log")"
[ "$(engine_tag)" = "v9.8.0" ]; check $? "the engine is the old tag again" "got $(engine_tag)"
assert_declined "after the rollback"

echo "▸ and forward again, now with a record"
brain update >"$H/update2.log" 2>&1; check $? "the second update exits 0" "$(tail -3 "$H/update2.log")"
[ "$(engine_tag)" = "v9.9.0" ]; check $? "the engine is the new tag" "got $(engine_tag)"
assert_declined "after the second update"
assert_record "after the second update"

echo "▸ the documented repair: ./install.sh again, by hand, with no option"
( cd "$H/engine-src" && git checkout -q v9.9.0 && ./install.sh ) >"$H/rerun.log" 2>&1
check $? "the re-run exits 0" "$(tail -3 "$H/rerun.log")"
assert_declined "after a re-run by hand"
grep -q 'install choices kept from the last install' "$H/rerun.log"
check $? "the re-run says which choices it kept"

echo "▸ an option given by hand replaces the record"
( cd "$H/engine-src" && ./install.sh --no-launchd --no-planet --no-capsule --no-shortcut ) >"$H/rerun2.log" 2>&1
check $? "the re-run with options exits 0" "$(tail -3 "$H/rerun2.log")"
grep -qx 'shortcut=0' "$GM/state/install-choices"; check $? "the record now declines the shortcut too"

# The other half of reading the disk: a piece that IS there counts as chosen.
# An orb's folder, and a dry run, which neither writes the record nor starts anything.
echo "▸ with no record, a piece found on this Mac counts as chosen"
rm -f "$GM/state/install-choices"
mkdir -p "$GM/runtime/capsule-test/node_modules/electron/dist/Electron.app"
bash "$GM/versions/v9.9.0/install.sh" --dry-run >"$H/infer.log" 2>&1
line="$(grep 'install choices read from this Mac' "$H/infer.log")"
[ -n "$line" ]; check $? "a replay with no record reads the choices from this Mac"
case "$line" in *--no-capsule*) r=1 ;; *) r=0 ;; esac
check $r "an orb on disk counts as the pill chosen" "$line"
[ ! -e "$GM/state/install-choices" ]; check $? "a dry run writes no record"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ what was declined at install stays declined: update, rollback, update, re-run"
  exit 0
fi
echo "❌ $FAILS failure(s): a piece declined at install came back, or outlived the update"
exit 1
