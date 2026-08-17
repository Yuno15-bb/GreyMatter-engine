#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# e2e_install_update.sh — THE FIRST END-TO-END CONTRACT.
#
# WHY IT EXISTS. On 2026-08-17 fifteen contracts were green and the product was
# broken: the documented install produced an engine `brain update` refused for
# ever. Every contract was right about its own component; not one of them looked
# at the chain. The checkpoint named it — "green component by component is not a
# correct product" — and this file is the answer.
#
# So it fabricates NOTHING. No hand-written marker, no function lifted out of
# install.sh, no string searched for in a script. It builds a source repository,
# runs the real installer, invokes the real installed CLI, runs the real updater,
# and looks at what is on disk afterwards:
#
#   source → install → versioned engine → marker → CLI → update → switch →
#   rollback → trunk intact
#
# THE ENVIRONMENT IS ISOLATED, and that means more than $HOME. An isolated HOME
# with the host's PATH still runs the HOST's `brain`, which is fault B1 — a test
# that goes green having exercised the developer's own installation. PATH is
# built from scratch here, and `assert_no_host_leak` proves the binary under test
# is the one this test installed.
#
# Usage: tests/e2e_install_update.sh [--sabotage <name>] [--keep]
#        --sabotage lists its names when given an unknown one.
set -uo pipefail

SABOTAGE="${SABOTAGE:-}"
KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --sabotage) SABOTAGE="${2:-}"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    *) echo "Usage: $0 [--sabotage <name>] [--keep]"; exit 2 ;;
  esac
done

# ⚠ A MISSPELLED SABOTAGE MUST NOT RUN THE NORMAL TEST. Without this check
# `--sabotage swtich-before-selftest` would quietly perturb nothing, go green,
# and be recorded as proof that the sabotage reddens — the harness lying about
# itself, which is the most expensive kind of green there is.
SABOTAGES="no-ownership dev-updated switch-before-selftest rollback-missing update-touches-trunk source-mutated host-brain-leak"
if [ -n "$SABOTAGE" ]; then
  case " $SABOTAGES " in
    *" $SABOTAGE "*) : ;;
    *) echo "❌ unknown sabotage: $SABOTAGE"; echo "   known:"; for n in $SABOTAGES; do echo "     $n"; done; exit 2 ;;
  esac
fi

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
LAB="$(cd "$(mktemp -d "${TMPDIR:-/tmp}/cbrain-e2e.XXXXXX")" && pwd -P)"
trap '[ "$KEEP" = "1" ] || rm -rf "$LAB"' EXIT

