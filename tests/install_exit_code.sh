#!/usr/bin/env bash
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# install_exit_code.sh — a red selftest has to reach whoever ran the installer.
#
# WHY THIS EXISTS. install.sh runs the selftest at the end and printed its
# verdict — and then exited 0 whatever that verdict was. A person reading the
# screen could see the red; a script, a CI job or an agent running the installer
# could not: it read success. And the screen itself could hide it: the closing
# verdict was an if/elif, so a bare PATH — the usual case on a new Mac — printed
# the PATH advice and never got to the failed verification. Both found on a
# blank Mac on 2026-09-26.
#
# The bench installs for real, from a clone, in throwaway HOMEs. It makes the
# selftest fail the honest way — a pill build left in the shared runtime that no
# longer runs (an interrupted build, a cleaner that truncated it), which is a
# thing a machine can have — and never by editing the product. Until 2.2 the
# broken thing was a Node on PATH that could not parse the Electron capsule; the
# selftest no longer calls Node, so that case turned green and this bench red.
# The case needs Swift: without it the installer skips the pill, the selftest
# skips its check, and there is nothing honest left to break — it says so.
#
# The same goes for a failure before the selftest. The update mirror could not
# be created and the installer ended with no word at all: under `set -e` a bare
# failing call exits on the spot. Seen in CI on 2026-09-29, where the log stopped
# at "engine built". The bench takes the mirror's path with a plain file, which a
# machine can have, and reads what the screen says.
#
# Run: bash tests/install_exit_code.sh [--sabotage exit-zero|path-hides-selftest|mirror-silent]
#   exit-zero           — the installer exits 0 again after a red selftest; must go RED.
#   path-hides-selftest — the PATH advice hides the failed verification again; must go RED.
#   mirror-silent       — a failed mirror ends the install without a word again; must go RED.
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

# install.sh builds the engine from the source's COMMITTED tree, so the bench
# installs from a clone: a sabotage has to be a commit to be what gets run.
SRC="$H/src"
git clone -q "$ROOT" "$SRC" || { echo "  ❌ could not clone $ROOT"; exit 1; }
sabotage() {  # sabotage <name> <python replace: old> <new>
  python3 - "$SRC/install.sh" "$2" "$3" <<'SAB' || { echo "  ❌ sabotage $1 did not apply"; exit 1; }
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path).read()
if src.count(old) != 1:
    sys.exit(1)
open(path, "w").write(src.replace(old, new))
SAB
  git -C "$SRC" -c user.name=bench -c user.email=bench@localhost \
    commit -qam "sabotage: $1" || { echo "  ❌ sabotage commit failed"; exit 1; }
  echo "  ⚠ sabotage $1 applied"
}
case "$SABOTAGE" in
  "") ;;
  exit-zero)
    sabotage exit-zero '[ "${SELFTEST_OK:-1}" = "1" ] || exit 1' ':' ;;
  path-hides-selftest)
    sabotage path-hides-selftest 'if [ "${SELFTEST_OK:-1}" = "0" ]; then' \
      'if [ "${SELFTEST_OK:-1}" = "0" ] && [ "${PATH_OK:-1}" = "1" ]; then' ;;
  mirror-silent)
    sabotage mirror-silent 'mirror_source "$SOURCE" "$MIRROR" || die "could not create the update mirror $MIRROR"' \
      'mirror_source "$SOURCE" "$MIRROR"' ;;
  *) echo "unknown sabotage: $SABOTAGE"; exit 2 ;;
esac

# seed_broken_pill <home>: the build install.sh would reuse for these sources
# (same key, see capsule_dir), already there and unable to answer --check.
seed_broken_pill() {
  local rt
  rt="$(source "$SRC/greymatter/engine-lib.sh" && capsule_dir "$SRC" "$1/.greymatter/runtime")" || return 1
  mkdir -p "$rt/release"
  printf '#!/bin/sh\necho "Capsule: broken on purpose" >&2\nexit 1\n' > "$rt/release/Capsule"
  chmod +x "$rt/release/Capsule"
}

