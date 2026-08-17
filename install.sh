#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# install.sh — installs C Brain. The SINGLE entry point.
#
# Three promises, kept by construction:
#   · IDEMPOTENT — re-running breaks nothing and duplicates nothing.
#   · NON-DESTRUCTIVE — anything already there is backed up before being touched.
#   · REVERSIBLE — every action is logged; ./uninstall.sh undoes them.
#
# Installed layout:
#   ~/.c-brain/engine  → link to THIS repo (the ENGINE: code, nothing else)
#   ~/.c-brain/trunk     → YOUR trunk (your notes). Never overwritten, never updated.
#
# Usage: ./install.sh [--core-only] [--no-launchd] [--no-capsule]
#                     [--no-planet] [--no-shortcut] [--dry-run]
#
#   --core-only  the memory alone: trunk, recall, agents, hooks, `brain`.
#                No capsule, no planet launcher, no scheduled jobs.
set -euo pipefail

ENGINE="$(cd "$(dirname "$0")" && pwd -P)"
TRUNK="$HOME/.c-brain/trunk"
CB="$HOME/.c-brain"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUPS="$CB/backups/$TS"
MANIFEST="$CB/manifest.txt"

DO_LAUNCHD=1; DO_CAPSULE=1; DO_SHORTCUT=1; DO_PLANET=1; DRY=0
for a in "$@"; do
  case "$a" in
    --no-launchd) DO_LAUNCHD=0 ;;
    --no-capsule) DO_CAPSULE=0 ;;
    --no-shortcut) DO_SHORTCUT=0 ;;
    # The memory, and nothing else: trunk, recall, agents, hooks, `brain`.
    # No Electron window, no 3D globe, no background job. Named as one option
    # because "install it without the ornaments" is a thing people want to ask
    # for in one go, and three flags they have to discover is not an answer.
    --core-only)  DO_LAUNCHD=0; DO_CAPSULE=0; DO_PLANET=0 ;;
    --no-planet)  DO_PLANET=0 ;;
    --dry-run)    DRY=1 ;;
    *) echo "Unknown option: $a"; exit 1 ;;
  esac
done

say()  { echo "  $*"; }
step() { echo; echo "▸ $*"; }
warn() { echo "  ⚠️  $*"; }
die()  { echo; echo "❌ $*"; exit 1; }

# Logs what we create, so uninstall knows what to undo.
note() { [ "$DRY" = "1" ] || { mkdir -p "$CB"; echo "$1|$2" >> "$MANIFEST"; }; }

# Back up before overwriting. User content never disappears.
save() {
  [ -e "$1" ] || return 0
  [ "$DRY" = "1" ] && { say "(dry-run) would back up $1"; return 0; }
  mkdir -p "$BACKUPS"
  cp -R "$1" "$BACKUPS/$(basename "$1")" 2>/dev/null || true
  say "backed up: $1 → $BACKUPS/"
}

run() { [ "$DRY" = "1" ] && { say "(dry-run) $*"; return 0; }; "$@"; }

# Places a symlink idempotently: already correct → nothing is touched.
link() {  # link <target> <link>
  local target="$1" path="$2"
  if [ -L "$path" ] && [ "$(readlink "$path")" = "$target" ]; then
    say "= $path (already linked)"; return 0
  fi
  if [ -e "$path" ] || [ -L "$path" ]; then
    save "$path"
    run rm -rf "$path"
  fi
  run mkdir -p "$(dirname "$path")"
  run ln -s "$target" "$path"
  note link "$path"
  say "+ $path → $target"
}

echo "🧠 C Brain — installation"
echo "   engine : $ENGINE"
echo "   trunk  : $TRUNK"
[ "$DRY" = "1" ] && echo "   (DRY-RUN: nothing will be written)"

# ─── 0. Prerequisites ────────────────────────────────────────────────────────
step "Prerequisites"
[ "$(uname)" = "Darwin" ] || die "C Brain targets macOS (launchd, Electron, \`open\`)."
command -v python3 >/dev/null || die "python3 is required (it runs every hook)."
say "python3 $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
command -v git >/dev/null || warn "git missing — \`brain update\` will not be able to pull updates."

