#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# update.sh — updates the ENGINE. Never touches the TRUNK.
#
# What it does:
#   1. fetches the published tags INTO ITS OWN MIRROR (~/.c-brain/source.git),
#   2. BUILDS the newest one as a new immutable version under versions/,
#   3. runs migrations that have not been applied yet,
#   4. selftests THAT VERSION while it is still inactive,
#   5. and only if it is green, switches the `engine` symlink atomically.
#
# A version may only become the active engine after passing its own controls, so
# there is no window in which the live engine is one nobody has checked. A red
# candidate is deleted; the active version was never involved, which is why the
# rollback path is now a safety net rather than a load-bearing step.
#
# What it does NOT do: read, modify or send a single one of your notes.
#
# Usage: brain update [--check] [--rollback] [--force] [--auto]
set -euo pipefail

# Canonical — see the same note in install.sh. The ownership check compares the
# engine's resolved path against the recorded one, and the two must be resolved
# the same way or a legitimate install is refused on a symlinked $HOME.
CB="$HOME/.c-brain"
CB="$(cd "$CB" 2>/dev/null && pwd -P || echo "$HOME/.c-brain")"
ENGINE="$(cd "$CB/engine" 2>/dev/null && pwd -P)" || { echo "❌ Engine not found ($CB/engine)."; exit 1; }
STATE="$CB/state"
VERSIONS="$CB/versions"
RUNTIME="$CB/runtime"
MIRROR="$CB/source.git"
APPLIED="$STATE/applied-migrations.txt"
PREVIOUS="$STATE/previous-version"
MANAGED="$STATE/engine-managed"
DEVMARK="$STATE/engine-dev"
mkdir -p "$STATE"

# Building and verifying a version — the same definitions the installer uses.
. "$ENGINE/cbrain/engine-lib.sh"

# ─── Automatic updates ────────────────────────────────────────────────────
# State files shared with `cbrain/check_update.py`, which triggers `--auto` at
# session start.
AUTO=0
LOCK="$STATE/auto-update.lock"            # a directory: `mkdir` is atomic
JOURNAL="$STATE/auto-update.log"
RESULT="$STATE/last-auto-update"          # read, shown, then deleted by the hook
AUTO_OFF="$STATE/auto-update-off"

MODE="update"
for a in "$@"; do
  case "$a" in
    --check) MODE="check" ;;
    --rollback) MODE="rollback" ;;
    --force) MODE="force" ;;
    --auto) AUTO=1; MODE="update" ;;
    --auto-off) MODE="auto-off" ;;
    --auto-on)  MODE="auto-on" ;;
    *) echo "Usage: brain update [--check] [--rollback] [--force] [--auto|--auto-off|--auto-on]"; exit 1 ;;
  esac
done

# ─── The switch ───────────────────────────────────────────────────────────
# It comes BEFORE everything else, on purpose: turning automatic updates off
# must not depend on the network, on the state of the repo, or on anything that
# can fail. It is the one command in this file that has to work when nothing
# else does.
if [ "$MODE" = "auto-off" ]; then
  mkdir -p "$STATE"; : > "$AUTO_OFF"
  echo "✅ Automatic updates are OFF."
  echo "   Session start will report new versions without installing them."
  echo "   To turn them back on:  brain update --auto-on"
  exit 0
fi
if [ "$MODE" = "auto-on" ]; then
  rm -f "$AUTO_OFF"
  echo "✅ Automatic updates are back ON."
  echo "   Every session start will install the latest published version."
  exit 0
fi

