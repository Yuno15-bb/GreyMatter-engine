#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_tag_family.sh — the update path must never change the user's language.
#
# WHY THIS TEST EXISTS. Tags are not scoped to a branch, so `git tag -l 'v*'`
# returns the English and French families at once — and `sort -V` places
# `v1.18.0-fr` AFTER `v1.18.0`. Taking the global maximum moved an ENGLISH
# installation onto the FRENCH tree the moment the French branch caught up,
# with no error whatsoever: the tag exists, the checkout succeeds, and the user
# simply finds their tool speaking another language.
#
# It stayed invisible for as long as `fr` lagged behind. That is exactly the
# kind of bug a test has to hold down, because nothing else will report it.
#
# The test builds a throwaway repository with the real topology — two branches
# that diverge, each carrying its own tag family — and asserts that an install
# of each family is offered its OWN newest version.
#
# Run: bash tests/update_tag_family.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

git init -q -b main "$T/engine"
cd "$T/engine"
# NOT a plausible-looking address: leakcheck scans this repository for e-mail
# patterns, and a placeholder that matches one turns the guard red on a file
# that leaks nothing. git accepts any string here.
git config user.email cbrain-test
git config user.name cbrain-test

echo base > f && git add f && git commit -qm base
git checkout -q -b fr && echo fr1 > f && git commit -qam fr1 && git tag -a v1.17.0-fr -m x
git checkout -q main && echo en1 > f && git commit -qam en1 && git tag -a v1.17.0 -m x
echo en2 > f && git commit -qam en2 && git tag -a v1.18.0 -m x
git checkout -q fr && echo fr2 > f && git commit -qam fr2 && git tag -a v1.18.0-fr -m x

# The bug, demonstrated: the global maximum is the FRENCH tag.
naive="$(git tag -l 'v*' | sort -V | tail -1)"
[ "$naive" = "v1.18.0-fr" ] || {
  echo "⚠️  the premise no longer holds: global max is '$naive', not v1.18.0-fr"
}

# Load the real functions from update.sh rather than re-implementing them —
# a copy in the test would keep passing after the shipped code was broken.
# ⚠ THE ENGINE IS NO LONGER A REPOSITORY (2026-08-17, chantier #9). Tags now live
# in the installer's own mirror, and the installed version is a DIRECTORY whose
# NAME carries the family — `v1.18.0`, `v1.18.0-fr`, `v1.28.1-24-g6f28312`. So
# the harness names a version instead of checking one out, and points the tag
# lookup at the mirror. The property under test is unchanged: an English
# installation is never offered the French tree, and vice versa.
MIRROR="$T/engine"          # the repository that holds the published tags
VERSIONS="$T/versions"
mkdir -p "$VERSIONS"
# STATE and FAMILY_FILE are pulled in too: `family()` reads the recorded family
# BEFORE deriving one, and a harness that omitted it would test a version of the
# function the shipped script never runs — the exact copy-drift this eval avoids.
# `current()` comes along because `family()` calls it: extracting only the two
# functions under test would leave the third to the harness, and a
# re-implemented `current()` is precisely the drift this avoids.
STATE="$T/state"
mkdir -p "$STATE"
eval "$(sed -n '/^FAMILY_FILE=/p;/^current() {/,/^}/p;/^family() {/,/^}/p;/^latest_tag() {/,/^}/p' "$ROOT/cbrain/update.sh")"

check() {  # check <label> <installed-version-name> <expected>
  ENGINE="$VERSIONS/$2"
  mkdir -p "$ENGINE"
  local got; got="$(latest_tag)"
  if [ "$got" = "$3" ]; then
    echo "  ✅ $1 → $got"
  else
    echo "  ❌ $1 → got '$got', expected '$3'"
    FAILS=$((FAILS + 1))
  fi
}

echo "▸ each installation is offered its own family"
check "English install (v1.17.0)"      v1.17.0            v1.18.0
check "French install (v1.17.0-fr)"    v1.17.0-fr         v1.18.0-fr
# A plain clone of a branch installs a `git describe` name, not a bare tag: the
# family has to survive the suffix `describe` appends, or every user who
# installed from `main` between two releases would be handed the other tree.
check "clone of main, between releases" v1.17.0-3-gabc1234 v1.18.0
check "clone of fr, between releases"   v1.17.0-fr-3-gabc1234 v1.18.0-fr

echo "▸ a recorded family wins over the derived one, and only when it exists"
# The end of the `-fr` family (2026-08-13) rests entirely on this: a French
# install that switches to English sits on a `-fr` TAG, so derivation would send
# it straight back to the French tree at the next update. The recorded choice is
# what makes the switch hold.
ENGINE="$VERSIONS/v1.17.0-fr"; mkdir -p "$ENGINE"   # a FRENCH installation
printf '' > "$STATE/tag-family"                 # recorded: the bare family
check_recorded() {  # check_recorded <label> <expected>
  local got; got="$(latest_tag)"
  if [ "$got" = "$2" ]; then
    echo "  ✅ $1 → $got"
  else
    echo "  ❌ $1 → got '$got', expected '$2'"
    FAILS=$((FAILS + 1))
  fi
}
check_recorded "French tag + recorded English → English" v1.18.0
rm -f "$STATE/tag-family"
check_recorded "file removed → back to derivation"       v1.18.0-fr

echo "▸ a repository with no tag at all does not crash"
git -C "$MIRROR" tag -d $(git -C "$MIRROR" tag) >/dev/null 2>&1
if out="$(latest_tag)" && [ -z "$out" ]; then
  echo "  ✅ empty result, exit 0"
else
  echo "  ❌ crashed or returned '$out' with no tags present"
  FAILS=$((FAILS + 1))
fi

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ the update path keeps every installation in its own language"
  exit 0
fi
echo "❌ $FAILS failure(s) — an update could switch a user's language"
exit 1
