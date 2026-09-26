#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# e2e_occupied_surfaces.sh — INSTALLING OVER SOMEBODY ELSE'S INSTALLATION.
#
# WHY IT EXISTS. On 2026-08-19 this installer ran on a machine that already had
# an author's installation of C Brain. It repointed `~/.claude/agents` at its own
# trunk and overwrote `~/.claude/statusline.py`, printed "backed up:" and "+",
# and exited 0. The other installation kept calling agents that were no longer
# where it had left them: 118 `agent not found` in 39 hours, its distillation
# dead, and no line anywhere saying a foreign surface had been taken. The backup
# was real and is what allowed the repair — the defect is the SILENT TAKEOVER.
#
# WHAT IS MEASURED, and it is the printed screen. Not an exit code: the install
# SUCCEEDS in both the broken and the repaired version, and succeeded during the
# incident itself. So every assertion below reads either the installer's output
# or the state of a surface on disk afterwards. This is the same discipline as
# tests/launchd_ownership.py one surface over, and the reason that file exists.
#
# WHY IT CANNOT DISTURB THE MACHINE IT RUNS ON.
#   · `--core-only` — no launchd. `launchctl` indexes by Label inside gui/<uid>,
#     NOT by $HOME, so a test that reached that step would register jobs on the
#     real machine. That is exactly what happened on 2026-08-18, for 28 hours.
#   · `--no-shortcut` — nothing lands on the real Desktop.
#   · $HOME and PATH are built from nothing, so the `brain` under test is the one
#     this file installed and never the developer's own (fault B1, 2026-08-17).
#
# Usage: tests/e2e_occupied_surfaces.sh [--sabotage <name>] [--keep]
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

# A MISSPELLED SABOTAGE MUST NOT RUN THE NORMAL TEST, or the harness records a
# green as proof that a sabotage reddens. Borrowed from e2e_install_update.sh.
SABOTAGES="silent-overwrite silent-statusline summary-swallowed"
if [ -n "$SABOTAGE" ]; then
  case " $SABOTAGES " in
    *" $SABOTAGE "*) : ;;
    *) echo "❌ unknown sabotage: $SABOTAGE"; echo "   known:"
       for n in $SABOTAGES; do echo "     $n"; done; exit 2 ;;
  esac
fi

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
LAB="$(cd "$(mktemp -d "${TMPDIR:-/tmp}/cbrain-surfaces.XXXXXX")" && pwd -P)"
trap '[ "$KEEP" = "1" ] || rm -rf "$LAB"' EXIT

fails=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1"; fails=$((fails + 1)); }
info() { echo "     $1"; }

echo "== C Brain — installing over an installation that is already there =="
[ -n "$SABOTAGE" ] && echo "   SABOTAGE: $SABOTAGE"
echo "   lab: $LAB"

# ─── The source, taken from the WORKING TREE ─────────────────────────────────
# The code as it is on disk right now, uncommitted changes included: a contract
# that could only see the last commit has nothing to say while work is going on.
mkdir -p "$LAB/src"
( cd "$REPO" && git ls-files -z | xargs -0 tar -c ) | tar -x -C "$LAB/src"

sabotage_patch() {   # sabotage_patch <file> <old> <new>
  python3 - "$LAB/src/$1" "$2" "$3" <<'PY'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path).read()
if old not in s:
    sys.exit("SABOTAGE DID NOT APPLY to %s — the pattern matched nothing" % path)
open(path, "w").write(s.replace(old, new, 1))
PY
}

case "$SABOTAGE" in
  # The gate comes out of `link`, and the installer takes any link it finds —
  # the 2026-08-19 behaviour, exactly.
  silent-overwrite)
    sabotage_patch install.sh \
      '      *) surface_owned "$path" \' \
      '      *) : ;; # SABOTAGE
      *) surface_owned "$path" \' ;;
  # Same, for the plain copy that lands the status line. ⚠ THE FIRST VERSION OF
  # THIS SABOTAGE WAS A NO-OP: it inserted `if false; then` and left the real
  # condition on an `elif`, so the gate still ran and the bench stayed green —
  # a harness certifying its own reddening while changing nothing. The condition
  # itself is what has to go false.
  silent-statusline)
    sabotage_patch install.sh \
      '       && ! surface_owned "$HOME/.claude/statusline.py"; then' \
      '       && false; then  # SABOTAGE' ;;
  # The refusals are still printed where they happen — three screens up — but
  # the closing screen stops repeating them. This is C bis A4 wearing a new hat.
  summary-swallowed)
    sabotage_patch install.sh \
      'if [ "${REFUSED_SURFACES:-0}" -gt 0 ]; then' \
      'if false; then' ;;
esac

# The installer builds its engine with `git archive`, so the source has to be a
# repository with a commit in it.
git -C "$LAB/src" init -q
git -C "$LAB/src" add -A
git -C "$LAB/src" -c user.email=t@test -c user.name=t commit -qm "under test"
git -C "$LAB/src" tag v1.0.0

# ─── An environment isolated in BOTH the ways that have already failed ───────
export HOME="$LAB/home"
export PATH="$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
MARK="MARKER-OTHER-INSTALLATION"