HAS_CLAUDE_CODE=0
[ -d "$HOME/.claude" ] && HAS_CLAUDE_CODE=1
if [ "$HAS_CLAUDE_CODE" = "0" ]; then
  warn "~/.claude missing: Claude Code does not appear to be installed."
  warn "C Brain will still install, but WITHOUT the closed loop:"
  warn "the hooks (recall, archiving, maintenance) are specific to Claude Code."
  warn "You keep the \`brain\` CLI, the agents, the planet and the capsule."
fi

# ─── 1. C Brain root ────────────────────────────────────────────────────
step "C Brain root (~/.c-brain)"
run mkdir -p "$CB"
link "$ENGINE" "$CB/engine"
[ "$DRY" = "1" ] || { git -C "$ENGINE" describe --tags --always 2>/dev/null > "$CB/VERSION" || echo "untagged" > "$CB/VERSION"; }
# HANDS THE ENGINE OVER TO THE UPDATER — and only from a state that holds no work.
# `brain update` does destructive git on the engine (it checks out a release tag),
# and this file is what says it is allowed to. Written only when the repo is clean
# AND detached on a release tag, i.e. what an install looks like and what a
# development checkout does not: on 2026-08-17 an update rewound a working repo
# past four commits and detached its branch, because nothing recorded who owned it.
if [ "$DRY" != "1" ]; then
  mkdir -p "$CB/state"
  if [ -z "$(git -C "$ENGINE" status --porcelain --untracked-files=no 2>/dev/null)" ] \
     && [ "$(git -C "$ENGINE" rev-parse --abbrev-ref HEAD 2>/dev/null)" = "HEAD" ] \
     && git -C "$ENGINE" describe --tags --exact-match >/dev/null 2>&1; then
    printf '%s\n' "$ENGINE" > "$CB/state/engine-managed"
    note "file" "$CB/state/engine-managed"
  else
    rm -f "$CB/state/engine-managed"     # never vouch for a repo somebody works in
    say "engine is a working checkout — \`brain update\` will refuse to touch it"
  fi
fi
say "version: $(cat "$CB/VERSION" 2>/dev/null || echo '?')"

# ─── 2. The trunk ──────────────────────────────────────────────────────────
step "Trunk (~/.c-brain/trunk)"
if [ -d "$TRUNK" ]; then
  # A trunk exists. If it holds a REAL hooks/ folder (not a link), it is
  # a previous standalone install: we refuse to demolish it silently.
  if [ -d "$TRUNK/hooks" ] && [ ! -L "$TRUNK/hooks" ]; then
    die "$TRUNK/hooks is a REAL folder, not a link.
   There is already an old-style Brain installed here. I will not replace it on my own:
   its files might be yours. Back it up, then re-run:
     mv $TRUNK $TRUNK.before-c-brain && ./install.sh"
  fi
  say "= existing trunk kept (your notes are untouched)"
else
  run mkdir -p "$TRUNK"
  run cp -R "$ENGINE/skeleton/." "$TRUNK/"
  note dir "$TRUNK"
  say "+ trunk created from skeleton/ (empty, ready to grow)"
fi
run mkdir -p "$TRUNK/state" "$TRUNK/sessions/archive"

# ─── 3. The engine, linked into the trunk ────────────────────────────────────
# The list is NOT inline here any more: cbrain/engine-paths.txt is the single
# definition, also read by update.sh (to tell engine dirt from user work) and by
# brain_doctor (to report it). Three consumers, one list — see that file for why.
step "Engine linked into the trunk"
ENGINE_PATHS=$(grep -vE '^\s*(#|$)' "$ENGINE/cbrain/engine-paths.txt" 2>/dev/null)
[ -n "$ENGINE_PATHS" ] || ENGINE_PATHS="hooks agents capsule planet companion tests"
for d in $ENGINE_PATHS; do
  link "$CB/engine/$d" "$TRUNK/$d"
done

# ─── 4. The `brain` command ───────────────────────────────────────────────
step "The \`brain\` command"
link "$CB/engine/brain" "$HOME/.local/bin/brain"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) say "~/.local/bin is on PATH" ;;
  *) warn "~/.local/bin is NOT on your PATH. Add to your ~/.zshrc:"
     warn "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ─── 5. Agents visible to Claude Code ───────────────────────────────────
# Trap #1: without this link the agents exist but Claude Code cannot see
# them. No error, just an autonomous loop spinning on nothing.
step "Agents visible to the CLI agent"
if [ "$HAS_CLAUDE_CODE" = "1" ]; then
  link "$TRUNK/agents" "$HOME/.claude/agents"