# ─── Automatic mode preamble ──────────────────────────────────────────────
# WHY THIS MODE EXISTS. Updating used to be a gesture: the hook reported, the
# user typed `brain update`. Nobody typed it. The published engine stayed weeks
# behind the author's, and the only sign was a line at session start that people
# learn to stop reading.
#
# What it costs, said plainly: code from the remote repo now installs itself
# WITHOUT being asked. That is an execution channel. Three counterweights, none
# of them optional:
#   · `$AUTO_OFF` (or CBRAIN_NO_AUTO_UPDATE=1) restores the previous behaviour —
#     report, do not apply. The way out exists before the way in.
#   · the selftest decides. In automatic mode nobody is watching the screen: an
#     update that breaks the tool and LEAVES it broken would be worse than no
#     update at all. So red means roll back, immediately, by the script itself.
#   · nothing ever blocks a session — the hook is what detaches; here we only
#     work quietly into a log.
if [ "$AUTO" = "1" ]; then
  if [ -e "$AUTO_OFF" ] || [ -n "${CBRAIN_NO_AUTO_UPDATE:-}" ]; then exit 0; fi

  # A lock, because several sessions start at the same time. `mkdir` fails when
  # the directory exists: that is the shell's atomic test-and-set, where
  # `[ -f ] && touch` leaves a window between the two.
  # Stale lock: a machine that goes to sleep or a session killed mid-run would
  # leave the directory behind forever, and automatic updates would die in
  # silence — exactly the mute failure this is meant to avoid.
  if ! mkdir "$LOCK" 2>/dev/null; then
    if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
      rm -rf "$LOCK"; mkdir "$LOCK" 2>/dev/null || exit 0
    else
      exit 0                      # another session is already on it
    fi
  fi
  trap 'rm -rf "$LOCK"' EXIT INT TERM

  # Everything this script says goes to the log: in automatic mode there is no
  # screen. The log is overwritten on each pass — we want the last failure
  # readable, not a file that grows while nobody ever goes back to it.
  exec >"$JOURNAL" 2>&1
  echo "=== auto-update $(date '+%Y-%m-%d %H:%M:%S') ==="
fi

# Writes the report the hook will show at the NEXT session. One line, two
# fields: the outcome, then the version it concerns.
result() { [ "$AUTO" = "1" ] && printf '%s\t%s\n' "$1" "$2" > "$RESULT"; return 0; }

say()  { echo "  $*"; }
warn() { echo "  ⚠️  $*"; }

# ─── The switch itself ───────────────────────────────────────────────────────
# ATOMIC, and it has to be. `~/.c-brain/engine` is what the trunk's mounts, the
# `brain` CLI, the Claude Code hooks and the launchd jobs all resolve through, so
# for the instant it does not exist, every one of them is broken — and sessions
# start at moments we do not choose. `ln -s` onto an existing path fails, and
# `rm` then `ln` leaves exactly that hole. Creating the link under a temporary
# name and `mv`-ing it over is a single rename(2): readers see the old target or
# the new one, never nothing.
# ⚠ `-h` IS NOT OPTIONAL, and leaving it out does not fail — it does something
# else entirely. `~/.c-brain/engine` is a symlink to a DIRECTORY, and `mv -f`
# stats its destination, follows it, and moves the new link INSIDE the old
# version. The engine never switches, and an immutable version quietly gains a
# stray file that breaks its own manifest. Measured on 2026-08-17: with `-f` the
# link still pointed at v1.0.0 and `versions/v1.0.0/.engine.switching.12345` had
# appeared. The update still seemed to work, because the `install.sh` replay
# further down relinks the engine with `rm` + `ln -s` — so the real switch was
# happening non-atomically, in a different file, by accident.
# `-h` renames the LINK itself: one rename(2), no window, nothing followed.
switch_to() {   # switch_to <version-name>
  local name="$1" tmp="$CB/.engine.switching.$$"
  [ -d "$VERSIONS/$name" ] || return 1
  ln -sfn "$VERSIONS/$name" "$tmp" || return 1
  mv -hf "$tmp" "$CB/engine" || { rm -f "$tmp"; return 1; }
  # And CHECK. A switch that silently did not happen is what this comment is
  # about; asserting the result costs one readlink.
  [ "$(readlink "$CB/engine")" = "$VERSIONS/$name" ]
}

# Keep the active version, the one to roll back to, and one spare. Anything older
# is code nobody can reach: `--rollback` only ever names `previous-version`.
# Pruning runs AFTER a successful switch, never before — a version we might still
# need must not be removed on the strength of an update that has not landed.
prune_versions() {
  local keep_active keep_prev n
  keep_active="$(basename "$(cd "$CB/engine" && pwd -P)")"
  keep_prev="$(cat "$PREVIOUS" 2>/dev/null || true)"
  n=0
  # Newest first, so the survivors are the recent ones.
  for d in $(ls -1t "$VERSIONS" 2>/dev/null); do
    [ "$d" = "$keep_active" ] && continue
    [ "$d" = "$keep_prev" ] && continue
    n=$((n + 1))
    [ "$n" -le 1 ] && continue          # one spare beyond active + previous
    rm -rf "${VERSIONS:?}/$d" && say "pruned old version $d"
  done
}

command -v git >/dev/null || { echo "❌ git is required for updates."; exit 1; }

