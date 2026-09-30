#!/usr/bin/env bash
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# install.sh — installs GreyMatter. The SINGLE entry point.
#
# Three promises, kept by construction:
#   · IDEMPOTENT — re-running breaks nothing and duplicates nothing.
#   · NON-DESTRUCTIVE — anything already there is backed up before being touched.
#   · REVERSIBLE — every action is logged; ./uninstall.sh undoes them.
#
# Installed layout:
#   ~/.greymatter/versions/<id>/  an ENGINE: an immutable export of the source
#   ~/.greymatter/engine          → link to the ACTIVE version. Switching is one symlink.
#   ~/.greymatter/source.git      the mirror updates are fetched into
#   ~/.greymatter/runtime/        the native capsule's build, shared by versions
#   ~/.greymatter/trunk           YOUR trunk (your notes). Never overwritten, never updated.
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
#                and switch automatic updates off for it. For working on GreyMatter.
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
# left a `~/.greymatter` behind on a machine that had never installed anything, and
# the CI step that checks exactly that went red. Resolving $HOME and appending
# the name gives the same canonical path without writing: the symlink that has
# to be resolved on macOS (`/var` → `/private/var`) is in $HOME, not in the last
# component. The `cd "$GM"` branch is kept for the case the plain concatenation
# cannot cover — a `~/.greymatter` that is itself a link somewhere else.
GM="$HOME/.greymatter"
if [ -d "$GM" ]; then
  GM="$(cd "$GM" && pwd -P)"
else
  GM="$(cd "$HOME" 2>/dev/null && pwd -P || echo "$HOME")/.greymatter"
fi
TRUNK="$GM/trunk"
VERSIONS="$GM/versions"
RUNTIME="$GM/runtime"
MIRROR="$GM/source.git"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUPS="$GM/backups/$TS"
MANIFEST="$GM/manifest.txt"

DO_LAUNCHD=1; DO_CAPSULE=1; DO_SHORTCUT=1; DO_PLANET=1; DRY=0; DEV=0
# 1 once any piece is chosen by option: a replay then obeys the options, not the record.
CHOSEN_BY_HAND=0
for a in "$@"; do
  case "$a" in
    # The ONLY mode in which an engine may be a working checkout, and it has to
    # be asked for by name. Everything the updater could do destructively is
    # switched off for this install: a development repo is somebody's work, and
    # no amount of inspection can tell it apart from an install after the fact.
    --dev) DEV=1 ;;
    --no-launchd) DO_LAUNCHD=0; CHOSEN_BY_HAND=1 ;;
    --no-capsule) DO_CAPSULE=0; CHOSEN_BY_HAND=1 ;;
    --no-shortcut) DO_SHORTCUT=0; CHOSEN_BY_HAND=1 ;;
    # The memory, and nothing else: trunk, recall, agents, hooks, `brain`.
    # No menu bar pill, no 3D globe, no background job. Named as one option
    # because "install it without the ornaments" is a thing people want to ask
    # for in one go, and three flags they have to discover is not an answer.
    --core-only)  DO_LAUNCHD=0; DO_CAPSULE=0; DO_PLANET=0; CHOSEN_BY_HAND=1 ;;
    --no-planet)  DO_PLANET=0; CHOSEN_BY_HAND=1 ;;
    --dry-run)    DRY=1 ;;
    *) echo "Unknown option: $a"; exit 1 ;;
  esac
done

say()  { echo "  $*"; }
step() { echo; echo "▸ $*"; }
warn() { echo "  ⚠️  $*"; }
die()  { echo; echo "❌ $*"; exit 1; }

# Building, verifying and mounting a version — shared with greymatter/update.sh so
# that the installer and the updater cannot disagree on what a version is.
. "$SOURCE/greymatter/engine-lib.sh"
. "$SOURCE/greymatter/launchd-lib.sh"

# ─── 0. The root's old name ──────────────────────────────────────────────────
# Until v2.1.0 the root was `~/.c-brain`. It moves to `~/.greymatter` HERE, before  (pre-rename)
# anything is written, and leaves a permanent link at the old place — the same
# script an update runs (greymatter/migrations/002). Run from install.sh too,
# because an update from before the rename reaches this installer without ever
# having looked in greymatter/migrations/. Idempotent: on any other machine it
# says "nothing to move" and returns.
OLD_ROOT="$HOME/.c-brain"   # pre-rename
if [ -e "$OLD_ROOT" ] || [ -L "$OLD_ROOT" ]; then
  if [ "$DRY" = "1" ]; then
    [ -L "$OLD_ROOT" ] && [ -e "$HOME/.greymatter" ] \
      || echo "  (dry-run) would move ~/.c-brain to ~/.greymatter, and leave a link at the old place"  # pre-rename
  else
    bash "$SOURCE/greymatter/migrations/002-rename-root.sh" \
      || die "the root could not be renamed — nothing else was changed (see the line above)"
    [ -d "$HOME/.greymatter" ] && GM="$(cd "$HOME/.greymatter" && pwd -P)"
    TRUNK="$GM/trunk"; VERSIONS="$GM/versions"; RUNTIME="$GM/runtime"
    MIRROR="$GM/source.git"; BACKUPS="$GM/backups/$TS"; MANIFEST="$GM/manifest.txt"
    # The managed-engine marker holds the versions root as written at install
    # time, so it still names the old one; `brain update` compares it with the
    # RESOLVED engine and refused every update and rollback after the move.
    # Rewritten only when it resolves to exactly the same folder.
    m="$GM/state/engine-managed"
    if [ -f "$m" ] && [ "$(cat "$m")" != "$VERSIONS" ] \
       && [ "$(cd "$(cat "$m")" 2>/dev/null && pwd -P)" = "$VERSIONS" ]; then
      printf '%s\n' "$VERSIONS" > "$m"
    fi
  fi
fi

