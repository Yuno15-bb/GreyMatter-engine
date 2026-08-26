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
#   ~/.c-brain/versions/<id>/  an ENGINE: an immutable export of the source
#   ~/.c-brain/engine          → link to the ACTIVE version. Switching is one symlink.
#   ~/.c-brain/source.git      the mirror updates are fetched into
#   ~/.c-brain/runtime/        the Electron runtime, installed once and shared
#   ~/.c-brain/trunk           YOUR trunk (your notes). Never overwritten, never updated.
#
# THIS REPOSITORY IS THE SOURCE, NOT THE ENGINE. The installer reads it to build
# a version and never writes to it again — see docs/install-model.md.
#
# Usage: ./install.sh [--core-only] [--no-launchd] [--no-capsule]
#                     [--no-planet] [--no-shortcut] [--dry-run] [--dev]
#
#   --core-only  the memory alone: trunk, recall, agents, hooks, `brain`.
#                No capsule, no planet launcher, no scheduled jobs.
#   --dev        link the engine to THIS checkout instead of building a version,
#                and switch automatic updates off for it. For working on C Brain.
set -euo pipefail

# WHERE THIS SCRIPT WAS RUN FROM — the SOURCE. It is read to build an engine and
# is never written to. It is not the engine, and after 2026-08-17 it never is
# again unless --dev says so explicitly.
SOURCE="$(cd "$(dirname "$0")" && pwd -P)"
# ⚠ CANONICAL, and it matters. `$HOME` may contain a symlink — on macOS every
# `mktemp -d` path does, `/var` being a link to `/private/var`. The installer
# records ownership as a path and the updater compares the engine against it
# with `pwd -P`, so one side resolved and the other not made a legitimate
# install look like somebody else's directory. Caught by the end-to-end test on
# its first run, which is precisely the kind of gap no component test can see.
# ⚠ AND IT CREATES NOTHING. Canonicalising by `mkdir -p` then `cd` ran BEFORE
# the flags were parsed, so `--dry-run` — whose whole contract is to be inert —
# left a `~/.c-brain` behind on a machine that had never installed anything, and
# the CI step that checks exactly that went red. Resolving $HOME and appending
# the name gives the same canonical path without writing: the symlink that has
# to be resolved on macOS (`/var` → `/private/var`) is in $HOME, not in the last
# component. The `cd "$CB"` branch is kept for the case the plain concatenation
# cannot cover — a `~/.c-brain` that is itself a link somewhere else.
CB="$HOME/.c-brain"
if [ -d "$CB" ]; then
  CB="$(cd "$CB" && pwd -P)"
else
  CB="$(cd "$HOME" 2>/dev/null && pwd -P || echo "$HOME")/.c-brain"
fi
TRUNK="$CB/trunk"
VERSIONS="$CB/versions"
RUNTIME="$CB/runtime"
MIRROR="$CB/source.git"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUPS="$CB/backups/$TS"
MANIFEST="$CB/manifest.txt"

DO_LAUNCHD=1; DO_CAPSULE=1; DO_SHORTCUT=1; DO_PLANET=1; DRY=0; DEV=0
for a in "$@"; do
  case "$a" in
    # The ONLY mode in which an engine may be a working checkout, and it has to
    # be asked for by name. Everything the updater could do destructively is
    # switched off for this install: a development repo is somebody's work, and
    # no amount of inspection can tell it apart from an install after the fact.
    --dev) DEV=1 ;;
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

# Building, verifying and mounting a version — shared with cbrain/update.sh so
# that the installer and the updater cannot disagree on what a version is.
. "$SOURCE/cbrain/engine-lib.sh"
. "$SOURCE/cbrain/launchd-lib.sh"

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
echo "   source : $SOURCE"
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

