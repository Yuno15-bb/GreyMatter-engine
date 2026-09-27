#!/usr/bin/env bash
# 002-rename-root.sh — the root `~/.c-brain` becomes `~/.greymatter`, plus a
# permanent compatibility link at the old location.
#
# Why: the product is called GreyMatter everywhere (decision of 2026-09-27). The
# old name survived only in the paths, and a folder named after something that
# no longer exists is the first thing a new user cannot explain.
#
# Same shape as 001: it only MOVES. The rewiring — engine link, settings.json,
# launchd jobs, the `brain` command, the home shortcut — is redone right after by
# install.sh, which every update calls anyway.
#
# It runs from three places, which is why it must be harmless on replay:
#   · an updater of this generation, from greymatter/migrations/;
#   · an updater from BEFORE the rename (v2.0.x), which only looks in
#     cbrain/migrations/ — the forwarding stub there exists for that alone;
#   · plugin_bootstrap.py, at every session start of a plugin install.
set -euo pipefail

OLD="$HOME/.c-brain"        # pre-rename root
NEW="$HOME/.greymatter"

real() { (cd "$1" 2>/dev/null && pwd -P) || true; }

# Nothing at the old place: a fresh machine, or already migrated and the
# compatibility link removed by hand. Either way there is nothing to move.
if [ ! -e "$OLD" ] && [ ! -L "$OLD" ]; then
  echo "  nothing to move (no ~/.c-brain)"
  exit 0
fi

# Already migrated: the old place leads to the new one.
if [ -e "$NEW" ] && [ "$(real "$OLD")" = "$(real "$NEW")" ]; then
  echo "  already migrated (~/.c-brain → ~/.greymatter)"
  exit 0
fi

# Two different roots. Picking one would silently hide the other's notes: stop.
if [ -e "$NEW" ] || [ -L "$NEW" ]; then
  echo "  ✗ both ~/.c-brain and ~/.greymatter exist, and they are different folders." >&2
  echo "    Nothing was moved. Keep the one holding your notes, move the other aside," >&2
  echo "    then run the update again." >&2
  exit 1
fi

if [ -L "$OLD" ]; then
  # The root was itself a link (a trunk kept on another volume): the new name
  # points where the old one pointed, and the old one then points at the new.
  ln -s "$(readlink "$OLD")" "$NEW"
  rm "$OLD"
else
  mv "$OLD" "$NEW"
fi
ln -s "$NEW" "$OLD"

# Checked, not assumed: the old path must still lead to the same notes.
[ "$(real "$OLD")" = "$(real "$NEW")" ] || { echo "  ✗ compatibility link does not resolve" >&2; exit 1; }
echo "  ~/.c-brain → ~/.greymatter (the old path stays valid, as a link)"