# Logs what we create, so uninstall knows what to undo.
note() { [ "$DRY" = "1" ] || { mkdir -p "$GM"; echo "$1|$2" >> "$MANIFEST"; }; }

# Back up before overwriting. User content never disappears.
save() {
  [ -e "$1" ] || return 0
  [ "$DRY" = "1" ] && { say "(dry-run) would back up $1"; return 0; }
  mkdir -p "$BACKUPS"
  cp -R "$1" "$BACKUPS/$(basename "$1")" 2>/dev/null || true
  say "backed up: $1 → $BACKUPS/"
}

run() { [ "$DRY" = "1" ] && { say "(dry-run) $*"; return 0; }; "$@"; }

# ─── WHOSE SURFACE IS THIS? ──────────────────────────────────────────────────
#
# THE INCIDENT. On 2026-08-19 this installer ran on a machine that already had
# an author's installation. It repointed `~/.claude/agents` at its own trunk and
# overwrote `~/.claude/statusline.py`. It printed "backed up:" and "+", scrolled
# on, and exited 0. The other installation went on calling agents that were no
# longer where it had put them: 118 `agent not found` in 39 hours, its
# distillation dead, and not one line anywhere saying a foreign surface had been
# taken. The timestamped backup WAS made, and it is what allowed the repair. The
# defect is the SILENT TAKEOVER, not a missing backup.
#
# THE RULE, and it is the one greymatter/launchd-lib.sh already applies to a Label.
# Ownership is a RECORDED FACT, never inferred — not from the name of the file,
# not from "it looks like something GreyMatter writes", not from "an older GreyMatter
# probably put it there". And the record already existed: `manifest.txt`, which
# every run appends to AFTER a placement has succeeded. It was written for the
# uninstaller and never read by the installer. The absence of a record is not a
# proof of ownership either, so an unrecorded surface is refused BY NAME and
# nothing is changed.
#
# WHERE THE GATE APPLIES — and where it must NOT. Inside `$GM` this installation
# is the owner by definition: that directory IS the installation, and gating it
# would make a legitimate re-install refuse its own engine. The gate is for the
# surfaces on which two installations can collide because they are SHARED with
# the rest of the machine: `~/.claude/agents`, `~/.claude/statusline.py`,
# `~/.local/bin/brain`.
REFUSED_SURFACES=0

surface_owned() {   # <path> → 0 if a previous run of THIS installation placed it
  [ -f "$MANIFEST" ] || return 1
  grep -qxF "link|$1" "$MANIFEST" 2>/dev/null && return 0
  grep -qxF "file|$1" "$MANIFEST" 2>/dev/null
}

# WHAT IS THERE, read off the disk — never guessed. A refusal that cannot say
# what it found leaves the reader to check by hand, which is where they give up.
surface_what() {    # <path> → one line, no newline
  if [ -L "$1" ]; then
    printf 'a link pointing at %s' "$(readlink "$1")"
  elif [ -d "$1" ]; then
    printf 'a directory holding %s item(s)' "$(ls -A "$1" 2>/dev/null | wc -l | tr -d ' ')"
  else
    printf 'a file of %s bytes, last modified %s' \
      "$(wc -c < "$1" 2>/dev/null | tr -d ' ')" \
      "$(date -r "$1" '+%Y-%m-%d %H:%M' 2>/dev/null || echo 'unknown')"
  fi
}

# One voice for every surface. It names the path, says what occupies it, states
# that nothing was changed, spells out what GreyMatter loses by not taking it, and
# ends on the one gesture that resolves it — because a refusal with no next step
# is just an obstacle.
surface_refuse() {  # <path> <what GreyMatter wanted to put there> [consequence]
  warn "OCCUPIED, and not by this installation: $1"
  warn "  There is already $(surface_what "$1")."
  warn "  This installation has no record of putting it there, so NOTHING was"
  warn "  changed: whatever uses it keeps working."
  if [ -n "${3:-}" ]; then warn "  What GreyMatter loses: $3"; fi
  warn "  It wanted to put $2 here. To hand it over, move the current one aside:"
  warn "    mv \"$1\" \"$1.before-greymatter\"     then re-run ./install.sh"
  REFUSED_SURFACES=$((REFUSED_SURFACES + 1))
  return 3
}

