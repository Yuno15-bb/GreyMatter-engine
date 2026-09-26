#!/bin/bash
# FULL CYCLE — walks the LIVE orb through every one of its states, in family
# order, so it can be watched on the real desktop.
#
# ⚠ THIS CYCLE FALSIFIES ITSELF IF YOU WORK DURING IT. Every tool call the agent
#   makes writes `status.json` back to "busy / working" via hooks/brain_battement.py:
#   the orb then shows WORKING instead of the cycle's state, and the
#   demonstration lies. Launch it DETACHED, then run nothing until it ends.
#
# ⚠ It drives an ALREADY RUNNING orb — it does not open one. Check first:
#     pgrep -f "$BRAIN/capsule" | wc -l           (0 = nothing to watch)
#   ⚠️ the pattern anchors on the root, it does not name it: hard-coded, it would
#      only match this trunk and return 0 for the capsule of a neighbouring tree.
#
# Usage:  ./banc/cycle.sh [seconds per state]     (default 4)
set -u
PAUSE="${1:-4}"
BRAIN="${BRAIN_HOME:-$HOME/.c-brain/trunk}"
STATUS="$BRAIN/hooks/brain_status.py"

# The order follows the FAMILIES, not the alphabet: you see each mechanic climb
# in intensity, then tip over into the next one. Alphabetical order would jump
# the colour at every step and the 1.4 s cross-fade would have nothing to tell.
ETATS=(
  mapping auditing architecting challenging      # Inspection     — swell
  filing archiving gardening correcting          # Organisation   — sweep
  working distilling synthesizing                # Transformation — vortex
  committing                                     # Validation     — shards
  idle                                           # Rest           — breath
)

# A list of states may follow the duration:  ./banc/cycle.sh 3 challenging gardening idle
# It is for FILMING. Fifteen seconds cannot carry thirteen states: the mechanic
# cross-fade lasts 1.4 s, so a state needs about 3 s to show itself cleanly.
# Fifteen seconds = five states, one per family — the orb's whole vocabulary,
# none of it rushed. (the author, 20/09: "every state must hold cleanly over the
# 15 seconds".)
CONNUS=" ${ETATS[*]} "
if [ "$#" -gt 1 ]; then
  shift
  for e in "$@"; do
    case "$CONNUS" in
      *" $e "*) ;;
      # Without this guard a misspelt state raises nothing: brain_status.py accepts it,
      # the orb does not know it and falls back to "idle". We would film a silent
      # state while believing we filmed the other one.
      *) echo "unknown state: $e" >&2; echo "known: ${ETATS[*]}" >&2; exit 1 ;;
    esac
  done
  ETATS=("$@")
fi

echo "cycle: ${#ETATS[@]} states × ${PAUSE}s ≈ $(( ${#ETATS[@]} * PAUSE ))s"
for e in "${ETATS[@]}"; do
  if [ "$e" = "idle" ]; then python3 "$STATUS" idle >/dev/null
  else                       python3 "$STATUS" busy "$e" cycle >/dev/null; fi
  printf '%s ' "$e"
  sleep "$PAUSE"
done
echo
echo "cycle over — the orb is back at rest"