# ─── 1. C Brain root, and the ENGINE this install will own ───────────────────
#
# A SOURCE IS NOT AN ENGINE. Until 2026-08-17 `~/.c-brain/engine` was a link to
# the very clone the user had just made, and ownership was INFERRED from that
# clone's git state: clean, detached, exactly on a release tag. The trouble is
# that `git clone` never produces that state — it lands on a branch — so the
# documented install produced an engine `brain update` refused for ever, while a
# developer's clean checkout sitting on a tag was adopted as if it were an
# install. Inference cannot answer "whose repository is this?", and never could.
#
# So the installer stops guessing and starts BUILDING. It exports the source into
# `versions/<id>/`, an immutable tree with no `.git` and no history, and points
# `engine` at it. What it created, it owns; what the user created, it never
# touches again. The engine can be replaced, rolled back and thrown away without
# a single git command ever naming a directory somebody works in.
step "C Brain root (~/.c-brain)"
run mkdir -p "$CB" "$CB/state"
# What the engine pointed at BEFORE this run — read now, because we are about to
# repoint it. Used only to tell a converting installation what just happened.
PREVIOUS_ENGINE="$(cd "$CB/engine" 2>/dev/null && pwd -P || true)"

# The version identity, read off the source. A tagged checkout gives `v1.29.0`;
# a plain clone of `main` gives `v1.28.1-24-g6f28312`. Both are legitimate names
# for a version directory — which is precisely what makes the DOCUMENTED
# `git clone && ./install.sh` produce an updatable install with no extra gesture
# from the user, and no change to a single line of INSTALL.md.
if git -C "$SOURCE" rev-parse --git-dir >/dev/null 2>&1; then
  VERSION_ID="$(git -C "$SOURCE" describe --tags --always 2>/dev/null || echo "untagged")"
  [ -n "$(git -C "$SOURCE" status --porcelain --untracked-files=no 2>/dev/null)" ] \
    && VERSION_ID="$VERSION_ID-dirty"
else
  # Downloaded as a zip rather than cloned: no history to name it by. Datestamp
  # it and say so — an install must not fail because the user chose the button
  # instead of the command.
  VERSION_ID="src-$TS"
fi