# Places a symlink idempotently: already correct → nothing is touched.
link() {  # link <target> <link> [what GreyMatter loses if the surface is refused]
  local target="$1" path="$2"
  if [ -L "$path" ] && [ "$(readlink "$path")" = "$target" ]; then
    say "= $path (already linked)"; return 0
  fi
  if [ -e "$path" ] || [ -L "$path" ]; then
    case "$path" in
      "$GM"/*) : ;;   # inside our own root — ours by definition, see above
      *) surface_owned "$path" \
           || { surface_refuse "$path" "a link to $target" "${3:-}"; return 3; } ;;
    esac
    save "$path"
    run rm -rf "$path"
  fi
  run mkdir -p "$(dirname "$path")"
  run ln -s "$target" "$path"
  note link "$path"
  say "+ $path → $target"
}

echo "🧠 GreyMatter — installation"
echo "   source : $SOURCE"
echo "   trunk  : $TRUNK"
[ "$DRY" = "1" ] && echo "   (DRY-RUN: nothing will be written)"

# ─── 0. Prerequisites ────────────────────────────────────────────────────────
step "Prerequisites"
[ "$(uname)" = "Darwin" ] || die "GreyMatter targets macOS (launchd, AppKit, \`open\`)."
command -v python3 >/dev/null || die "python3 is required (it runs every hook)."
say "python3 $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
command -v git >/dev/null || warn "git missing — \`brain update\` will not be able to pull updates."

HAS_CLAUDE_CODE=0
[ -d "$HOME/.claude" ] && HAS_CLAUDE_CODE=1
if [ "$HAS_CLAUDE_CODE" = "0" ]; then
  warn "~/.claude missing: Claude Code does not appear to be installed."
  warn "GreyMatter will still install, but WITHOUT the closed loop:"
  warn "the hooks (recall, archiving, maintenance) are specific to Claude Code."
  warn "You keep the \`brain\` CLI, the agents, the planet and the capsule."
fi

# ─── 1. GreyMatter root, and the ENGINE this install will own ───────────────────
#
# A SOURCE IS NOT AN ENGINE. Until 2026-08-17 `~/.greymatter/engine` was a link to
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
step "GreyMatter root (~/.greymatter)"
run mkdir -p "$GM" "$GM/state"
# What the engine pointed at BEFORE this run — read now, because we are about to
# repoint it. Used only to tell a converting installation what just happened.
PREVIOUS_ENGINE="$(cd "$GM/engine" 2>/dev/null && pwd -P || true)"

# The version identity, read off the source. A tagged checkout gives `v1.29.0`;
# a plain clone of `main` gives `v1.28.1-24-g6f28312`. Both are legitimate names
# for a version directory — which is precisely what makes the DOCUMENTED
# `git clone && ./install.sh` produce an updatable install with no extra gesture
# from the user, and no change to a single line of INSTALL.md.
SOURCE_DIRTY=0
if git -C "$SOURCE" rev-parse --git-dir >/dev/null 2>&1; then
  VERSION_ID="$(git -C "$SOURCE" describe --tags --always 2>/dev/null || echo "untagged")"
  # ⚠ NO `-dirty` SUFFIX — removed 2026-09-20, and the reason is the whole point.
  #   `build_version()` exports with `git archive HEAD`: the engine IS the commit,
  #   and the source's uncommitted work is deliberately left out of it. Suffixing
  #   the version therefore labelled the ENGINE with a property of the SOURCE.
  #   Measured on this machine: `~/.greymatter/versions/` held TWO directories for
  #   the same commit 686f2ac, one named `…-dirty`, and the two exports were
  #   BYTE-IDENTICAL. The suffix bought a redundant ~11.6 MB engine per dirty
  #   install and made the `already installed and intact` branch below unreachable
  #   for anyone working in their clone — the fast path could never fire.
  #   What the user actually needed was never a name: it was being TOLD their work
  #   is not in the engine. That is said out loud, once, where the engine is built.
  if [ -n "$(git -C "$SOURCE" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    SOURCE_DIRTY=1
  fi
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

# ─── WHAT THE USER DECLINED STAYS DECLINED ───────────────────────────────────
# Every `brain update` and every rollback ends by replaying this script, and the
# updaters already on users' disks pass it no option at all. So each update used
# to put back the jobs, the pill, the Desktop app and the shortcut the user had
# turned down — and so did the documented repair, "re-run ./install.sh".
#
#   run                    record    → the pieces installed
#   with options           —         → the options, which become the record
#   without options        present   → the record: the choices of the last install
#   replay, no options     absent    → read from this Mac (installed before v2.2.0)
#   by hand, no options    absent    → every piece: a first install
#
# The record holds the CHOICE, never the outcome: a pill skipped because Swift
# is missing stays chosen, so installing Swift and re-running still adds it. An
# install from before v2.2.0 left no choice written anywhere, only its result on
# disk, where a declined piece is simply absent; the Electron orb of v2.1.x
# stands for the pill. That reading cannot tell "declined" from "Node was
# missing" — both had no orb, and both keep having no pill, which is the error
# that takes nothing away. engine-lib.sh keeps the record.
kept=""
if [ "$CHOSEN_BY_HAND" = "0" ]; then
  if choices_read; then
    kept="kept from the last install"
  elif [ "$ALREADY_A_VERSION" = "1" ]; then
    kept="read from this Mac (installed before v2.2.0)"
    DO_LAUNCHD=0; DO_CAPSULE=0; DO_PLANET=0; DO_SHORTCUT=0
    la="$HOME/Library/LaunchAgents"
    for f in "$la/com.greymatter.resume.plist" "$la/com.greymatter.machiniste.plist" \
             "$la/com.claudebrain.resume.plist" "$la/com.claudebrain.machiniste.plist"; do  # pre-rename
      [ -e "$f" ] && DO_LAUNCHD=1
    done
    for f in "$RUNTIME"/capsule-*/node_modules/electron/dist/Electron.app \
             "$RUNTIME"/capsule-native-*/release/Capsule; do
      [ -e "$f" ] && DO_CAPSULE=1
    done
    for f in "$HOME/Desktop/GreyMatter.app" "$HOME/Desktop/C Brain Planet.app"; do  # pre-rename
      [ -e "$f" ] && DO_PLANET=1
    done
    [ -n "$(map_apps "$TRUNK")" ] && DO_PLANET=1   # moved by the user: still installed
    for f in "$HOME/GreyMatter" "$HOME/C Brain"; do  # pre-rename
      [ -L "$f" ] && DO_SHORTCUT=1
    done
  fi
fi
if [ -n "$kept" ]; then
  declined="$(choices_as_flags)"
  say "= install choices $kept:${declined:- nothing declined}"
  say "  to change them, run ./install.sh with the options you want now; for every"
  say "  piece, delete $(choices_file) first"
fi
[ "$DRY" = "1" ] || choices_write || warn "could not record the install choices ($(choices_file))"

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
    printf '%s\n' "$SOURCE" > "$GM/state/engine-dev"
    rm -f "$GM/state/engine-managed"          # the two are mutually exclusive
    note "file" "$GM/state/engine-dev"
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
    # SAID HERE AND NOWHERE ELSE: this is the one place where an engine is about
    # to be built, or found already built, out of the commit rather than out of
    # what is on disk. Saying it at the version-id stage would also fire for
    # `--dev`, which links the checkout itself and for which it would be false.
    if [ "$SOURCE_DIRTY" = "1" ]; then
      warn "your source has uncommitted changes, and they are NOT in this engine"
      warn "the engine is built from the commit $VERSION_ID — commit, then re-run"
    fi
    if [ -n "$(manifest_of "$ENGINE")" ] && verify_manifest "$ENGINE" >/dev/null 2>&1; then
      say "= $VERSION_ID already installed and intact"
    else
      build_version "$SOURCE" "$ENGINE" || die "could not build the engine $VERSION_ID from $SOURCE"
      say "+ engine built: versions/$VERSION_ID ($(find "$ENGINE" -type f ! -name .greymatter-manifest | wc -l | tr -d ' ') files)"
    fi
    # The mirror the updater fetches into. It exists so that NO git command in
    # the update path ever names a directory the user created.
    # Under `set -e` a bare failure here ended the install with no word at all.
    mirror_source "$SOURCE" "$MIRROR" || die "could not create the update mirror $MIRROR"
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
          say "  was:  $PREVIOUS_ENGINE (a git checkout GreyMatter used directly)"
          say "  now:  $ENGINE (built here, replaceable, never your repository)"
          say "  \`brain update\` will not touch $PREVIOUS_ENGINE again — see docs/UPGRADING.md"
          ;;
      esac
    fi
    # OWNERSHIP AS PROVENANCE, not as a verdict on a git state: this file says
    # "the installer built the tree under versions/ and may replace it". It names
    # the versions root rather than one version, because the whole point is that
    # the active version changes.
    printf '%s\n' "$VERSIONS" > "$GM/state/engine-managed"
    rm -f "$GM/state/engine-dev"
    note "file" "$GM/state/engine-managed"
  fi
fi

link "$ENGINE" "$GM/engine"
[ "$DRY" = "1" ] || printf '%s\n' "$VERSION_ID" > "$GM/VERSION"
say "version: $(cat "$GM/VERSION" 2>/dev/null || echo '?')"

# ─── 2. The trunk ──────────────────────────────────────────────────────────
step "Trunk (~/.greymatter/trunk)"
if [ -d "$TRUNK" ]; then
  # A trunk exists. If it holds a REAL hooks/ folder (not a link), it is
  # a previous standalone install: we refuse to demolish it silently.
  if [ -d "$TRUNK/hooks" ] && [ ! -L "$TRUNK/hooks" ]; then
    die "$TRUNK/hooks is a REAL folder, not a link.
   There is already an old-style Brain installed here. I will not replace it on my own:
   its files might be yours. Back it up, then re-run:
     mv $TRUNK $TRUNK.before-greymatter && ./install.sh"
  fi
  say "= existing trunk kept (your notes are untouched)"
else
  run mkdir -p "$TRUNK"
  run cp -R "$ENGINE/skeleton/." "$TRUNK/"
  note dir "$TRUNK"
  say "+ trunk created from skeleton/ (empty, ready to grow)"
fi
run mkdir -p "$TRUNK/state" "$TRUNK/sessions/archive"

# An update must add product configuration that older trunks lack. Copy only
# missing files so user settings in an existing trunk are preserved.
if [ -f "$ENGINE/skeleton/config/ranking.json" ] && [ ! -f "$TRUNK/config/ranking.json" ]; then
  run mkdir -p "$TRUNK/config"
  run cp "$ENGINE/skeleton/config/ranking.json" "$TRUNK/config/ranking.json"
  say "+ config/ranking.json added to trunk"
fi

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
       && git -C "$TRUNK" -c user.email=greymatter@localhost -c user.name="GreyMatter" \
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
# The list is NOT inline here any more: greymatter/engine-paths.txt is the single
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
ENGINE_PATHS=$(grep -vE '^\s*(#|$)' "$ENGINE/greymatter/engine-paths.txt" 2>/dev/null || true)
[ -n "$ENGINE_PATHS" ] || ENGINE_PATHS=$(grep -vE '^\s*(#|$)' "$SOURCE/greymatter/engine-paths.txt" 2>/dev/null || true)
[ -n "$ENGINE_PATHS" ] || ENGINE_PATHS="hooks agents capsule planet companion tests"
for d in $ENGINE_PATHS; do
  link "$GM/engine/$d" "$TRUNK/$d"
done

# ─── 4. The `brain` command ───────────────────────────────────────────────
step "The \`brain\` command"
# `|| :` because a refusal (exit 3) is a REPORTED OUTCOME, not a crash: the rest
# of GreyMatter installs, and the closing screen counts what was left alone.
link "$GM/engine/brain" "$HOME/.local/bin/brain" \
     "the \`brain\` command will keep starting the installation already on PATH" || :
case ":$PATH:" in
  *":$HOME/.local/bin:"*) PATH_OK=1; say "~/.local/bin is on PATH" ;;
  *) PATH_OK=0
     warn "~/.local/bin is NOT on your PATH. Add to your ~/.zshrc:"
     warn "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