else
  say "(skipped — ~/.claude missing)"
fi

# ─── 6. Hooks + status line ────────────────────────────────────────────────
step "Wiring the hooks"
if [ "$HAS_CLAUDE_CODE" = "1" ]; then
  if [ "$DRY" = "1" ]; then say "(dry-run) would merge ~/.claude/settings.json"
  else
    # No `save` here: merge_settings.py backs up ONLY when it actually writes.
    # Backing up every pass would stack a useless copy on every re-run.
    python3 "$ENGINE/merge_settings.py" install
    note settings "$HOME/.claude/settings.json"
  fi
  if [ -f "$ENGINE/statusline.py" ]; then
    save "$HOME/.claude/statusline.py"
    run cp "$ENGINE/statusline.py" "$HOME/.claude/statusline.py"
    note file "$HOME/.claude/statusline.py"
    say "+ status line installed"
  fi
else
  say "(skipped — no Claude Code: C Brain will work on demand)"
fi

# ─── 7. Capsule ───────────────────────────────────────────────────────────
step "Capsule (Electron window)"
capsule_ok() {  # does Electron ACTUALLY respond?
  local bin="$ENGINE/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
  # ⚠ The whole point is to run a binary that may be broken, and a half-extracted
  # Electron does not exit — it ABORTS. The shell then reports "Abort trap: 6" on
  # ITS OWN stderr, past the redirection on the command, so the install printed a
  # crash trace one line before announcing success. The subshell catches the
  # shell's own job report; the check itself is unchanged.
  [ -x "$bin" ] && ( "$bin" --version >/dev/null 2>&1 ) 2>/dev/null
}

# ─── Repairing an Electron that npm reported as installed ────────────────────
#
# MEASURED on 2026-08-17, macOS arm64, Node v26.5.0, npm 11.17:
#   · the archive downloads fine and `unzip -t` reports no error;
#   · electron's postinstall RUNS (`> electron@33.4.11 postinstall`), finishes in
#     ONE second, exits 0, prints nothing;
#   · with DEBUG=* it extracts 20 directory entries, reaches the first real file
#     ("opening read stream … electron.icns") and the process simply ends;
#   · `dist/` is left at 256 KB instead of ~250 MB, with no `Frameworks/` at all,
#     and `path.txt` — which electron writes only on success — is never created.
# So the binary exists, is executable, and dies with
# "Library not loaded: @rpath/Electron Framework.framework/Electron Framework".
# Reproduced identically on electron 42, so it is not the electron version: the
# node-side extraction is what broke. The system `unzip` reads the same archive
# without complaint and yields a runtime that answers `--version`.
#
# ⚠ This is a REPAIR, not an architecture. It uses the archive electron already
# downloaded, and does nothing that electron's own installer would not have done.
# The capsule's future is not more Electron plumbing, so this stays the smallest
# thing that makes a fresh install produce a window that opens.
capsule_repair() {
  local ed="$ENGINE/capsule/node_modules/electron" ver arch zip
  [ "$(uname -s)" = "Darwin" ] || return 1        # the only packaging we ship
  [ -d "$ed" ] || return 1
  command -v unzip >/dev/null 2>&1 || return 1
  ver="$(node -p "require('$ed/package.json').version" 2>/dev/null)" || return 1
  [ -n "$ver" ] || return 1
  case "$(uname -m)" in arm64) arch=arm64 ;; x86_64) arch=x64 ;; *) return 1 ;; esac
  # Where @electron/get puts what it downloaded, keyed by a hash we do not need
  # to recompute: the file name carries the version and the architecture.
  zip="$(find "$HOME/Library/Caches/electron" -name "electron-v$ver-darwin-$arch.zip" \
         -print 2>/dev/null | head -1)"
  [ -n "$zip" ] && [ -f "$zip" ] || return 1
  rm -rf "$ed/dist" && mkdir -p "$ed/dist" || return 1
  unzip -q "$zip" -d "$ed/dist" || return 1
  # ⚠ NO trailing newline. electron's `isInstalled()` compares this file to the
  # platform path with `!==`, so a stray "\n" makes every later `npm install`
  # decide the runtime is missing and run the broken download again.
  printf '%s' 'Electron.app/Contents/MacOS/Electron' > "$ed/path.txt"
}

