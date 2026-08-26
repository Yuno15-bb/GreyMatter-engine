#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# uninstall.sh — undoes what install.sh did, and NOTHING else.
#
# Absolute rule: **your trunk is never deleted**. Your notes are your work, not a
# dependency of C Brain. The trunk loses its links to the engine; it keeps all of
# its content.
#
# Usage: ./uninstall.sh [--yes] [--purge-engine]
set -euo pipefail

# ⚠ CANONICAL, on the SAME rule as install.sh — and it has to be, because the two
# compare strings. The installer resolves $HOME with `pwd -P` before writing the
# Finder shortcut, so the link holds `/private/var/…` wherever $HOME goes through
# a symlink (every `mktemp -d` on macOS, and the CI runner). Uninstall read
# `$HOME/.c-brain/trunk` unresolved, the two spellings of the same directory did
# not match, and the uninstaller decided the shortcut IT had just made belonged
# to somebody else and left it behind. install.sh already carries this warning
# for the ownership record; this is the same trap, one file further on.
CB="$HOME/.c-brain"
if [ -d "$CB" ]; then
  CB="$(cd "$CB" && pwd -P)"
else
  CB="$(cd "$HOME" 2>/dev/null && pwd -P || echo "$HOME")/.c-brain"
fi
TRUNK="$CB/trunk"
MANIFEST="$CB/manifest.txt"

ASSUME_YES=0; PURGE_ENGINE=0
for a in "$@"; do
  case "$a" in
    --yes) ASSUME_YES=1 ;;
    --purge-engine) PURGE_ENGINE=1 ;;
    *) echo "Unknown option: $a"; exit 1 ;;
  esac
done

say() { echo "  $*"; }

echo "🧠 C Brain — uninstall"
echo
echo "  Will be removed:"
echo "    · the C Brain hooks from ~/.claude/settings.json (the rest untouched)"
echo "    · the engine links inside $TRUNK (hooks, agents, capsule, planet, companion, tests)"
echo "    · ~/.local/bin/brain, the Desktop launcher, the Finder shortcut, the launchd jobs"
echo
echo "  Will be KEPT:"
echo "    · $TRUNK and ALL your notes"
echo "    · the backups in $CB/backups/"
echo

if [ "$ASSUME_YES" = "0" ]; then
  printf "  Continue? [y/N] "
  read -r ans
  case "$ans" in y|Y|o|O) ;; *) echo "  Cancelled."; exit 0 ;; esac
fi

# ─── 1. Hooks ─────────────────────────────────────────────────────────────
echo
echo "▸ Hooks"
if [ -f "$HOME/.claude/settings.json" ] && [ -f "$CB/engine/merge_settings.py" ]; then
  python3 "$CB/engine/merge_settings.py" remove
else
  say "(settings.json or merge_settings.py missing — nothing to do)"
fi

# ─── 2. Scheduled jobs ────────────────────────────────────────────────────
echo
echo "▸ Scheduled jobs"
# FAIL CLOSED. Without the library there is no way to tell our jobs from
# somebody else's, and the safe answer to "whose is this?" is to leave it.
if [ -f "$CB/engine/cbrain/launchd-lib.sh" ]; then
  . "$CB/engine/cbrain/launchd-lib.sh"
  for t in resume machiniste; do
    label="com.claudebrain.$t"
    p="$HOME/Library/LaunchAgents/$label.plist"
    if [ -f "$p" ] || cb_launchd_registered "$label"; then
      cb_launchd_uninstall "$label" "$p" || :
    fi
  done
else
  say "(cbrain/launchd-lib.sh missing — the launchd jobs are LEFT ALONE:"
  say " removing them would mean touching identities this script cannot prove are ours)"
fi