# THIS WARNING IS THREE HUNDRED LINES FROM THE LAST SCREEN, so on a fresh macOS it
# has scrolled away by the time anyone reads the closing block — which then offered
# four commands beginning with `brain`, none of which resolve. Reported as C bis A4.
# The verdict is kept in PATH_OK and spoken again at the end, where it is acted on.

# ─── 5. Agents visible to Claude Code ───────────────────────────────────
# Trap #1: without this link the agents exist but Claude Code cannot see
# them. No error, just an autonomous loop spinning on nothing.
step "Agents visible to the CLI agent"
if [ "$HAS_CLAUDE_CODE" = "1" ]; then
  link "$TRUNK/agents" "$HOME/.claude/agents" \
       "Claude Code will not see GreyMatter's agents — but it keeps seeing the ones already there" || :
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
    # Same gate as `link`, spelled out because this one is a plain copy. This is
    # the OTHER half of the 2026-08-19 incident: the author's status line was
    # overwritten by this exact `cp`, and the only trace was "backed up:".
    if [ -e "$HOME/.claude/statusline.py" ] \
       && ! surface_owned "$HOME/.claude/statusline.py"; then
      surface_refuse "$HOME/.claude/statusline.py" "its own status line" \
        "the bar at the bottom of Claude Code keeps showing what it shows today" || :
    else
      save "$HOME/.claude/statusline.py"
      run cp "$ENGINE/statusline.py" "$HOME/.claude/statusline.py"
      note file "$HOME/.claude/statusline.py"
      say "+ status line installed"
    fi
  fi