if [ "$DO_CAPSULE" = "0" ]; then say "(skipped — --no-capsule)"
elif ! command -v npm >/dev/null; then
  # ⚠ THIS BRANCH USED TO BE ONE SILENT LINE, and it cost a first user about an
  # hour (install report, 2026-08-13, macOS Intel with no dev tooling). Told only
  # "npm missing", they went looking for Node themselves, landed on Homebrew —
  # which needs an interactive sudo, then recompiled openssl@3, xz, lz4 and cmake
  # FROM SOURCE for 38 minutes without ever reaching Node, with the fans at full
  # tilt. Every minute of that was avoidable: the official .pkg takes two.
  # Saying WHAT IS MISSING is not enough. A message that does not name the next
  # step sends the reader to invent one, and they invent the expensive one.
  warn "Node.js is missing — only the capsule (the floating orb) is skipped."
  say  "Everything else is installed and working: hooks, agents, memory, \`brain\`."
  say  "To get the orb later:"
  say  "  1. install Node with the OFFICIAL package — https://nodejs.org (macOS .pkg,"
  say  "     ~2 min, one password prompt, compiles nothing);"
  say  "  2. re-run this installer: it is idempotent, it will only add the capsule."
  say  "  (Homebrew works too, but on a machine without up-to-date Command Line Tools"
  say  "   it rebuilds its dependencies from source — count 40 min instead of 2.)"
  # Offered, never done behind their back: installing Node means an admin
  # password and a system-wide change. Asking costs one keypress; deciding for
  # them costs their trust. Only when a human is actually there to answer —
  # in a pipe or a CI this must not hang.
  if [ -t 0 ]; then
    printf "  Open the download page now? [y/N] "
    read -r rep || rep=""
    case "$rep" in
      [yYoO]*) open "https://nodejs.org/en/download" 2>/dev/null \
                 && say "→ page opened. Once Node is installed: re-run ./install.sh" \
                 || warn "could not open the browser — https://nodejs.org/en/download" ;;
      *) say "(not opened — the address is above)" ;;
    esac
  fi
elif [ "$DRY" = "1" ]; then say "(dry-run) would install the capsule dependencies"
elif capsule_ok; then say "= capsule already working"
else
  say "npm install (Electron, ~1 min)…"
  npm --prefix "$ENGINE/capsule" install --silent >/dev/null 2>&1 || true
  # `npm install` exits SUCCESSFULLY even when the Electron binary was never
  # extracted (archive truncated by @electron/get — a trap already hit). Trusting
  # the exit code would report a capsule as installed while it cannot start.
  # So we check the binary itself.
  if capsule_ok; then
    say "+ capsule working ($("$ENGINE/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" --version 2>/dev/null))"
    # npm 11 prints `warn allow-scripts ... electron (postinstall: node install.js)`
    # here. It reads like a failure, and it worried the first outside user enough
    # to be logged in their report. It is not one — and we are in a position to
    # PROVE it, since capsule_ok has just started the actual binary.
    say "  (npm's \"allow-scripts\" warning above is benign: Electron did start,"
    say "   which is what the line above checks — the binary, not npm's exit code.)"
  elif capsule_repair && capsule_ok; then
    # The remedy this branch used to PRINT was the very thing that had just
    # failed — `npm install` again, which re-runs the extraction that dies. A
    # remedy that cannot work is worse than none: it sends the reader round the
    # loop and lets us call the capsule "known flaw, not ours" while a fresh
    # install ships a window that never opens.
    say "+ capsule repaired and working ($("$ENGINE/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" --version 2>/dev/null))"
    say "  (electron's own extraction stopped at the first file and exited 0;"
    say "   the archive it had already downloaded was unpacked with unzip.)"
  else
    warn "The Electron binary does not respond, and the archive could not be unpacked."
    warn "The capsule (the floating orb) will not open. Everything else works."
    warn "To retry by hand:"
    warn "  rm -rf $ENGINE/capsule/node_modules && npm --prefix $ENGINE/capsule install"
    warn "  then re-run this installer — it will unpack what npm downloaded."
  fi
fi

