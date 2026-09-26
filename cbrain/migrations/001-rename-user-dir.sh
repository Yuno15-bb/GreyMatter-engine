#!/usr/bin/env bash
# 001-rename-user-dir.sh — ~/claude-brain becomes ~/.c-brain/trunk.
#
# WHY. The user directory of a public product was called "claude-brain": an
# Anthropic trademark in a name C Brain creates on other people's machines, and
# a fourth name for a single thing (C Brain, c-brain, ~/claude-brain,
# ~/.c-brain/engine). After this: ONE root, ~/.c-brain, engine and trunk side
# by side.
#
#   before                       after
#   ~/.c-brain/engine  (code)    ~/.c-brain/engine  (code, unchanged)
#   ~/claude-brain     (notes)   ~/.c-brain/trunk   (notes, moved here)
#                                ~/claude-brain     → link to trunk (compatibility)
#
# WHAT IT DOES NOT DO. It touches no note, renames nothing INSIDE the trunk,
# restarts no service. The rewiring (engine symlinks, settings.json, launchd
# plists, Desktop launcher) is redone right after by install.sh, which update.sh
# always calls. Here we move — nothing else.
set -euo pipefail

OLD="$HOME/claude-brain"
NEW="$HOME/.c-brain/trunk"

say() { echo "  $*"; }

# ─── Case 1: already migrated ─────────────────────────────────────────────
# The migration log can disappear (restore, new machine). A replayed migration
# must be a non-event, not an error.
if [ -L "$OLD" ] && [ -d "$NEW" ]; then
  say "already migrated — trunk is at $NEW, $OLD is the compatibility link"
  exit 0
fi

# ─── Case 2: nothing to move ──────────────────────────────────────────────
if [ ! -e "$OLD" ]; then
  if [ -d "$NEW" ]; then
    say "nothing to move — the trunk is already at $NEW"
  else
    say "no trunk found — install.sh will create one at $NEW"
  fi
  exit 0
fi

# ─── Case 3: collision ────────────────────────────────────────────────────
# Two real trunks, each with notes in it. Merging blindly would decide, on the
# user's behalf, which one wins. We stop instead: a hard stop gets fixed, a
# silent merge gets discovered three weeks later.
if [ -d "$NEW" ] && [ ! -L "$OLD" ]; then
  echo "❌ Two trunks coexist:"
  echo "     $OLD  ($(find "$OLD" -name '*.md' 2>/dev/null | wc -l | tr -d ' ') notes)"
  echo "     $NEW  ($(find "$NEW" -name '*.md' 2>/dev/null | wc -l | tr -d ' ') notes)"
  echo "   I will not merge them for you: these are your notes."
  echo "   Pick the one to keep, move the other aside, then run \`brain update\` again."
  exit 1
fi

# ─── The move ─────────────────────────────────────────────────────────────
mkdir -p "$HOME/.c-brain"

# `mv` of a directory into an empty directory on the SAME volume: atomic,
# instant, and it preserves the trunk's .git — so the notes keep their history.
mv "$OLD" "$NEW"
say "trunk moved: $OLD → $NEW"

# Compatibility link. C Brain does not need it (nothing targets the old path any
# more) but EVERYTHING ELSE might: the CLI agent's memory link, the user's own
# scripts, their bookmarks, a git remote written down somewhere. Without it, the
# migration breaks things no test in here knows about.
ln -s "$NEW" "$OLD"
say "compatibility link in place: $OLD → $NEW"

# Executed check, not assumed: the link must resolve onto a real directory.
[ -d "$OLD/." ] || { echo "❌ $OLD does not resolve after migration"; exit 1; }
say "verified — both paths lead to the same trunk"