else
  say "(skipped — no Claude Code: GreyMatter will work on demand)"
fi

# ─── 7. Capsule ───────────────────────────────────────────────────────────
# SINCE v2.2 THE CAPSULE IS NATIVE: a small Swift app (capsule/macos) that sits
# in the menu bar, shows which agent is working, and drops a panel on click.
# No Electron, no Node, no npm, nothing downloaded. It needs the Swift compiler
# from Apple's Command Line Tools, which a Mac running Claude Code usually has.
#
# The build goes OUTSIDE the version (see build_capsule in engine-lib.sh): a
# version is immutable, and the build output is a runtime, like the old
# node_modules was. In --dev the checkout IS the engine, so it builds in place,
# in the `.build` folder a developer already has — never deleted from here.
#
# Then the pill is STARTED, right away. A user who has just installed GreyMatter
# should see it in the menu bar without waiting for their next Claude session.
step "Capsule (menu bar pill)"
CAPSULE_BIN="$ENGINE/capsule/macos/.build/release/Capsule"
capsule_start() {
  local trunk bin
  trunk="$(cd "$TRUNK" 2>/dev/null && pwd -P)" || return 1
  # Launched through the trunk, the path hooks/auto_maintain.py looks for with
  # pgrep: started from anywhere else, the hook would not recognise it as ours.
  bin="$trunk/capsule/macos/.build/release/Capsule"
  [ -x "$bin" ] || return 1
  [ -e "$trunk/state/no-capsule" ] && { say "= capsule not started (state/no-capsule: light mode)"; return 0; }
  if pgrep -f "$bin" >/dev/null 2>&1; then say "= capsule already running"; return 0; fi
  CAPSULE_BRAIN="$trunk" nohup "$bin" </dev/null >/dev/null 2>&1 &
  disown 2>/dev/null || true
  say "+ capsule started: look for \"GreyMatter idle\" in the menu bar"
}

# The Electron orb of v2.1.x is gone from this version, whatever the choice: left
# running, it would sit next to the new pill, or outlive a pill the user declined.
# Stopped BEFORE any branch below, light mode and --no-capsule included — inside
# capsule_start it came after the light-mode return, and survived the update.
# Matched where Node really runs it (orb_patterns), not on the trunk path.
if [ "$DRY" != "1" ]; then
  while IFS= read -r orb; do
    pkill -f "$orb" 2>/dev/null || true
  done < <(orb_patterns "$TRUNK" "$RUNTIME")
fi

if [ "$DO_CAPSULE" = "0" ]; then say "(skipped — --no-capsule)"
elif [ ! -f "$ENGINE/capsule/macos/Package.swift" ]; then say "(no native capsule in this version)"
elif ! { command -v swift >/dev/null 2>&1 && xcode-select -p >/dev/null 2>&1; }; then
  # A message that names what is missing but not the next step sends the reader
  # to invent one, and they invent the expensive one (install report, 2026-08-13).
  warn "Apple's Command Line Tools are missing — only the capsule (the menu bar pill) is skipped."
  say  "Everything else is installed and working: hooks, agents, memory, \`brain\`."
  say  "To get the pill later:"
  say  "  1. run: xcode-select --install   (Apple's installer, one window, a few minutes);"
  say  "  2. re-run this installer: it is idempotent, it will only add the capsule."
elif [ "$DRY" = "1" ]; then say "(dry-run) would build the capsule (swift build, ~30 s) and start it"
else
  CAPSULE_LOG="$GM/state/capsule-build.log"
  mkdir -p "$GM/state"
  if [ -x "$CAPSULE_BIN" ] && [ "$DEV" != "1" ]; then built=0
  else say "building the capsule (swift build, ~30 s the first time)…"; built=1; fi
  if [ "$DEV" = "1" ]; then
    swift build -c release --package-path "$ENGINE/capsule/macos" >"$CAPSULE_LOG" 2>&1 || true
  else
    build_capsule "$ENGINE" "$RUNTIME" "$CAPSULE_LOG" || true
  fi
  if [ -x "$CAPSULE_BIN" ]; then
    [ "$built" = "1" ] && say "+ capsule built" || say "= capsule already built"
    capsule_start || warn "the capsule is built but could not be started — \`brain capsule\` retries"
  else
    warn "The capsule did not build. Everything else works."
    warn "  The compiler's output is in $CAPSULE_LOG"
    warn "  It needs Swift 6 (Xcode 16 or its Command Line Tools). To update them:"
    warn "  softwareupdate --list, then re-run this installer."
  fi
fi