# ─── 8. Scheduled jobs ─────────────────────────────────────────────────
step "Scheduled jobs (launchd)"
if [ "$DO_LAUNCHD" = "0" ]; then say "(skipped — --no-launchd)"
else
  run mkdir -p "$HOME/Library/LaunchAgents"
  for t in resume machiniste; do
    tpl="$ENGINE/hooks/com.claudebrain.$t.plist.template"
    [ -f "$tpl" ] || continue
    out="$HOME/Library/LaunchAgents/com.claudebrain.$t.plist"
    if [ "$DRY" = "1" ]; then say "(dry-run) would generate $out"; continue; fi
    # __HOME__ substituted here: a hardcoded path in a .plist is THE bug that
    # silently breaks an install on another machine.
    sed "s|__HOME__|$HOME|g" "$tpl" > "$out"
    note file "$out"
    launchctl unload "$out" 2>/dev/null || true
    launchctl load "$out" 2>/dev/null && say "+ com.claudebrain.$t loaded" \
      || warn "com.claudebrain.$t generated but not loaded (launchctl refused)"
  done
fi

# ─── 9. Planet launcher ─────────────────────────────────────────────
# AN APP BUNDLE, NOT A `.command`. Both are one double-click, but only a bundle
# can carry an icon: a `.command` takes one solely through its resource fork,
# which on macOS is set with `Rez` — from the Xcode Command Line Tools, exactly
# what the machine in the 2026-08-13 install report did not have. An icon that
# only appears on machines already equipped for development is not an icon.
# A bundle is plain files: it works on a bare machine, shows up in the Dock while
# the planet is serving, and quitting it stops the server.
#
# The icon itself: `planet/planete.icns`, generated from the planet's OWN colours
# (#07070b ground, #5ad7e6 accent) — see tools/icone-planete.py in the author's
# trunk, which redraws it with the standard library alone.
step "Planet launcher (Desktop)"
APP="$HOME/Desktop/C Brain Planet.app"
OLD_CMD="$HOME/Desktop/Planete-C-Brain.command"
if [ "$DO_PLANET" = "0" ]; then say "(skipped — --core-only)"
elif [ "$DRY" = "1" ]; then say "(dry-run) would create $APP"
elif [ -d "$HOME/Desktop" ]; then
  run rm -rf "$APP"                       # idempotent: rebuilt whole, never patched
  run mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  if [ "$DRY" != "1" ]; then
    # The GUI hands a launched app a minimal PATH — python3 and `open` have to be
    # findable, or the double-click does nothing at all and says nothing either.
    printf '#!/bin/bash\nexport PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"\nexec "%s/planet/launch.sh"\n' "$TRUNK" > "$APP/Contents/MacOS/planet"
    chmod +x "$APP/Contents/MacOS/planet"
    cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>C Brain Planet</string>
  <key>CFBundleDisplayName</key><string>C Brain Planet</string>
  <key>CFBundleIdentifier</key><string>org.cbrain.planet</string>
  <key>CFBundleExecutable</key><string>planet</string>
  <key>CFBundleIconFile</key><string>planete</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
</dict></plist>
PLIST
    if [ -f "$ENGINE/planet/planete.icns" ]; then
      cp "$ENGINE/planet/planete.icns" "$APP/Contents/Resources/planete.icns"
    else
      warn "planete.icns missing — the launcher works, with the generic icon."
    fi
    # Finder caches an app's icon by path+mtime. Without this touch, a rebuilt
    # bundle keeps showing the previous icon until the next log-out.
    touch "$APP"
  fi
  note dir "$APP"
  say "+ $APP (double-click → globe on localhost:8765)"
  # An installer that leaves the previous version's shortcut behind hands the
  # user two icons for one action, and lets them pick the stale one.
  if [ -f "$OLD_CMD" ]; then
    run rm -f "$OLD_CMD"
    say "- Planete-C-Brain.command removed (replaced by the app above)"
  fi
else
  warn "~/Desktop not found — launcher not created. The planet stays reachable at:"
  warn "  $TRUNK/planet/launch.sh"
fi