# macOS ships no `readlink -f`; this follows a chain of symlinks to the end.
readlink_f() {
  local p="$1" d t
  while [ -L "$p" ]; do
    d="$(cd -P "$(dirname "$p")" && pwd)"; t="$(readlink "$p")"
    case "$t" in /*) p="$t" ;; *) p="$d/$t" ;; esac
  done
  printf '%s\n' "$p"
}

# ⚠ NEVER RETURNS AN EMPTY STRING SILENTLY. `basename "$(cd "$CB/engine" && pwd -P)"`
# yields "" when the link dangles — and comparing "" to "" then reports the
# engine as unchanged. That is a green produced by being unable to look, and it
# hid a sabotage that had in fact switched the engine to a deleted directory.
# A name that could not be read is reported as such, and never matches anything.
active_version() {
  local p
  p="$(cd "$CB/engine" 2>/dev/null && pwd -P)" || { echo "<UNREADABLE:dangling-or-missing-engine-link>"; return 0; }
  [ -n "$p" ] && basename "$p" || echo "<UNREADABLE:empty>"
}

fails=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1"; fails=$((fails + 1)); }
info() { echo "     $1"; }

echo "== C Brain — end-to-end: install → update → rollback =="
[ -n "$SABOTAGE" ] && echo "   SABOTAGE: $SABOTAGE"
echo "   lab: $LAB"

# ─── The source, built from the WORKING TREE ─────────────────────────────────
# `git ls-files` from the repository under test, not a clone of its HEAD: the
# point is to exercise the code as it is on disk right now, including changes
# that are staged but not committed. A test that could only see the last commit
# would have nothing to say while a chantier is being written.
mkdir -p "$LAB/src"
( cd "$REPO" && git ls-files -z | xargs -0 tar -c ) | tar -x -C "$LAB/src"

# ─── SABOTAGE GOES INTO THE SOURCE, BEFORE ANY VERSION EXISTS ────────────────
#
# TWO REASONS, both learned the hard way on 2026-08-17.
#
# 1. The installer builds a version with `git archive`, which emits the COMMITTED
#    tree. A sabotage applied to a working file in the user's clone therefore
#    never reaches the engine that runs — the new model keeping a source's
#    uncommitted state out of the engine, doing exactly its job.
# 2. Even committed in the clone, a sabotage only lands in the version built FROM
#    that clone. The updater then builds the NEXT version from the mirror, which
#    is clean — so `--rollback`, which runs the new engine's code, was executing
#    an unsabotaged updater and going green. The sabotage has to be in the
#    published history, not in one checkout of it.
#
# Patched here, both v1.0.0 and v1.1.0 carry it, and so does the user's clone.
sabotage_patch() {   # sabotage_patch <file> <python-expression-on-`s`>
  python3 - "$LAB/src/$1" "$2" <<'PY'
import sys, re
path, expr = sys.argv[1], sys.argv[2]
s = open(path).read()
before = s
s = eval(expr, {"re": re, "s": s})
if s == before:
    sys.exit("SABOTAGE DID NOT APPLY to %s — the pattern matched nothing" % path)
open(path, "w").write(s)
PY
}

case "$SABOTAGE" in
  # The installer stops recording that it owns what it built. One line.
  no-ownership)
    sabotage_patch install.sh 's.replace(chr(39)+chr(37)+"s\\n"+chr(39)+" \"$VERSIONS\" > \"$CB/state/engine-managed\"", ": # SABOTAGE")' ;;
  # The updater forgets that a --dev engine is off limits — both refusals.
  dev-updated)
    sabotage_patch cbrain/update.sh 's.replace("if [ -f \"$DEVMARK\" ] && [ \"$MODE\" != \"auto-off\" ] && [ \"$MODE\" != \"auto-on\" ]; then", "if false; then").replace("if [ -f \"$DEVMARK\" ]; then", "if false; then")' ;;
  # The switch happens before the check — the ordering this chantier replaced.
  switch-before-selftest)
    sabotage_patch cbrain/update.sh 's.replace("if bash \"$CANDIDATE/hooks/selftest.sh\"", "switch_to \"$NEW\"\nif bash \"$CANDIDATE/hooks/selftest.sh\"", 1)' ;;
  # Rolling back to a version that is not on disk is no longer checked for.
  rollback-missing)
    sabotage_patch cbrain/update.sh 's.replace("if [ ! -d \"$VERSIONS/$target\" ]; then", "if false; then")' ;;
  # The updater writes into the user's notes.
  update-touches-trunk)
    sabotage_patch cbrain/update.sh 's.replace("\ngate_ownership\n", "\ngate_ownership\nrm -rf \"$HOME/.c-brain/trunk/lessons\"\n", 1)' ;;
  # The updater reaches back into the source the model exists to protect.
  source-mutated)
    sabotage_patch cbrain/update.sh 's.replace("\ngate_ownership\n", "\ngate_ownership\ngit -C \"'"$LAB"'/user-clone\" checkout -q main 2>/dev/null || true\n", 1)' ;;
esac

# A published history: v1.0.0, then v1.1.0 differing by one tracked file. Both
# hold the SAME code under test, so an update exercises this updater and not a
# historical one.
git -C "$LAB/src" init -q
git -C "$LAB/src" add -A
git -C "$LAB/src" -c user.email=e2e@test -c user.name=e2e commit -qm "v1.0.0"
git -C "$LAB/src" tag v1.0.0
echo "the 1.1.0 marker" > "$LAB/src/VERSION-MARKER"
git -C "$LAB/src" add -A
git -C "$LAB/src" -c user.email=e2e@test -c user.name=e2e commit -qm "v1.1.0"
git -C "$LAB/src" tag v1.1.0
git clone --quiet --bare "$LAB/src" "$LAB/origin.git"

# ─── The isolated environment ────────────────────────────────────────────────
export HOME="$LAB/home"
mkdir -p "$HOME"
CB="$HOME/.c-brain"
# PATH BUILT FROM NOTHING. The host's ~/.local/bin is deliberately absent: that
# is where the developer's own `brain` lives, and inheriting it is how a test
# ends up measuring the wrong installation. /opt/homebrew/bin is included only
# for `node`, which the selftest needs.
export PATH="$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
# The trunk's auto-save and the agents must not reach the real machine.
export CBRAIN_NO_AUTO_UPDATE=""
unset CLAUDE_BRAIN_GARDENING 2>/dev/null || true

# SABOTAGE `host-brain-leak`: put a decoy `brain` ahead on PATH, exactly as an
# inherited PATH would. The assertion below must catch it; if it does not, every
# other green in this file is worthless.
if [ "$SABOTAGE" = "host-brain-leak" ]; then
  mkdir -p "$LAB/decoy"
  printf '#!/bin/sh\necho "decoy brain from the host"\n' > "$LAB/decoy/brain"
  chmod +x "$LAB/decoy/brain"
  export PATH="$LAB/decoy:$PATH"
fi

# ─── The user's clone, as INSTALL.md prescribes ──────────────────────────────
git clone --quiet "$LAB/origin.git" "$LAB/user-clone"
git -C "$LAB/user-clone" checkout -q v1.0.0

# ⚠ THE BASELINE IS TAKEN HERE, after any sabotage has patched the clone and
# before the installer runs. Taken earlier it recorded a tree the sabotages then
# dirtied themselves, and every sabotaged run reported "the update mutated the
# source" while showing an UNCHANGED HEAD — an accusation the evidence beside it
# contradicted. A witness must be photographed at the moment the watch begins.
SRC_HEAD_BEFORE="$(git -C "$LAB/user-clone" rev-parse HEAD)"
SRC_TREE_BEFORE="$(git -C "$LAB/user-clone" status --porcelain --untracked-files=no)"

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 1. install — the documented path"
# ═══════════════════════════════════════════════════════════════════════════
# --core-only: no launchd. `launchctl load` registers into the REAL user's
# launchd domain whatever $HOME says, so a test that ran it would install
# background jobs on the machine running the test.
if ( cd "$LAB/user-clone" && ./install.sh --core-only ) >"$LAB/install.log" 2>&1; then
  ok "install.sh completed"
else
  ko "install.sh failed"; tail -5 "$LAB/install.log" | sed 's/^/       /'
fi

ENGINE_LINK="$(readlink "$CB/engine" 2>/dev/null || echo "")"
case "$ENGINE_LINK" in
  "$CB/versions/"*) ok "engine points into versions/ ($(basename "$ENGINE_LINK"))" ;;
  "") ko "no engine link at all" ;;
  *)  ko "engine points OUTSIDE versions/: $ENGINE_LINK" ;;
esac

[ -d "$CB/engine/.git" ] \
  && ko "the engine carries a .git — it is a checkout, not an immutable version" \
  || ok "the engine has no .git (an export, not a repository)"

# THE MARKER IS READ, NEVER WRITTEN. The contract this replaces built its own
# fixture marker, so it could not have noticed that install.sh never wrote one.
if [ -f "$CB/state/engine-managed" ]; then
  ok "install.sh wrote the ownership marker itself"
  info "owns: $(cat "$CB/state/engine-managed")"
else
  ko "install.sh did NOT write state/engine-managed — the install owns nothing"
fi

if [ -d "$CB/source.git" ]; then ok "source mirror created"; else ko "no source mirror — updates have nowhere to fetch from"; fi
if [ -f "$CB/engine/.cbrain-manifest" ]; then ok "the version carries an integrity manifest"; else ko "no manifest — immutability cannot be checked"; fi

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 2. the installed CLI — and that it is OURS"
# ═══════════════════════════════════════════════════════════════════════════
BRAIN_BIN="$(command -v brain 2>/dev/null || echo "")"
if [ -z "$BRAIN_BIN" ]; then
  ko "no \`brain\` on PATH after installing"
else
  # FULLY resolved, directory components included. Following only the trailing
  # symlink stops at `~/.c-brain/engine/brain` — a real file inside a symlinked
  # DIRECTORY — and the assertion then compares a path that still contains the
  # link it was supposed to see through. That mistake made this very check fail
  # on a correct install the first time it ran.
  RESOLVED="$(cd -P "$(dirname "$(readlink_f "$BRAIN_BIN")")" && pwd)/$(basename "$BRAIN_BIN")"
  case "$RESOLVED" in
    "$CB/versions/"*)
      ok "the \`brain\` on PATH resolves into this test's own versions/" ;;
    *)
      ko "PATH LEAK — \`brain\` resolves to $RESOLVED, outside this test's install"
      info "this is fault B1: an isolated HOME is not an isolated environment" ;;
  esac
fi

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 3. a note in the trunk, to prove the update never touches it"
# ═══════════════════════════════════════════════════════════════════════════
mkdir -p "$HOME/.c-brain/trunk/lessons"
NOTE="$HOME/.c-brain/trunk/lessons/e2e-witness.md"
printf -- '---\nname: e2e-witness\n---\n\nthe user knowledge that must survive an update\n' > "$NOTE"
NOTE_BEFORE="$(shasum -a 256 "$NOTE" | cut -d' ' -f1)"
ok "witness note written"

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 4. update — the real one, through the installed CLI"
# ═══════════════════════════════════════════════════════════════════════════
VERSION_BEFORE="$(active_version)"

# SABOTAGE `switch-before-selftest` needs the candidate to be BAD. Breaking it in
# the mirror is what a bad release would look like — the updater has to find out
# on its own.
if [ "$SABOTAGE" = "switch-before-selftest" ]; then
  git -C "$LAB/src" rm -q --cached hooks/brain_status.py >/dev/null 2>&1
  echo "this is not python(((" > "$LAB/src/hooks/brain_status.py"
  git -C "$LAB/src" add -A
  git -C "$LAB/src" -c user.email=e2e@test -c user.name=e2e commit -qm "broken 1.1.0" >/dev/null
  git -C "$LAB/src" tag -f v1.1.0 >/dev/null
  git -C "$LAB/src" push --quiet --force "$LAB/origin.git" --tags >/dev/null 2>&1
fi

set +e
brain update >"$LAB/update.log" 2>&1
UPDATE_RC=$?
set -e
VERSION_AFTER="$(active_version)"

if [ "$SABOTAGE" = "no-ownership" ] || [ "$SABOTAGE" = "dev-updated" ]; then
  : # asserted in their own sections below
elif [ "$SABOTAGE" = "switch-before-selftest" ]; then
  # THE PROPERTY: a version may only become the engine after passing its checks.
  if [ "$VERSION_AFTER" = "$VERSION_BEFORE" ]; then
    ok "candidate failed its selftest and the engine was NOT switched (still $VERSION_AFTER)"
  else
    ko "THE ENGINE WAS SWITCHED TO A VERSION THAT FAILS ITS OWN SELFTEST ($VERSION_BEFORE → $VERSION_AFTER)"
  fi
  [ -d "$CB/versions/v1.1.0" ] \
    && ko "the failed candidate was left on disk" \
    || ok "the failed candidate was deleted"
else
  if [ "$UPDATE_RC" -eq 0 ]; then ok "brain update succeeded (rc=0)"; else ko "brain update failed (rc=$UPDATE_RC)"; tail -6 "$LAB/update.log" | sed 's/^/       /'; fi
  if [ "$VERSION_AFTER" = "v1.1.0" ]; then
    ok "the engine really moved: $VERSION_BEFORE → $VERSION_AFTER"
  else
    ko "the engine did not reach v1.1.0 (it is on $VERSION_AFTER)"
  fi
  # The update is only real if the NEW CODE is what is mounted. A symlink that
  # points at a directory proves nothing about what is inside it.
  [ -f "$CB/engine/VERSION-MARKER" ] \
    && ok "the new version's files are the ones mounted (VERSION-MARKER present)" \
    || ko "the engine link moved but the new version's content is not there"
  # Selftest before switch: the log must show the check happening on the
  # candidate, not on the engine after the fact.
  grep -q "still inactive" "$LAB/update.log" \
    && ok "the selftest ran on the candidate BEFORE the switch" \
    || ko "no evidence the candidate was tested before being switched to"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 5. what the update must NEVER have touched"
# ═══════════════════════════════════════════════════════════════════════════
if [ -f "$NOTE" ] && [ "$(shasum -a 256 "$NOTE" | cut -d' ' -f1)" = "$NOTE_BEFORE" ]; then
  ok "the trunk note is byte-for-byte intact"
else
  ko "THE UPDATE TOUCHED THE TRUNK — the user's knowledge is not intact"
fi

SRC_HEAD_AFTER="$(git -C "$LAB/user-clone" rev-parse HEAD)"
SRC_TREE_AFTER="$(git -C "$LAB/user-clone" status --porcelain --untracked-files=no)"
if [ "$SRC_HEAD_AFTER" = "$SRC_HEAD_BEFORE" ] && [ "$SRC_TREE_AFTER" = "$SRC_TREE_BEFORE" ]; then
  ok "the user's source clone was not moved or modified"
else
  ko "THE UPDATE MUTATED THE SOURCE CLONE (HEAD ${SRC_HEAD_BEFORE:0:7} → ${SRC_HEAD_AFTER:0:7})"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 6. rollback"
# ═══════════════════════════════════════════════════════════════════════════
if [ "$SABOTAGE" = "" ] || [ "$SABOTAGE" = "host-brain-leak" ] || [ "$SABOTAGE" = "rollback-missing" ]; then
  # ─── First: a rollback whose target is GONE ────────────────────────────────
  # Versions are pruned, and a user can delete one by hand. Announcing a
  # rollback while landing somewhere else — or on a half-deleted tree — is worse
  # than refusing, because the user believes they went back and they did not.
  # This runs in the normal pass too: a refusal nobody exercises is a refusal
  # nobody knows still works.
  SAVED="$LAB/saved-version"
  rm -rf "$SAVED"; cp -R "$CB/versions/$VERSION_BEFORE" "$SAVED"
  rm -rf "$CB/versions/$VERSION_BEFORE"
  set +e; brain update --rollback >"$LAB/rollback-missing.log" 2>&1; RBM_RC=$?; set -e
  NOW="$(active_version)"
  if [ "$RBM_RC" -ne 0 ] && [ "$NOW" = "$VERSION_AFTER" ]; then
    ok "rollback to a version that is gone is REFUSED, engine untouched"
  else
    ko "rollback to a MISSING version was not refused (rc=$RBM_RC, engine now $NOW)"
    info "the engine was moved on the strength of a version that is not on disk"
  fi
  # ⚠ AND IT MUST SAY WHICH ONE, AND WHAT IS LEFT. Measured: without the explicit
  # check, `switch_to` refuses on its own — the engine is safe either way — but
  # the user is told "could not switch the engine link", a diagnosis of the wrong
  # problem. They cannot act on it, and the versions they COULD roll back to are
  # never named. That is what the guard uniquely provides, so that is what this
  # asserts.
  if grep -q "no longer installed" "$LAB/rollback-missing.log" \
     && grep -q "Versions still on disk" "$LAB/rollback-missing.log"; then
    ok "the refusal names the missing version and lists what remains"
  else
    ko "the refusal does not say WHICH version is missing, nor what is left"
    tail -3 "$LAB/rollback-missing.log" | sed 's/^/       /'
  fi
  # put it back, so the real rollback below has something to return to
  cp -R "$SAVED" "$CB/versions/$VERSION_BEFORE"
fi

if [ "$SABOTAGE" = "" ] || [ "$SABOTAGE" = "host-brain-leak" ] || [ "$SABOTAGE" = "rollback-missing" ]; then
  set +e; brain update --rollback >"$LAB/rollback.log" 2>&1; RB_RC=$?; set -e
  NOW="$(active_version)"
  if [ "$RB_RC" -eq 0 ] && [ "$NOW" = "$VERSION_BEFORE" ]; then
    ok "rollback returned the engine to $VERSION_BEFORE"
  else
    ko "rollback did not restore $VERSION_BEFORE (rc=$RB_RC, engine on $NOW)"
    tail -5 "$LAB/rollback.log" | sed 's/^/       /'
  fi
  [ -f "$CB/engine/VERSION-MARKER" ] \
    && ko "rolled back, but v1.1.0's file is still mounted" \
    || ok "the rolled-back version's content is the one mounted"
else
  info "(rollback not exercised under this sabotage)"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 7. the two refusals — an unowned engine, and a --dev engine"
# ═══════════════════════════════════════════════════════════════════════════
if [ "$SABOTAGE" = "no-ownership" ]; then
  if [ ! -f "$CB/state/engine-managed" ]; then
    ok "sabotage in place: no ownership marker was written"
  else
    ko "the sabotage did not take — the marker is still there, this run proves nothing"
  fi
  if [ "$UPDATE_RC" -ne 0 ] && [ "$VERSION_AFTER" = "$VERSION_BEFORE" ]; then
    ok "an unowned engine is refused, and nothing moved"
  else
    ko "an engine nobody owns was UPDATED anyway (rc=$UPDATE_RC, $VERSION_BEFORE → $VERSION_AFTER)"
  fi
fi

# ─── A development engine, on THIS SAME installation ─────────────────────────
# Deliberately the same $HOME: it already holds versions/ and a source mirror, so
# the updater has everything it needs to go ahead. That is what makes the guard
# load-bearing rather than decorative — in a fresh home the update would stop at
# "no source mirror" and a disabled guard would look harmless.
# It is also the realistic path: somebody installs C Brain, then re-runs the
# installer with --dev from their checkout.
( cd "$LAB/user-clone" && ./install.sh --core-only --dev ) >"$LAB/dev-install.log" 2>&1

DEV_ENGINE="$(readlink "$CB/engine" 2>/dev/null || echo "")"
if [ "$(cd "$DEV_ENGINE" 2>/dev/null && pwd -P)" = "$LAB/user-clone" ]; then
  ok "--dev linked the engine to the checkout"
else
  ko "--dev did not link the checkout (engine → $DEV_ENGINE)"
fi
[ -f "$CB/state/engine-dev" ] && ok "--dev wrote its own marker" || ko "--dev wrote no marker"
[ -f "$CB/state/engine-managed" ] && ko "--dev ALSO claims to be a managed install" || ok "--dev is not marked as managed (the two are exclusive)"

DEV_HEAD_BEFORE="$(git -C "$LAB/user-clone" rev-parse HEAD)"
set +e; brain update >"$LAB/dev-update.log" 2>&1; DEV_RC=$?; set -e
DEV_HEAD_AFTER="$(git -C "$LAB/user-clone" rev-parse HEAD)"
DEV_ENGINE_AFTER="$(cd "$CB/engine" 2>/dev/null && pwd -P || echo "")"

# THE PROPERTY: a --dev engine is never updated. Not "the clone survives" — the
# new model makes that true even without the guard, since nothing writes to a
# source any more. What a disabled guard costs is the install silently ceasing
# to be a development install: the engine link leaves the checkout, and the
# developer's next session runs a built version instead of their own code.
if [ "$DEV_ENGINE_AFTER" = "$LAB/user-clone" ]; then
  ok "the engine still points at the development checkout"
else
  ko "AN UPDATE MOVED A --dev ENGINE off the checkout (now $DEV_ENGINE_AFTER)"
fi

# ⚠ MEASURED, and worth stating: with the dev guard disabled the engine STILL
# does not move — `gate_ownership` refuses an engine outside versions/ on its own.
# The two protections overlap, which is why the sabotage below cannot make the
# checkout move. What it CAN redden, and what it therefore asserts, is the
# refusal being the RIGHT one: a developer told "this engine carries no
# managed-install marker" is being handed a diagnosis of the wrong problem, and
# would go looking for a marker to create.
grep -qi "Development engine detected" "$LAB/dev-update.log" \
  && ok "a --dev engine is refused BY NAME, not by a generic ownership error" \
  || { ko "a --dev engine was not refused with the expected message"; tail -4 "$LAB/dev-update.log" | sed 's/^/       /'; }

[ "$DEV_HEAD_AFTER" = "$DEV_HEAD_BEFORE" ] \
  && ok "the development checkout was not moved (HEAD unchanged)" \
  || ko "THE DEVELOPMENT CHECKOUT WAS MOVED by an update (${DEV_HEAD_BEFORE:0:7} → ${DEV_HEAD_AFTER:0:7})"

# ═══════════════════════════════════════════════════════════════════════════
echo
if [ "$fails" -eq 0 ]; then
  echo "✅ e2e_install_update — the chain holds end to end"
  exit 0
else
  echo "❌ e2e_install_update — $fails assertion(s) failed"
  echo "   lab kept at: $LAB"
  KEEP=1
  exit 1
fi