# ─── 8. Scheduled jobs ─────────────────────────────────────────────────
step "Scheduled jobs (launchd)"
if [ "$DO_LAUNCHD" = "0" ]; then say "(skipped — --no-launchd)"
else
  run mkdir -p "$HOME/Library/LaunchAgents"
  refused=0
  # Jobs this installation registered under the pre-rename label: retired here,
  # through the same ownership rule as everything else — only the ones on
  # record as ours. Kept, each job would run twice, once under each name.
  # One running under the old label that is NOT on record (a machine that never
  # adopted its legacy jobs) is left alone, and its new twin is not installed:
  # it still does the job, through the ~/.c-brain link, and two of them would not. (pre-rename)
  kept_old=""
  for t in resume machiniste etat; do
    old_label="com.claudebrain.$t"   # pre-rename
    [ "$DRY" = "1" ] && continue
    if gm_launchd_owned "$old_label"; then
      gm_launchd_uninstall "$old_label" "$HOME/Library/LaunchAgents/$old_label.plist" \
        && say "- $old_label retired (now com.greymatter.$t)" || :
    elif gm_launchd_registered "$old_label"; then
      kept_old="$kept_old $t"
      warn "$old_label is running and this installation holds no proof it is its own."
      warn "  Left running; com.greymatter.$t is NOT installed, so the job does not run twice."
      warn "  If it is an old GreyMatter job, docs/UPGRADING.md says how to stop it;"
      warn "  then re-run this installer."
    fi
  done
  for t in resume machiniste; do
    case " $kept_old " in *" $t "*) continue ;; esac
    tpl="$ENGINE/hooks/com.greymatter.$t.plist.template"
    [ -f "$tpl" ] || continue
    label="com.greymatter.$t"
    out="$HOME/Library/LaunchAgents/$label.plist"
    if [ "$DRY" = "1" ]; then say "(dry-run) would generate $out"; continue; fi
    # OWNERSHIP IS ASKED BEFORE THE FILE IS WRITTEN, not before the unload. On a
    # machine where another installation already holds this identity, its plist
    # sits at exactly this path: writing first and asking after would have
    # overwritten it, and "nothing was changed" would be a lie.
    if gm_launchd_registered "$label" && ! gm_launchd_owned "$label"; then
      gm_launchd_refuse "$label" || :
      refused=$((refused + 1))
      continue
    fi
    # __HOME__ substituted here: a hardcoded path in a .plist is THE bug that
    # silently breaks an install on another machine.
    sed "s|__HOME__|$HOME|g" "$tpl" > "$out"
    note file "$out"
    gm_launchd_install "$label" "$out" \
      || warn "$label generated but not registered — see the line above"
  done
  if [ "$refused" -gt 0 ]; then
    warn "$refused scheduled job(s) left untouched. GreyMatter is installed and works;"
    warn "  those jobs keep running whatever they were already running."
  fi
fi

# ─── 9. Planet launcher ─────────────────────────────────────────────
# SINCE v2.2 IT OPENS GMTR, NOT THE OLD PLANET, IN ITS OWN WINDOW. Same bundle
# id, same icon, same place on the Desktop. Its executable is now a native app
# (gmtr/macos: AppKit + the system's WebKit, no Electron, no browser tab), built
# here with `swift build`. It starts gmtr/launch.sh, shows the map when the
# server answers on localhost:8767, and stops the server when it quits. Without
# the Apple developer tools there is nothing to build with: the bundle then
# carries the v2.1 shell script, which opens the map in the default browser.
# AN APP BUNDLE, NOT A `.command`. Both are one double-click, but only a bundle
# can carry an icon: a `.command` takes one solely through its resource fork,
# which on macOS is set with `Rez` — from the Xcode Command Line Tools, exactly
# what the machine in the 2026-08-13 install report did not have. An icon that
# only appears on machines already equipped for development is not an icon.
# A bundle is plain files: it works on a bare machine, shows up in the Dock while
# the planet is serving, and quitting it stops the server.
#
# The icon itself: `gmtr/macos/GreyMatter.icns`, the GMTR mark of 22/09 (the
# author's desktop app icon), which replaced the planet icon with the map.
step "Planet launcher (Desktop)"
APP="$HOME/Desktop/GreyMatter.app"
# The Desktop is only where the FIRST install puts it: a copy the user moved or
# renamed is rebuilt where it is, not doubled on the Desktop (map_apps says why).
# EVERY copy, not the first one found: the updates before this fix left a Desktop
# duplicate beside the moved app, and a copy left unbuilt keeps the old binary
# and the bugs this very update fixes, one double-click away.
MAP_APPS="$(map_apps "$TRUNK")"
[ -z "$MAP_APPS" ] || APP="$(printf '%s\n' "$MAP_APPS" | head -1)"
BUILT_APPS=""                               # what the end screen names
OLD_CMD="$HOME/Desktop/Planete-C-Brain.command"   # pre-rename
if [ "$DO_PLANET" = "0" ]; then say "(skipped — --no-planet)"
elif [ "$DRY" = "1" ]; then
  while IFS= read -r a; do say "(dry-run) would create $a"; done <<< "${MAP_APPS:-$APP}"
# "GreyMatter.app" is a plain name another app could carry: only OUR launcher
# (its bundle id) is rebuilt, anything else under that name is left alone.
elif [ -d "$APP" ] && ! grep -q "org.greymatter.planet" "$APP/Contents/Info.plist" 2>/dev/null; then
  warn "$APP is not this launcher — left alone. The planet stays reachable at:"
  warn "  $TRUNK/gmtr/launch.sh"
# A copy that cannot be cleared — a file locked in Finder, another owner's — is
# named and passed over, never the reason the whole update stops: the day a
# moved copy became ours to rebuild, one locked file in it failed every update.
elif [ -d "${APP%/*}" ] && ! run rm -rf "$APP"; then
  warn "$APP could not be rebuilt (a locked file? not yours?) — it is NOT"
  warn "  current: delete it, then run the update again."
  APP=""; MAP_APPS=""                     # nothing current to name at the end