# ─── ALREADY AN ENGINE ───────────────────────────────────────────────────────
# `update.sh` replays this script FROM the version it has just built, and every
# successful update ends by doing so. Run from inside `versions/`, there is
# nothing to build: the tree we would build from is the tree we are standing in,
# and it has no `.git` to export from anyway. So we mount and move on. Without
# this branch the replay would try to rebuild an engine out of a non-repository
# and fail on every single update.
case "$SOURCE" in
  "$VERSIONS"/*) ALREADY_A_VERSION=1 ;;
  *)             ALREADY_A_VERSION=0 ;;
esac

if [ "$ALREADY_A_VERSION" = "1" ]; then
  ENGINE="$SOURCE"
  VERSION_ID="$(basename "$SOURCE")"
  say "= running from versions/$VERSION_ID — mounting it, nothing to build"
elif [ "$DEV" = "1" ]; then
  # ─── DEVELOPMENT ENGINE ────────────────────────────────────────────────────
  # Linked to the checkout, exactly as installs behaved before this change, and
  # marked as such so the updater refuses to run destructive git against it.
  # The marker is a FILE, not a deduction: nothing about this repo has to look
  # different from an install for it to be protected.
  ENGINE="$SOURCE"
  if [ "$DRY" != "1" ]; then
    printf '%s\n' "$SOURCE" > "$CB/state/engine-dev"
    rm -f "$CB/state/engine-managed"          # the two are mutually exclusive
    note "file" "$CB/state/engine-dev"
  fi
  say "DEVELOPMENT engine — $SOURCE"
  say "automatic engine updates are OFF for this install (\`brain update\` will say so)"
else
  # ─── MANAGED ENGINE ────────────────────────────────────────────────────────
  ENGINE="$VERSIONS/$VERSION_ID"
  if [ "$DRY" = "1" ]; then
    say "(dry-run) would build $ENGINE from $SOURCE"
  else
    mkdir -p "$VERSIONS"
    if [ -f "$ENGINE/.cbrain-manifest" ] && verify_manifest "$ENGINE" >/dev/null 2>&1; then
      say "= $VERSION_ID already installed and intact"
    else
      build_version "$SOURCE" "$ENGINE" || die "could not build the engine $VERSION_ID from $SOURCE"
      say "+ engine built: versions/$VERSION_ID ($(find "$ENGINE" -type f ! -name .cbrain-manifest | wc -l | tr -d ' ') files)"
    fi
    # The mirror the updater fetches into. It exists so that NO git command in
    # the update path ever names a directory the user created.
    mirror_source "$SOURCE" "$MIRROR"
    # ─── SAY IT, AT THE ONE MOMENT IT IS TRUE ────────────────────────────────
    # An installation upgrading from v1.28.1 or earlier arrives here with
    # `engine` still pointing at the user's own clone, and leaves with it
    # pointing at a built version. That is a change in what their checkout IS,
    # and it happens inside an automatic update they did not watch. Saying so
    # here puts the explanation in the update log, next to the moment it applies
    # — docs/UPGRADING.md is where they would have to already suspect something
    # to go looking.
    if [ -n "${PREVIOUS_ENGINE:-}" ] && [ "$PREVIOUS_ENGINE" != "${ENGINE%/*}" ]; then
      case "$PREVIOUS_ENGINE/" in
        "$VERSIONS"/*) : ;;   # already a managed install, nothing to announce
        *)
          say "converted: your checkout is now a SOURCE, not the engine"
          say "  was:  $PREVIOUS_ENGINE (a git checkout C Brain used directly)"
          say "  now:  $ENGINE (built here, replaceable, never your repository)"
          say "  \`brain update\` will not touch $PREVIOUS_ENGINE again — see docs/UPGRADING.md"
          ;;
      esac
    fi
    # OWNERSHIP AS PROVENANCE, not as a verdict on a git state: this file says
    # "the installer built the tree under versions/ and may replace it". It names
    # the versions root rather than one version, because the whole point is that
    # the active version changes.
    printf '%s\n' "$VERSIONS" > "$CB/state/engine-managed"
    rm -f "$CB/state/engine-dev"
    note "file" "$CB/state/engine-managed"
  fi
fi

link "$ENGINE" "$CB/engine"
[ "$DRY" = "1" ] || printf '%s\n' "$VERSION_ID" > "$CB/VERSION"
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

# ─── LOCAL VERSION HISTORY ───────────────────────────────────────────────────
#
# ⚠️ THIS IS NOT A BACKUP. It is a local history, on this disk, in this trunk. If
# the disk dies it dies with it. The package pushes nowhere and never will on its
# own — a user who puts a remote on their trunk did not ask for their notes to
# leave at every session end. Say "history", never "backup", or the word does the
# promising.
#
# WHY IT IS CREATED HERE. `hooks/commit_par_zone.py` — the per-zone auto-save
# that runs at the end of every session — begins with "is this a git repo?" and
# returns 0 when it is not, printing one line into a log nobody reads. Its own
# comment called that "the normal case: nobody ran `git init`". So on a default
# install the shipped protection was INERT, silently, for everyone: the notes
# were on disk, and nothing kept a history of them. `brain doctor` said so, but
# only to whoever ran it and read to the end.
#
# ⚠️ TRUNK GIT IS NOT ENGINE GIT. The ownership gate added to `brain update`
# reasons about the ENGINE repo. This one is the user's notes, it has no remote,
# no tag and no upstream, and nothing about updating may ever look at it.
if [ "$DRY" != "1" ] && [ ! -e "$TRUNK/.git" ]; then
  if ! command -v git >/dev/null 2>&1; then
    warn "git is missing — local version history is OFF."
    warn "Your notes are still saved as files; nothing keeps their history."
    warn "Install git, then re-run this installer to turn it on."
  elif git -C "$TRUNK" init -q >/dev/null 2>&1 \
       && git -C "$TRUNK" add -A >/dev/null 2>&1 \
       && git -C "$TRUNK" -c user.email=c-brain@localhost -c user.name="C Brain" \
              commit -qm "the trunk, as installed" >/dev/null 2>&1; then
    note dir "$TRUNK/.git"
    say "+ local version history ON — every session end records what changed"
    say "  (on this disk only: it is a history, not a backup. \`brain backup\` shows where it stands.)"
  else
    warn "could not start the local version history in $TRUNK."
    warn "Your notes are still saved as files, but nothing records their history."
    warn "To turn it on by hand:  git -C $TRUNK init"
  fi
fi

# ─── 3. The engine, linked into the trunk ────────────────────────────────────
# The list is NOT inline here any more: cbrain/engine-paths.txt is the single
# definition, also read by update.sh (to tell engine dirt from user work) and by
# brain_doctor (to report it). Three consumers, one list — see that file for why.
step "Engine linked into the trunk"
# THREE READS, IN THIS ORDER, AND NONE OF THEM MAY ABORT THE SCRIPT.
# `VAR=$(grep …)` under `set -e` kills the run when grep exits non-zero — and a
# missing file is exit 2. Under `--dry-run` the version is never built, so
# $ENGINE does not exist and the installer died right here, silently, at
# "Engine linked into the trunk". The `|| true` is what makes the fallback below
# reachable at all.
# The SOURCE is the second read rather than the hardcoded list, because that is
# where a real install would take the list from: a dry run that described a
# different set of links than the install it previews is worse than no preview.
ENGINE_PATHS=$(grep -vE '^\s*(#|$)' "$ENGINE/cbrain/engine-paths.txt" 2>/dev/null || true)
[ -n "$ENGINE_PATHS" ] || ENGINE_PATHS=$(grep -vE '^\s*(#|$)' "$SOURCE/cbrain/engine-paths.txt" 2>/dev/null || true)
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

# WHERE npm IS ALLOWED TO WRITE. `npm install` rewrites `package-lock.json` in
# the directory it runs in. In the old model that directory was the engine repo,
# and the rewrite is what made the SECOND update refuse ("local changes") — the
# net for it is still in update.sh. Here it would be worse: it would mutate an
# immutable version at every install, and doctor would report an anomaly the
# installer had just caused itself. So for a managed engine npm runs in the
# SHARED RUNTIME, and the version holds only a symlink to its `node_modules`.
if [ "$DEV" = "1" ] || [ "$DRY" = "1" ]; then
  CAPSULE_PREFIX="$ENGINE/capsule"
else
  link_runtime "$ENGINE" "$RUNTIME" || warn "could not mount the shared Electron runtime"
  CAPSULE_PREFIX="$(runtime_dir "$ENGINE" "$RUNTIME")"
fi

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
  npm --prefix "$CAPSULE_PREFIX" install --silent >/dev/null 2>&1 || true
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
    warn "  rm -rf $CAPSULE_PREFIX/node_modules && npm --prefix $CAPSULE_PREFIX install"
    warn "  then re-run this installer — it will unpack what npm downloaded."
  fi
fi

# ─── 8. Scheduled jobs ─────────────────────────────────────────────────
step "Scheduled jobs (launchd)"
if [ "$DO_LAUNCHD" = "0" ]; then say "(skipped — --no-launchd)"
else
  run mkdir -p "$HOME/Library/LaunchAgents"
  refused=0
  for t in resume machiniste; do
    tpl="$ENGINE/hooks/com.claudebrain.$t.plist.template"
    [ -f "$tpl" ] || continue
    label="com.claudebrain.$t"
    out="$HOME/Library/LaunchAgents/$label.plist"
    if [ "$DRY" = "1" ]; then say "(dry-run) would generate $out"; continue; fi
    # OWNERSHIP IS ASKED BEFORE THE FILE IS WRITTEN, not before the unload. On a
    # machine where another installation already holds this identity, its plist
    # sits at exactly this path: writing first and asking after would have
    # overwritten it, and "nothing was changed" would be a lie.
    if cb_launchd_registered "$label" && ! cb_launchd_owned "$label"; then
      cb_launchd_refuse "$label" || :
      refused=$((refused + 1))
      continue
    fi
    # __HOME__ substituted here: a hardcoded path in a .plist is THE bug that
    # silently breaks an install on another machine.
    sed "s|__HOME__|$HOME|g" "$tpl" > "$out"
    note file "$out"
    cb_launchd_install "$label" "$out" \
      || warn "$label generated but not registered — see the line above"
  done
  if [ "$refused" -gt 0 ]; then
    warn "$refused scheduled job(s) left untouched. C Brain is installed and works;"
    warn "  those jobs keep running whatever they were already running."
  fi
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