# The version this installation is running, by name. It is the directory name
# under `versions/`, which is also what `$CB/VERSION` records — no git call, and
# nothing to derive: an engine has no history to ask.
# ⚠ MULTI-LINE ON PURPOSE. tests/update_tag_family.sh lifts these functions out of
# this file with `sed '/^current() {/,/^}/p'` rather than re-implementing them, so
# that a change here cannot leave a passing copy behind in the test. A one-line
# definition has no `^}` to stop at, and the extraction swallows the rest of the
# file — the eval then fails and every case reports "command not found".
current() {
  basename "$ENGINE"
}

# Which FAMILY of tags this installation belongs to — English (`v1.2.3`) or
# French (`v1.2.3-fr`).
#
# ⚠ This is not decoration, it is a language-switch bug waiting to happen.
# Tags are not scoped to a branch, so `git tag -l 'v*'` hands back both
# families at once — and `sort -V` places `v1.18.0-fr` AFTER `v1.18.0`.
# Taking the global maximum therefore moved an ENGLISH installation onto the
# FRENCH tree the moment the French branch caught up, with no error at all:
# the tag exists, the checkout succeeds, and the user simply finds their tool
# speaking another language. It stayed hidden only while `fr` lagged behind.
#
# So: read the family off what is installed, and never leave it.
#
# The one case this cannot resolve is a bare tag and an `-fr` tag on the SAME
# commit, where `--exact-match` picks one arbitrarily. That cannot happen here:
# the two branches diverge by construction, `main` being a translation of `fr`.
# If they ever converge, this needs a recorded family instead of a derived one.
# ⚠ RECORDED FAMILY — added on 2026-08-13 together with the end of the `-fr`
# family. The derivation below reads the family off the INSTALLED tag, so it
# cannot remember a choice: a French installation that switched to English
# would fall back to `-fr` at the first doubt. The file settles it, and it only
# exists if somebody wrote it — nobody switches on their own. This is the
# "recorded family instead of a derived one" the note above already called for.
FAMILY_FILE="$STATE/tag-family"

# ⚠ READ OFF THE INSTALLED VERSION NAME, not off a repository. An engine has no
# git history to interrogate any more; what it has is the name the installer gave
# it, which is `git describe` output taken at build time — `v1.29.0`,
# `v1.28.1-24-g6f28312`, `v1.29.0-fr`. That name carries the family just as the
# tag did, and it is the only thing left that can.
family() {
  if [ -f "$FAMILY_FILE" ]; then cat "$FAMILY_FILE"; return; fi
  case "$(current)" in
    *-fr|*-fr-*) echo "-fr" ;;
    *)           echo ""    ;;
  esac
}

# The newest tag of THIS installation's family, by version order rather than
# alphabetical order: without `-V`, v10 would sort before v9.
latest_tag() {
  local suffix rx
  suffix="$(family)"
  if [ -n "$suffix" ]; then rx='^v[0-9]+\.[0-9]+\.[0-9]+-fr$'
  else                      rx='^v[0-9]+\.[0-9]+\.[0-9]+$'; fi
  # `|| true`: with no matching tag `grep` exits 1, and under `set -e` +
  # `pipefail` that would kill the script one line before the empty-result
  # check that already handles it properly.
  git -C "$MIRROR" tag -l 'v*' | grep -E "$rx" | sort -V | tail -1 || true
}