elif [ -d "${APP%/*}" ]; then             # cleared just above: rebuilt whole, never patched
  run mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  if [ "$DRY" != "1" ]; then
    # The GUI hands a launched app a minimal PATH — python3 and `open` have to be
    # findable, or the double-click does nothing at all and says nothing either.
    # Built outside the engine: SwiftPM's scratch folder is hundreds of MB that
    # would otherwise ride along in every copy of the engine.
    GM_BUILD="$(mktemp -d "${TMPDIR:-/tmp}/greymatter-app.XXXXXX")"
    MAP_APP=native
    if ! command -v swift >/dev/null 2>&1 \
       || ! swift build -c release --package-path "$ENGINE/gmtr/macos" --scratch-path "$GM_BUILD" >"$GM_BUILD.log" 2>&1 \
       || ! cp "$GM_BUILD/release/GreyMatter" "$APP/Contents/MacOS/planet"; then
      MAP_APP=browser
      warn "the native map app could not be built (no Apple developer tools?) — the"
      warn "launcher opens the map in your browser instead. Log: $GM_BUILD.log"
      printf '#!/bin/bash\nexport PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"\nexec "%s/gmtr/launch.sh"\n' "$TRUNK" > "$APP/Contents/MacOS/planet"
    else
      rm -f "$GM_BUILD.log"
    fi
    rm -rf "$GM_BUILD"
    chmod +x "$APP/Contents/MacOS/planet"
    cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>GreyMatter</string>
  <key>CFBundleDisplayName</key><string>GreyMatter</string>
  <key>CFBundleIdentifier</key><string>org.greymatter.planet</string>
  <key>CFBundleExecutable</key><string>planet</string>
  <key>CFBundleIconFile</key><string>GreyMatter</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>GMTRLaunch</key><string>$TRUNK/gmtr/launch.sh</string>
  <key>GMTRPort</key><string>8767</string>
</dict></plist>
PLIST
    if [ -f "$ENGINE/gmtr/macos/GreyMatter.icns" ]; then
      cp "$ENGINE/gmtr/macos/GreyMatter.icns" "$APP/Contents/Resources/GreyMatter.icns"
    else
      warn "GreyMatter.icns missing — the launcher works, with the generic icon."
    fi
    # Finder caches an app's icon by path+mtime. Without this touch, a rebuilt
    # bundle keeps showing the previous icon until the next log-out.
    touch "$APP"
  fi
  note dir "$APP"
  if [ "$MAP_APP" = "native" ]; then say "+ $APP (double-click → the GMTR map in its own window)"
  else say "+ $APP (double-click → GMTR map in your browser, localhost:8767)"; fi
  BUILT_APPS="$APP"
  # The other copies get the bundle just built: one build, the same app everywhere.
  while IFS= read -r a; do
    [ -n "$a" ] && [ ! "$a" -ef "$APP" ] || continue
    if run rm -rf "$a" && run ditto "$APP" "$a"; then   # a locked one: see above
      [ "$DRY" = "1" ] || touch "$a"         # the icon cache, as above
      note dir "$a"
      say "+ $a (the same map app, where you keep another copy)"
      BUILT_APPS="$BUILT_APPS
$a"
    else
      warn "$a could not be rebuilt (a locked file? not yours?) — it is NOT"
      warn "  current: delete it. $APP is."
    fi
  done <<< "$MAP_APPS"
  # An installer that leaves the previous version's shortcut behind hands the
  # user two icons for one action, and lets them pick the stale one.
  OLD_APP="$HOME/Desktop/C Brain Planet.app"   # pre-rename
  if [ -d "$OLD_APP" ] && grep -q "org.cbrain.planet" "$OLD_APP/Contents/Info.plist" 2>/dev/null; then  # pre-rename
    run rm -rf "$OLD_APP"
    say "- the launcher under the old name removed (replaced by the app above)"
  fi
  if [ -f "$OLD_CMD" ]; then
    run rm -f "$OLD_CMD"
    say "- the old .command launcher removed (replaced by the app above)"
  fi
else
  warn "~/Desktop not found — launcher not created. The planet stays reachable at:"
  warn "  $TRUNK/gmtr/launch.sh"
fi

# ─── 10. Making the trunk findable ────────────────────────────────────────
# The trunk lives at ~/.greymatter/trunk. The leading dot keeps the plumbing out
# of the way — and hides the one part of this that is YOURS. A new user gets a
# memory they cannot see, in a folder Finder refuses to show. So we put a
# visible door on it.
#
# NOT the Finder sidebar: it is stored in a binary .sfl4 plist with no
# supported API, and the only way in is a third-party binary. Adding a
# dependency to place an icon is not a trade worth making — dragging the folder
# into Favourites takes the user two seconds, and we say so below.
step "Making your memory findable"
SHORTCUT="$HOME/GreyMatter"
if [ "$DO_SHORTCUT" = "0" ]; then say "(skipped — --no-shortcut)"
elif [ "$DRY" = "1" ]; then say "(dry-run) would create $SHORTCUT and tag the trunk"
else
  # The shortcut under the pre-rename name goes — only if it is ours: a link that
  # leads to this very trunk. Anything else by that name is someone's, left alone.
  OLD_SHORTCUT="$HOME/C Brain"   # pre-rename
  if [ -L "$OLD_SHORTCUT" ] && [ "$(cd "$OLD_SHORTCUT" 2>/dev/null && pwd -P)" = "$(cd "$TRUNK" && pwd -P)" ]; then
    rm "$OLD_SHORTCUT"
    say "- the shortcut under the old name removed"
  fi
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
blob = plistlib.dumps(["GreyMatter\n6"], fmt=plistlib.FMT_BINARY)   # 6 = red
subprocess.run(["xattr", "-w", "-x", "com.apple.metadata:_kMDItemUserTags",
                blob.hex(), sys.argv[1]], check=True)
PY
  say "  Tip: drag it into the Finder sidebar once — it stays there."
fi

