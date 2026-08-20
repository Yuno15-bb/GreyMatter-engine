#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# adopt-launchd.sh — take responsibility for a launchd job installed before
# C Brain kept a record of what it owns.
#
# WHAT THIS IS NOT. It is not a discovery of ownership. launchd records no
# provenance: it knows which program runs, never who called `load`. Nothing
# here can establish that this installation registered the job.
#
# WHAT IT IS, in one line:
#
#     TECHNICAL CONCORDANCE OBSERVED
#   + EXPLICIT HUMAN AUTHORISATION
#   = OWNERSHIP RECORDED FROM NOW ON.
#
# Both halves are required and neither substitutes for the other. Concordance
# alone would let an installation adopt a stranger's job that happens to match.
# Authorisation alone would let a person hand over an identity they have not
# been shown — a confirmation is permission to act, not proof of what is being
# acted upon, and that is precisely how an identity gets taken over.
#
# NO AUTOMATIC PATH CALLS THIS. Not install.sh, not update.sh, not uninstall.sh.
# A test asserts it: an adoption that a machine can trigger on its own is not an
# adoption, it is the inference this whole chantier removed.
#
# AFTER CONFIRMATION, NOTHING IS UNLOADED. Reloading the job "to prove" the
# adoption would be a mutation performed to justify the right to mutate. The
# record is written; the next ordinary operation is then allowed by the guard.
#
# Usage: bash cbrain/adopt-launchd.sh <label>
# Exit:  0 adopted · 1 declined by the user · 2 usage · 3 refused, proof missing
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd -P)"
CB="${CB:-$HOME/.c-brain}"
. "$SELF/launchd-lib.sh"

LABEL="${1:-}"
if [ -z "$LABEL" ]; then
  echo "usage: adopt-launchd.sh <label>" >&2
  exit 2
fi

refuse() {
  printf '\n  ADOPTION REFUSED — %s\n' "$1" >&2
  printf '  Nothing was changed: no launchd job was touched, and %s was not\n' "$LABEL" >&2
  printf '  recorded as owned by this installation.\n' >&2
  exit 3
}

# ─── the job this installation would ship under that name ────────────────────
suffix="${LABEL#com.claudebrain.}"
[ "$suffix" != "$LABEL" ] || refuse "$LABEL is not a name this installation uses"
TPL="$SELF/../hooks/com.claudebrain.$suffix.plist.template"
# The com.claudebrain.* prefix earns NOTHING on its own. Without a template of
# that name, this installation has no job to compare against and no business
# claiming the identity.
[ -f "$TPL" ] || refuse "this installation ships no job called $LABEL"

RENDERED="$(sed "s|__HOME__|$HOME|g" "$TPL")"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

expected_program() {   # the LAST string of ProgramArguments: the script we run
  printf '%s' "$RENDERED" | tr -d '\n' \
    | sed -n 's|.*<key>ProgramArguments</key>[[:space:]]*<array>\(.*\)|\1|p' \
    | sed 's|</array>.*||; s|<string>|\n|g; s|</string>||g' \
    | sed 's|^[[:space:]]*||; s|[[:space:]]*$||' \
    | sed '/^$/d' | tail -1
}
PROGRAM="$(expected_program)"
[ -n "$PROGRAM" ] || refuse "the template for $LABEL declares no program to compare"

echo "  Adoption of a pre-existing launchd job"
echo "  ── label ................ $LABEL"

# ─── PROOF A — the live registry ─────────────────────────────────────────────
# Asked of launchctl, never of the filesystem. A plist can sit on disk while the
# domain runs something else entirely; the registry is what decides.
LIVE="$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null || true)"
[ -n "$LIVE" ] || refuse "no service $LABEL is registered in this launchd domain"

LIVE_PATH="$(printf '%s\n' "$LIVE" | sed -n 's|^[[:space:]]*path = ||p' | head -1)"
case "$LIVE" in
  *"$PROGRAM"*) : ;;
  *) printf '  ── live program ........ %s\n' \
       "$(printf '%s\n' "$LIVE" | sed -n 's|^[[:space:]]*program = ||p' | head -1)" >&2
     refuse "the running job does not execute this installation's program
   expected: $PROGRAM" ;;
esac
if [ -n "$LIVE_PATH" ] && [ "$LIVE_PATH" != "$PLIST" ]; then
  refuse "the running job was loaded from another file
   running:  $LIVE_PATH
   expected: $PLIST"
fi
echo "  ── live program ......... $PROGRAM"
echo "  ── loaded from .......... ${LIVE_PATH:-(not reported)}"

# ─── PROOF B — the plist on disk ─────────────────────────────────────────────
[ -f "$PLIST" ] || refuse "no plist at $PLIST to compare with the template"
NORM="$SELF/plist_normalise.py"
if ! diff -q <(python3 "$NORM" < "$PLIST") \
             <(printf '%s\n' "$RENDERED" | python3 "$NORM") >/dev/null 2>&1; then
  refuse "the plist on disk is not what this installation would write
   compared under the normal form in cbrain/plist_normalise.py"
fi
echo "  ── plist ................ $PLIST"
echo "  ── template match ....... equivalent under cbrain/plist_normalise.py"
echo "  ── adopting installation. $CB  (HOME=$HOME)"

# ─── THE HUMAN HALF ──────────────────────────────────────────────────────────
cat <<'TXT'

  These two facts say that the live service and its plist match THIS
  installation TODAY. They do not say who loaded the job. Adopting it is your
  decision, and from now on C Brain will treat the identity as its own.

TXT
printf "  Adopt %s? [y/N] " "$LABEL"
ans=""
read -r ans || ans=""       # no input, no adoption
case "$ans" in
  y|Y|o|O) ;;
  *) echo "  Declined. Nothing was changed."; exit 1 ;;
esac

# ─── RECORD, AND NOTHING ELSE ────────────────────────────────────────────────
# state/launchd-owned keeps ONE Label per line — the format the ownership guard
# reads, unchanged, so what A6.2 proved about it still holds. The provenance of
# an adoption goes to a log beside it: an audit trail is not an authority.
cb_launchd_remember "$LABEL"
AUDIT="$CB/state/launchd-adoptions.log"
mkdir -p "$(dirname "$AUDIT")"
printf '%s\tadopted\t%s\tprogram=%s\tplist=%s\thome=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$LABEL" "$PROGRAM" "$PLIST" "$HOME" >> "$AUDIT"
echo "  + $LABEL is now recorded as owned by this installation."
echo "    Nothing was unloaded or reloaded. The next ordinary operation may act on it."