# The other installation, reduced to what the incident actually touched: an
# agents directory reached through a link, a status line, and a `brain` command.
fresh_other_install() {
  rm -rf "$HOME"
  mkdir -p "$HOME/.claude" "$HOME/.local/bin" "$HOME/other-trunk/agents"
  printf '# %s\n' "$MARK" > "$HOME/other-trunk/agents/distiller.md"
  ln -s "$HOME/other-trunk/agents" "$HOME/.claude/agents"
  printf '#!/usr/bin/env python3\n# %s\nprint("other")\n' "$MARK" > "$HOME/.claude/statusline.py"
  printf '#!/bin/sh\necho "%s"\n' "$MARK" > "$HOME/.local/bin/brain"
  chmod +x "$HOME/.local/bin/brain"
  printf '{}\n' > "$HOME/.claude/settings.json"
}

install_run() {      # install_run <log-name> → exit code of the installer
  ( cd "$LAB/src" && ./install.sh --core-only --no-shortcut ) >"$LAB/$1" 2>&1
}

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 1. the installer runs over an installation it did not make"
# ═══════════════════════════════════════════════════════════════════════════
fresh_other_install
install_run "over.log"; OVER_EXIT=$?
OUT="$LAB/over.log"

# A — EACH SURFACE IS NAMED. Not "some surfaces were skipped": the path, on the
# screen, because a person has to go and look at the thing that is there.
for s in ".claude/agents" ".claude/statusline.py" ".local/bin/brain"; do
  if grep -q "OCCUPIED, and not by this installation: $HOME/$s" "$OUT"; then
    ok "named on screen: ~/$s"
  else
    ko "NOT named on screen: ~/$s"
  fi
done

# B — AND NOT ONE OF THEM WAS REPLACED. The message could be printed by an
# installer that overwrites anyway; the disk is what settles it.
if [ "$(readlink "$HOME/.claude/agents")" = "$HOME/other-trunk/agents" ]; then
  ok "the agents link still points at the other installation"
else
  ko "the agents link was repointed"
  info "now → $(readlink "$HOME/.claude/agents" || echo '(not a link)')"
fi
grep -q "$MARK" "$HOME/.claude/statusline.py" \
  && ok "the status line is still the other installation's" \
  || ko "the status line was overwritten"
grep -q "$MARK" "$HOME/.local/bin/brain" \
  && ok "the \`brain\` command still starts the other installation" \
  || ko "the \`brain\` command was taken over"

# C — THE REFUSAL SURVIVES THE SCROLL. Printed where it happens, it is several
# screens above the end on a fresh machine — the defect C bis A4 named for the
# PATH warning, and the reason the count comes back at the close.
if grep -q "3 surface(s) were left to their current owner" "$OUT"; then
  ok "the closing screen still counts the three refusals"
else
  ko "the closing screen says nothing about the refusals"
  info "last lines: $(tail -3 "$OUT" | tr '\n' ' ')"
fi

# D — AND C BRAIN IS STILL INSTALLED. A refusal is a reported outcome, not a
# crash: refusing to take a surface must not cost the user the whole product.
[ "$OVER_EXIT" = "0" ] && ok "the installer still exits 0" \
                       || ko "the installer exited $OVER_EXIT"
[ -d "$HOME/.c-brain/trunk" ] && [ -d "$HOME/.c-brain/engine/hooks" ] \
  && ok "the trunk and the engine were installed anyway" \
  || ko "the install did not complete"

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 2. the gesture the refusal prints actually works"
# ═══════════════════════════════════════════════════════════════════════════
# A refusal that names no next step is an obstacle. The next step it names is
# `mv <path> <path>.before-c-brain`, so we run exactly that and nothing else.
mv "$HOME/.claude/agents" "$HOME/.claude/agents.before-c-brain"
install_run "handover.log"
if [ "$(readlink "$HOME/.claude/agents")" = "$HOME/.c-brain/trunk/agents" ]; then
  ok "after the printed gesture, C Brain takes the surface"
else
  ko "the printed gesture did not hand the surface over"
fi
if grep -q "2 surface(s) were left to their current owner" "$LAB/handover.log"; then
  ok "and the count drops to the two still occupied"
else
  ko "the count did not follow"
fi
[ "$(readlink "$HOME/.claude/agents.before-c-brain")" = "$HOME/other-trunk/agents" ] \
  && ok "what was moved aside is untouched" \
  || ko "what was moved aside was damaged"

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "▸ 3. a normal machine is not punished for it"
# ═══════════════════════════════════════════════════════════════════════════
# THE RISK THIS GATE CREATES, tested rather than assumed: a surface an earlier
# run of THIS installation placed must be replaced without a word, or every
# re-install turns into a wall of refusals and the gate becomes the defect.
rm -rf "$HOME"; mkdir -p "$HOME/.claude"
install_run "clean1.log"
install_run "clean2.log"
n1="$(grep -c "OCCUPIED" "$LAB/clean1.log")"
n2="$(grep -c "OCCUPIED" "$LAB/clean2.log")"
[ "$n1" = "0" ] && ok "a first install on a clean machine refuses nothing" \
                || ko "a first install refused $n1 surface(s)"
[ "$n2" = "0" ] && ok "a second install over its own surfaces refuses nothing" \
                || ko "a re-install refused $n2 of its own surface(s)"
[ -L "$HOME/.claude/agents" ] \
  && ok "and the agents link is in place" \
  || ko "the agents link was never created"

echo
if [ "$fails" = "0" ]; then
  echo "✅ an occupied surface is named, and left to whoever owns it."
  exit 0
fi
echo "❌ $fails check(s) failed."
exit 1