# ─── 11. Verification ─────────────────────────────────────────────────────
step "Verification"
if [ "$DRY" = "1" ]; then say "(dry-run) would run the selftest"
else
  # THE ENGINE IS NAMED, and that is the whole point. With no argument the
  # selftest reaches the CLI through `$TRUNK/brain` — which install.sh does not
  # create, the command being linked into ~/.local/bin — and then falls back to
  # whatever `brain` sits on PATH. On a fresh machine that is nothing, so four
  # checks went red on a healthy install; on a machine that already had GreyMatter
  # it was WORSE: the freshly installed engine reported green or red on somebody
  # else's version, run against this HOME. Naming the engine is the case the
  # selftest already documents — "when an engine is named, its OWN brain is the
  # only one allowed" — and it is exactly what an installer knows.
  if bash "$TRUNK/hooks/selftest.sh" "$GM/engine" >/tmp/greymatter-selftest.log 2>&1; then
    SELFTEST_OK=1; say "✅ selftest OK — every hook healthy"
  else
    SELFTEST_OK=0
    warn "selftest failed — details: /tmp/greymatter-selftest.log"
    tail -5 /tmp/greymatter-selftest.log | sed 's/^/     /'
  fi
  python3 "$TRUNK/hooks/brain_doctor.py" --quiet >/dev/null 2>&1 \
    && say "✅ doctor — tree consistent" || say "ℹ️  doctor flags a few things to look at (\`brain doctor\`)"
fi

echo
# THE CLOSING VERDICT IS NOT A CONSTANT. It used to print "✅ GreyMatter installed."
# whatever had happened above — including right after "❌ hooks broken" — and then
# offer four commands that could not run. A closing screen that cannot go red is a
# decoration, not a report: it is the same defect as a test that never fails.
# A REFUSAL SCROLLS AWAY TOO. Each one was printed where it happened, which on a
# fresh macOS is several screens above the end — the very defect C bis A4 named
# for the PATH warning. So the count comes back here, before the verdict, and it
# comes back whatever else went right.
if [ "${REFUSED_SURFACES:-0}" -gt 0 ]; then
  echo "⚠️  $REFUSED_SURFACES surface(s) were left to their current owner."
  # "And works" only when the verification agrees. A surface left alone can cost
  # something the selftest checks — an agents folder that is someone else's means
  # Claude Code cannot reach GreyMatter's agents — and the line below then says red.
  if [ "${SELFTEST_OK:-1}" = "1" ]; then
    echo "   GreyMatter installed everything else and works. Scroll up: each one is"
  else
    echo "   GreyMatter installed everything else; what it could not take may be why"
    echo "   the verification below is red. Scroll up: each one is"
  fi
  echo "   named, with what it costs and the one command that hands it over."
  echo
fi
if [ "${PATH_OK:-1}" = "0" ]; then
  echo "⚠️  GreyMatter is installed — but the \`brain\` command is not reachable yet."
  echo
  echo "   ~/.local/bin is not on your PATH, so every command below answers"
  echo "   \"command not found\" until that is fixed. One line, once:"
  echo
  echo "       echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
  echo
  echo "   Or reach it by its full path right now:  ~/.local/bin/brain status"
fi
# NOT AN `elif`. It was one, and a bare PATH — the usual case on a new Mac — then
# hid a red selftest behind the PATH advice: the one screen that has to say "this
# install is not healthy" said something else. Both are spoken when both are true.
if [ "${SELFTEST_OK:-1}" = "0" ]; then
  [ "${PATH_OK:-1}" = "0" ] && echo
  echo "❌ GreyMatter is installed, but its own verification did not pass."
  echo "   Details: /tmp/greymatter-selftest.log — re-run it with \`brain selftest\`."
  echo "   This installer exits with an error, so whatever ran it sees the failure too."
fi
if [ "${PATH_OK:-1}" = "1" ] && [ "${SELFTEST_OK:-1}" = "1" ]; then
  echo "✅ GreyMatter installed."
fi
echo
# Offered FIRST, not as a footnote: an empty trunk on first launch shows nothing
# of what the tool can do. That is the screen where people give up.
#
# ⚠️ BUT ONLY IF IT IS ACTUALLY EMPTY. There used to be no test at all: the block
# fired on every install, re-installs included. Reported 2026-08-16 (a tester)
# on a machine where it announced an empty trunk holding 23 notes — and
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
# WHAT IS ON THE DESKTOP, said from what is on disk. A user of v2.0.3 went
# looking for a desktop app this repository does not ship (issue #4): the screen
# that ends the install is where they look, so it names the two there are, and
# only the ones actually in place.
if [ "$DRY" != "1" ]; then
  _gm_ui=0
  while IFS= read -r a; do
    grep -q "org.greymatter.planet" "${a:-/nonexistent}/Contents/Info.plist" 2>/dev/null || continue
    _gm_where="On your Desktop: GreyMatter.app"
    [ "$a" -ef "$HOME/Desktop/GreyMatter.app" ] || _gm_where="In ${a%/*}: ${a##*/}"
    case "${MAP_APP:-}" in
      native)  echo "   $_gm_where opens the map of your notes, in its own window." ;;
      browser) echo "   $_gm_where opens the map of your notes, in your browser." ;;
      *)       echo "   $_gm_where opens the map of your notes." ;;
    esac
    _gm_ui=1
  done <<< "${BUILT_APPS:-${MAP_APPS:-${APP:-}}}"
  if [ "$DO_CAPSULE" = "1" ] && [ -x "${CAPSULE_BIN:-/nonexistent}" ]; then
    echo "   In the menu bar: the pill, the agents at work, live"
    echo "   (\`brain capsule\` opens it now)."
    _gm_ui=1
  fi
  if [ "$_gm_ui" = "1" ]; then echo "   These are the only desktop interfaces GreyMatter ships."; echo; fi
fi
[ "$HAS_CLAUDE_CODE" = "1" ] \
  && echo "   Restart your CLI session for the hooks to take effect." \
  || echo "   Without Claude Code: no closed loop, but the whole CLI is there."
echo "   Uninstall: $ENGINE/uninstall.sh"

# THE EXIT CODE IS PART OF THE VERDICT. The screen above can go red; the exit code
# stayed 0 whatever it said, so a script, a CI job or an agent running this
# installer read success after a red selftest (blank-Mac test, 2026-09-26: "an
# automatic tool does not see the failure"). Only the selftest decides it — a PATH
# still to fix, or a surface left to its owner, is a working install.
[ "${SELFTEST_OK:-1}" = "1" ] || exit 1