# ─── 3. Links ─────────────────────────────────────────────────────────────
# We delete symlinks ONLY. If something has become a real folder, that is
# content — we leave it alone.
echo
echo "▸ Engine links"
for d in hooks agents capsule planet companion tests; do
  p="$TRUNK/$d"
  if [ -L "$p" ]; then rm -f "$p"; say "- $p"
  elif [ -e "$p" ]; then say "! $p is not a link — left in place (that is content)"; fi
done
for p in "$HOME/.claude/agents" "$HOME/.local/bin/brain"; do
  if [ -L "$p" ]; then rm -f "$p"; say "- $p"; fi
done

# ─── 4. Odds and ends ─────────────────────────────────────────────────────
echo
echo "▸ Odds and ends"
[ -f "$HOME/Desktop/Planete-C-Brain.command" ] && { rm -f "$HOME/Desktop/Planete-C-Brain.command"; say "- Desktop launcher (old .command)"; }
# The launcher became an app bundle on 2026-08-14 — a DIRECTORY, so `rm -f` walks
# straight past it. An uninstaller that leaves a launcher on the Desktop leaves
# the impression the tool is still installed, and the icon still points at a
# trunk we may just have unlinked.
[ -d "$HOME/Desktop/C Brain Planet.app" ] && { rm -rf "$HOME/Desktop/C Brain Planet.app"; say "- Desktop launcher (C Brain Planet.app)"; }

# The Finder shortcut: a symlink we made, removed only if it still points at
# the trunk. If the user re-aimed it somewhere, it stopped being ours.
SHORTCUT="$HOME/C Brain"
if [ -L "$SHORTCUT" ] && [ "$(readlink "$SHORTCUT")" = "$TRUNK" ]; then
  rm -f "$SHORTCUT"; say "- $SHORTCUT"
elif [ -e "$SHORTCUT" ]; then
  say "! $SHORTCUT is not our shortcut — left in place"
fi
# …and the tag we put on the folder. Cosmetic, but we added it, so we take it back.
xattr -d com.apple.metadata:_kMDItemUserTags "$TRUNK" 2>/dev/null && say "- Finder tag on the trunk" || true

# Deterministic rule: if the file is IDENTICAL to the engine's, it is ours →
# remove it. If it differs, it is the user's (pre-existing or since edited) →
# do not touch it.
SL="$HOME/.claude/statusline.py"
if [ -f "$SL" ]; then
  if [ -f "$CB/engine/statusline.py" ] && cmp -s "$SL" "$CB/engine/statusline.py"; then
    rm -f "$SL"; say "- ~/.claude/statusline.py (ours, byte for byte)"
  else
    say "! ~/.claude/statusline.py differs from ours — left in place (it is yours)"
  fi
fi

# ─── 5. Engine ────────────────────────────────────────────────────────────
echo
echo "▸ Engine"
if [ "$PURGE_ENGINE" = "1" ]; then
  rm -f "$CB/engine" "$MANIFEST" "$CB/VERSION"
  # ⚠ THIS CAN NOW ACTUALLY DELETE THE ENGINE, and it could not before. While
  # `~/.c-brain/engine` was a link to the user's own clone, the only honest thing
  # to remove was the link — deleting the target would have deleted a repository
  # somebody else made. Since 2026-08-17 the installer BUILDS what it mounts:
  # `versions/`, the source mirror and the shared Electron runtime are all ours,
  # so `--purge-engine` finally removes what its name promises.
  #
  # The user's clone is still never touched. It was a source, it stays a source.
  for d in "$CB/versions" "$CB/source.git" "$CB/runtime"; do
    [ -e "$d" ] || continue
    rm -rf "$d" && say "- $(basename "$d") removed (built by the installer)"
  done
  rm -f "$CB/state/engine-managed" "$CB/state/engine-dev" "$CB/state/previous-version"
  say "  (the repository you cloned is untouched — it was the source, not the engine)"
else
  say "= $CB kept (versions + backups). Use --purge-engine to wipe it."
fi

echo
echo "✅ Uninstalled. $TRUNK and your notes are intact."
echo "   Backups: $CB/backups/"