# ─── 10. Making the trunk findable ────────────────────────────────────────
# The trunk lives at ~/.c-brain/trunk. The leading dot keeps the plumbing out
# of the way — and hides the one part of this that is YOURS. A new user gets a
# memory they cannot see, in a folder Finder refuses to show. So we put a
# visible door on it.
#
# NOT the Finder sidebar: it is stored in a binary .sfl4 plist with no
# supported API, and the only way in is a third-party binary. Adding a
# dependency to place an icon is not a trade worth making — dragging the folder
# into Favourites takes the user two seconds, and we say so below.
step "Making your memory findable"
SHORTCUT="$HOME/C Brain"
if [ "$DO_SHORTCUT" = "0" ]; then say "(skipped — --no-shortcut)"
elif [ "$DRY" = "1" ]; then say "(dry-run) would create $SHORTCUT and tag the trunk"
else
  if [ -L "$SHORTCUT" ] && [ "$(readlink "$SHORTCUT")" = "$TRUNK" ]; then
    say "= $SHORTCUT (already there)"
  elif [ -e "$SHORTCUT" ]; then
    warn "$SHORTCUT exists and is not our shortcut — left alone"
  else
    ln -s "$TRUNK" "$SHORTCUT"
    note shortcut "$SHORTCUT"
    say "+ $SHORTCUT → your notes, visible in Finder"
  fi
  # A Finder tag, so the folder is recognisable at a glance among thirty others.
  python3 - "$TRUNK" <<'PY' 2>/dev/null || true
import plistlib, subprocess, sys
blob = plistlib.dumps(["C Brain\n6"], fmt=plistlib.FMT_BINARY)   # 6 = red
subprocess.run(["xattr", "-w", "-x", "com.apple.metadata:_kMDItemUserTags",
                blob.hex(), sys.argv[1]], check=True)
PY
  say "  Tip: drag it into the Finder sidebar once — it stays there."
fi

# ─── 11. Verification ─────────────────────────────────────────────────────
step "Verification"
if [ "$DRY" = "1" ]; then say "(dry-run) would run the selftest"
else
  if bash "$TRUNK/hooks/selftest.sh" >/tmp/c-brain-selftest.log 2>&1; then
    say "✅ selftest OK — every hook healthy"
  else
    warn "selftest failed — details: /tmp/c-brain-selftest.log"
    tail -5 /tmp/c-brain-selftest.log | sed 's/^/     /'
  fi
  python3 "$TRUNK/hooks/brain_doctor.py" --quiet >/dev/null 2>&1 \
    && say "✅ doctor — tree consistent" || say "ℹ️  doctor flags a few things to look at (\`brain doctor\`)"
fi

echo
echo "✅ C Brain installed."
echo
# Offered FIRST, not as a footnote: an empty trunk on first launch shows nothing
# of what the tool can do. That is the screen where people give up.
#
# ⚠️ BUT ONLY IF IT IS ACTUALLY EMPTY. There used to be no test at all: the block
# fired on every install, re-installs included. Reported 2026-08-16 (Maissane
# Lagsir) on a machine where it announced an empty trunk holding 23 notes — and
# then offered `brain demo`, which injects demo notes into a live trunk. Telling
# someone their knowledge is gone, then handing them the command that writes into
# it, is the worst possible pairing.
TRUNK_VIDE=1
for z in projects lessons meta life; do
  if [ -n "$(find "$TRUNK/$z" -name '*.md' -print -quit 2>/dev/null)" ]; then
    TRUNK_VIDE=0; break
  fi
done
if [ "$TRUNK_VIDE" = "1" ]; then
  echo "   ▸ Your trunk is empty. To see it working:"
  echo "       brain demo                place 3 example notes"
  echo "       brain recall cache        what recall finds"
  echo "       brain demo --remove       take them away, leaving no trace"
else
  echo "   ▸ Your trunk is already growing. Where it stands:"
  echo "       brain doctor              is the tree consistent"
  echo "       brain recall <subject>    what it remembers"
fi
echo
echo "   brain status     where the trunk stands"
# Said HERE, before they run it: right after an install, `brain status` reports
# "busy / gardening". That is the first maintenance pass, and it is normal — but
# a first user reads a machine that says "busy" for no reason as a crash. Reported
# as such in the install report of 2026-08-13.
echo "                    (\"busy / gardening\" just after installing is the first"
echo "                     tidy-up pass — it is normal, and it ends on its own)"
echo "   brain recall <q> search your memory"
echo "   brain doctor     tree health"
echo "   brain selftest   re-check the installation"
echo
[ "$HAS_CLAUDE_CODE" = "1" ] \
  && echo "   Restart your CLI session for the hooks to take effect." \
  || echo "   Without Claude Code: no closed loop, but the whole CLI is there."
echo "   Uninstall: $ENGINE/uninstall.sh"