N=0
install_in() {  # install_in <1 if a broken pill waits> <1 if ~/.local/bin on PATH> [1 if the mirror's path is taken] → sets OUT, RC
  N=$((N + 1)); local home="$H/home-$N" p="$APPLE_PATH" mode=(--core-only)
  mkdir -p "$home"
  [ "${3:-0}" = "1" ] && { mkdir -p "$home/.greymatter" && : > "$home/.greymatter/source.git"; }
  [ "$2" = "1" ] && p="$home/.local/bin:$p"
  # --core-only: no launchd job, no capsule, no planet — a bench registers nothing
  # on the machine running it. The broken case keeps the capsule step so the
  # selftest meets the pill; the installer starts it once, it exits at once.
  # stdin is not a terminal, so it asks nothing.
  if [ "$1" = "1" ]; then
    seed_broken_pill "$home" || { echo "  ❌ could not seed the broken pill"; exit 1; }
    mode=(--no-launchd --no-planet)
  fi
  OUT="$(cd "$SRC" && env -i HOME="$home" USER="${USER:-tester}" LANG=en_US.UTF-8 \
           TERM=dumb PATH="$p" ./install.sh "${mode[@]}" </dev/null 2>&1)"
  RC=$?
  LAST="$(printf '%s' "$OUT" | tail -40)"
}
# Read from a variable, never from `tail | grep -q`: under pipefail, grep -q
# exits at the first match, tail can still be writing, takes a SIGPIPE, and a
# true line reads as absent. Measured on 2026-09-26: 15 false reds in 3000.
last_screen_has() { grep -q "$1" <<<"$LAST"; }

echo "▸ the update mirror cannot be created (its path is taken by a file)"
install_in 0 1 1
[ "$RC" -ne 0 ]; check $? "the installer exits non-zero" "exit code $RC"
last_screen_has "could not create the update mirror"
check $? "the screen says what failed" "last line: $(tail -1 <<<"$LAST")"
grep -q "already exists" <<<"$OUT"
check $? "and git's own reason is shown, not thrown away"

if ! { PATH="$APPLE_PATH" command -v swift >/dev/null 2>&1 && xcode-select -p >/dev/null 2>&1; }; then
  echo "Install exit code — selftest cases skipped (no Swift: the pill, the only honest way to fail the selftest from outside, is not built here)"
  [ "$FAILS" -eq 0 ] || { echo "❌ $FAILS check(s) failed"; exit 1; }
  exit 0
fi

echo "▸ the selftest fails, ~/.local/bin on PATH"
install_in 1 1
printf '%s' "$OUT" | grep -q "selftest failed"
check $? "the selftest really is red (the bench is aimed at the right case)"
[ "$RC" -ne 0 ]; check $? "the installer exits non-zero" "exit code $RC"
last_screen_has "own verification did not pass"
check $? "the last screen names the failed verification"
last_screen_has "✅ GreyMatter installed."
[ $? -ne 0 ]; check $? "it does not claim a clean install"

echo "▸ the selftest fails AND ~/.local/bin is not on PATH (a new Mac)"
install_in 1 0
[ "$RC" -ne 0 ]; check $? "the installer exits non-zero" "exit code $RC"
last_screen_has "not reachable yet"
check $? "the last screen still gives the PATH advice"
last_screen_has "own verification did not pass"
check $? "and the PATH advice no longer hides the failed verification"

echo "▸ control: a healthy install, PATH or not"
install_in 0 1
[ "$RC" -eq 0 ]; check $? "a green selftest exits 0" "exit code $RC — $(grep -E '❌|failed' <<<"$LAST" | head -2 | tr '\n' ' ')"
last_screen_has "✅ GreyMatter installed."
check $? "and says so plainly"
install_in 0 0
[ "$RC" -eq 0 ]; check $? "a PATH still to fix is a working install: exit 0" "exit code $RC"

if [ "$FAILS" -eq 0 ]; then
  echo "✅ a red selftest reaches the screen AND the exit code; a green one reaches neither as red"
  exit 0
fi
echo "❌ $FAILS check(s) failed"
exit 1