# ─── THE OWNERSHIP GATE ──────────────────────────────────────────────────────
#
# AN UPDATER MAY ONLY REPLACE WHAT IT BUILT.
#
# This used to be a set of guesses about the engine's git state — clean, detached,
# sitting exactly on a release tag — because the engine WAS the user's own clone
# and there was nothing else to go on. Guessing could not work, and did not: a
# `git clone` lands on a branch, so the documented install produced an engine
# that was refused for ever, while a developer's clean checkout parked on a tag
# was adopted as though the installer had put it there.
#
# There is nothing left to guess. A managed engine is a directory THIS INSTALLER
# CREATED, under `versions/`, and provenance is a fact rather than an inference.
# A development engine says so in a file it was given by name. Neither can be
# mistaken for the other, and the update path contains no git command that names
# a directory the user made.
gate_ownership() {   # every replacing path goes through here, rollback included
  refus() {
    echo "❌ $1"
    echo "   Nothing was changed: no version was built, replaced or switched."
    echo "   $2"
    result "blocked" "${NEW:-}"
    exit 1
  }

  # 1. A DEVELOPMENT ENGINE IS NEVER UPDATED. Asked for by name with
  #    `install.sh --dev`, so there is no doubt about intent, and no inspection
  #    of the repository is needed — or possible — to reach the right answer.
  if [ -f "$DEVMARK" ]; then
    echo "Development engine detected."
    echo "Automatic engine updates are disabled for --dev installations."
    echo "   engine: $ENGINE"
    echo "   Update it with git, as the working repository it is."
    result "dev" "${NEW:-}"
    # A configuration, not a failure: in automatic mode this is the expected
    # outcome on a developer's machine and must not be reported as an error.
    [ "$AUTO" = "1" ] && exit 0
    exit 1
  fi

  # 2. NOT OWNED. No marker, no update — and no adoption path any more. Adoption
  #    was the hole: it inferred ownership from a tag, which is exactly what a
  #    developer's checkout can look like.
  if [ ! -f "$MANAGED" ]; then
    refus "This engine carries no managed-install marker." \
          "Run ./install.sh from the source to build a managed engine."
  fi

  # 3. The marker names the versions root this installation owns. The engine must
  #    live INSIDE it: `~/.c-brain/engine` may have been repointed at somebody's
  #    repository since, and a stale marker must not vouch for it.
  OWNED_ROOT="$(cat "$MANAGED" 2>/dev/null)"
  case "$ENGINE/" in
    "$OWNED_ROOT"/*) : ;;
    *) refus "The active engine is not one this installation built." \
             "It owns $OWNED_ROOT, the engine is $ENGINE." ;;
  esac

  # 4. IMMUTABILITY. A version that has changed since it was built is an anomaly,
  #    and it is REPORTED rather than repaired: silently overwriting it would
  #    destroy whatever wrote to it, which is the whole family of faults this
  #    file exists to end.
  if ! verify_manifest "$ENGINE"; then
    refus "The active version has been modified since it was installed." \
          "Run \`brain doctor\` to see what changed. It is not repaired on its own."
  fi
}

# ─── A development engine answers here, and goes no further ──────────────────
# BEFORE the mirror, the fetch and the version arithmetic. Reached later, this
# install would first be told it has no source mirror — which is true, and
# completely beside the point: it is not that the update cannot proceed, it is
# that it must not. Saying the right thing means saying it before the machinery
# has a chance to complain about something else.
if [ -f "$DEVMARK" ] && [ "$MODE" != "auto-off" ] && [ "$MODE" != "auto-on" ]; then
  echo "Development engine detected."
  echo "Automatic engine updates are disabled for --dev installations."
  echo "   engine: $ENGINE"
  echo "   Update it with git, as the working repository it is."
  result "dev" ""
  [ "$AUTO" = "1" ] && exit 0     # expected on a developer's machine, not a failure
  exit 1
fi

# ─── Rollback ───────────────────────────────────────────────────────
if [ "$MODE" = "rollback" ]; then
  [ -f "$PREVIOUS" ] || { echo "❌ No previous version on record."; exit 1; }
  target="$(cat "$PREVIOUS")"
  # A rollback replaces the active engine, so it goes through the same gate: the
  # same incident through a different flag is still the same incident.
  gate_ownership
  # ⚠ THE TARGET MUST EXIST. Rolling back used to mean `git checkout <ref>` in a
  # repository that held every version at once, so there was nothing to check.
  # Now a version is a directory, and pruning removes old ones. Landing somewhere
  # else — or on a half-deleted tree — because the recorded version is gone is
  # worse than refusing: the user would be told they had gone back, and they
  # would not have.
  if [ ! -d "$VERSIONS/$target" ]; then
    echo "❌ The previous version ($target) is no longer installed."
    echo "   Nothing was changed. Versions still on disk:"
    ls -1 "$VERSIONS" 2>/dev/null | sed 's/^/     /'
    exit 1
  fi
  echo "⏪ Rolling back to $target"
  switch_to "$target" || { echo "❌ could not switch the engine link."; exit 1; }
  bash "$VERSIONS/$target/install.sh" >/dev/null 2>&1 || warn "install.sh reported a problem"
  echo "✅ Back on $target. Your notes did not move."
  exit 0
fi

# ─── Remote state ─────────────────────────────────────────────────────────
CUR="$(current)"
echo "🔄 C Brain — installed version: $CUR"

# --force: the remote is authoritative on tags. The user never creates any —
# without this, a single tag republished by the author makes the fetch fail
# ("would clobber existing tag") and BLOCKS every subsequent update, while
# reporting "no network". A silent, permanent failure.
# ⚠ INTO THE MIRROR, never into a repository the user made. This is the line
# that makes "the updater does not touch your clone" a structural fact rather
# than a promise somebody has to keep remembering.
if [ ! -d "$MIRROR" ]; then
  say "no source mirror ($MIRROR) — re-run ./install.sh from the source to create it."
  exit 0
fi
if ! FETCH_ERR="$(git -C "$MIRROR" fetch --tags --force origin 2>&1)"; then
  # Offline, unreachable repo, moved remote tag… none of it is blocking, but
  # we do not claim "no network" when the cause is something else: a wrong
  # diagnosis costs more than a slightly longer message.
  say "could not reach the remote versions — will retry later."
  [ -n "$FETCH_ERR" ] && printf '%s\n' "$FETCH_ERR" | head -3 | sed 's/^/     /'
  exit 0
fi

NEW="$(latest_tag)"
[ -n "$NEW" ] || { say "no version published yet."; exit 0; }

if [ "$CUR" = "$NEW" ] && [ "$MODE" != "force" ]; then
  say "already up to date ($NEW)."
  exit 0
fi

echo "  new version available: $NEW"

# WHERE THE CODE COMES FROM. An update replaces the engine — it runs code on
# this machine at the next session. Naming a version is not naming a source: a
# remote can be changed by anyone who can write to the engine's git config, and
# a tag can be moved. So the origin URL and the exact commit are shown BEFORE
# anything is applied, because that is what a person would need to check.
#
# This is disclosure, not verification. Tags are unsigned (see SECURITY.md);
# what follows lets you look, not the machine refuse.
REMOTE_URL="$(git -C "$MIRROR" remote get-url origin 2>/dev/null || echo "unknown")"
TARGET_SHA="$(git -C "$MIRROR" rev-parse --short "$NEW" 2>/dev/null || echo "unknown")"
echo "  from:   $REMOTE_URL"
echo "  commit: $TARGET_SHA"

if [ "$MODE" = "check" ]; then
  echo "  → \`brain update\` to install it."
  exit 10   # 10 = "an update exists", readable by a script
fi

# ─── Applying ──────────────────────────────────────────────────────────
# A hand-edited engine is somebody's work. We do not overwrite it.
#
# EXCEPT when the "work" is the gardening agents editing their own briefs. Those
# directories are mounted inside the trunk as symlinks, so an agent weaving
# `[[...]]` links across the trunk reaches them and dirties the ENGINE repo. That
# used to close a loop: every pass dirtied the engine, the next update refused,
# and the user fell behind for ever, silently. Reported 2026-08-16 by a tester
# on an install stranded exactly this way.
#
# Tolerating it costs nothing: the block further down already runs
# `git checkout -- .` after a successful update, so these edits were always going
# to be discarded. The only thing the refusal protected was the user's ability to
# update — which is what it was destroying.
#
# ⚠️ The refusal STAYS for anything outside those paths: a genuinely hand-edited
# engine is still somebody's work, and still blocks.
# ⚠️ THE PER-PATH EXCEPTION IS GONE, on purpose. It sorted dirty files into
# "engine-owned" and "yours", and quietly restored the first group. But the
# engine-owned list IS the codebase (hooks, capsule, planet, tests), and no test
# could tell an agent's edit from a human's — so the exception's real effect was
# to discard unsaved work under the paths where work actually happens. The
# stranded-install problem it was answering is solved instead by refusing without
# touching anything, and saying which files block: the user unblocks in one
# command, and nobody's edit is spent doing it.
# ─── THE OWNERSHIP GATE ──────────────────────────────────────────────────
#
# AN UPDATER MAY ONLY DESTROY WHAT IT OWNS.
#
# Measured on 2026-08-17, on five real repositories, before this gate existed:
#
#   managed install, on its tag     HEAD moved, tree replaced   legitimate
#   dev repo, clean branch          HEAD moved, BRANCH LOST
#   dev repo, commits above the tag HEAD moved, BRANCH LOST     ← the incident
#   uncommitted work in hooks/      `M hooks/thing.py` → clean  ← work DESTROYED
#
# The last line is the serious one. The block this replaces ran
# `git checkout -- .` over every engine-owned path — hooks, capsule, planet,
# tests, i.e. where ALL the code lives — so a developer's unsaved edits went to
# nothing with a `say` line for a warning. The intent was good (an agent editing
# its own brief must not strand the install), but the remedy was to throw the
# work away, and it could not tell an agent's edit from a human's.
#
# The gate is EXPLICIT, not a guess about paths or symlinks. `state/engine-managed`
# says "the installer put this engine here and owns it". Missing → not owned →
# nothing is touched. It is adopted below for installs that predate the marker,
# but ONLY from a state that could not hold anyone's work.
gate_ownership

# ─── BUILD, TEST, THEN SWITCH ────────────────────────────────────────────────
#
# THE ORDERING IS THE POINT. The old sequence was: check out the new version over
# the live engine, run the migrations, reinstall, and only then find out whether
# any of it worked — rolling back if not. That deliberately creates a window,
# however short, in which the ACTIVE engine is one nobody has checked, and it
# leans on the rollback working at the exact moment something has just proved not
# to. Sessions start during that window; the capsule and the hooks run from it.
#
# Versions living side by side remove the need to accept any of that. The
# candidate is built, verified and selftested while it is INACTIVE, and it
# becomes `~/.c-brain/engine` only after passing. Red means the candidate is
# deleted and the active version was never involved.
CANDIDATE="$VERSIONS/$NEW"

say "building ${NEW}…"
if ! build_version "$MIRROR" "$CANDIDATE" "$NEW"; then
  echo "❌ could not build $NEW from the mirror. Nothing was changed."
  result "blocked" "$NEW"
  exit 1
fi
link_runtime "$CANDIDATE" "$RUNTIME" || warn "shared Electron runtime not mounted on $NEW"

if ! verify_manifest "$CANDIDATE"; then
  echo "❌ $NEW does not match its own manifest — the build is not trustworthy."
  rm -rf "$CANDIDATE"
  result "blocked" "$NEW"
  exit 1
fi

# ─── Migrations ───────────────────────────────────────────────────────────
# Numbered, run exactly once, never destructive to content. They come from the
# CANDIDATE — they are what the new version needs done — and they run before the
# switch so that a failing one leaves the active engine where it was.
touch "$APPLIED"
for m in "$CANDIDATE"/cbrain/migrations/*.sh; do
  [ -e "$m" ] || continue
  name="$(basename "$m")"
  grep -qxF "$name" "$APPLIED" && continue
  # ${name} with braces, mandatory: glued to a UTF-8 character, bash on macOS
  # swallows it into the variable NAME ("name… : unbound variable") and kills
  # the update mid-flight.
  say "migration ${name}…"
  if bash "$m"; then
    echo "$name" >> "$APPLIED"
  else
    warn "migration $name failed — stopping. The engine was NOT switched."
    rm -rf "$CANDIDATE"
    result "blocked" "$NEW"
    exit 1
  fi
done

# ─── The control that decides, on the candidate itself ───────────────────────
# The engine path is passed explicitly. Without it `selftest.sh` resolves its
# scripts through the trunk's mounts — which point at the ACTIVE engine — and it
# would go green having tested the version we are trying to replace.
say "selftest on $NEW (still inactive)…"
if bash "$CANDIDATE/hooks/selftest.sh" "$CANDIDATE" >/tmp/c-brain-update-selftest.log 2>&1; then
  say "selftest green — switching"
else
  echo
  warn "selftest FAILED on $NEW (/tmp/c-brain-update-selftest.log)"
  warn "the candidate was DELETED. The engine is still $CUR — it was never switched."
  rm -rf "$CANDIDATE"
  result "blocked" "$NEW"
  exit 1
fi

# ─── The switch ──────────────────────────────────────────────────────────────
echo "$CUR" > "$PREVIOUS"
switch_to "$NEW" || { echo "❌ could not switch the engine link. Still on $CUR."; exit 1; }
say "engine now on $NEW"

# Replaying the installer propagates what the symlink cannot: the statusline is a
# COPY in ~/.claude, the launchd jobs and the settings hooks are generated files.
# Everything else was switched by the link itself.
say "reinstalling (idempotent)…"
bash "$CANDIDATE/install.sh" >/tmp/c-brain-update.log 2>&1 || warn "install.sh reported a problem (/tmp/c-brain-update.log)"

# The installer must not have dirtied the version it just mounted. npm used to do
# exactly that (it rewrites package-lock.json where it runs), which is why it now
# runs in the shared runtime instead. If anything else ever does, say so rather
# than quietly restoring: a version that changes under us is a fact worth seeing.
verify_manifest "$CANDIDATE" || warn "$NEW no longer matches its manifest after the reinstall — \`brain doctor\`"

prune_versions

echo
echo "✅ Updated to $NEW — selftest was green BEFORE the switch. Your notes were not touched."
result "ok" "$NEW"
