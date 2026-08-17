#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# engine-lib.sh — building, verifying and mounting an ENGINE VERSION.
#
# Sourced by install.sh and cbrain/update.sh. One definition, two consumers: the
# installer builds the first version, the updater builds every one after it, and
# they must agree byte for byte on what a version IS — or `doctor` would report
# an anomaly on a tree the updater had just written correctly.
#
# A VERSION IS IMMUTABLE. It is an export: no `.git`, no history, no remote —
# code and nothing else. Two things are added to it, both by us, both known:
# `.cbrain-manifest` (the integrity oracle) and `capsule/node_modules` (a link
# into the shared runtime). Anything else that differs from the manifest is an
# anomaly, and it is REPORTED, never silently repaired.

# ─── The integrity oracle ────────────────────────────────────────────────────
# A version has no `.git`, so `git status` cannot say whether it changed. The
# manifest replaces it: sha256 of every exported file, in `shasum -c` format so
# verification needs no parser of ours.
write_manifest() {   # write_manifest <version-dir>
  local dir="$1"
  ( cd "$dir" || return 1
    # -type f only, and the manifest itself excluded: it cannot contain its own
    # hash. `capsule/node_modules` is pruned because it is a link into the shared
    # runtime — 250 MB that belong to no version in particular.
    find . -type f ! -name .cbrain-manifest -not -path './capsule/node_modules/*' -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 shasum -a 256 > .cbrain-manifest ) || return 1
}

verify_manifest() {  # verify_manifest <version-dir> → 0 intact, 1 changed/missing
  local dir="$1"
  [ -f "$dir/.cbrain-manifest" ] || return 1
  ( cd "$dir" && shasum -a 256 -c --status .cbrain-manifest ) 2>/dev/null
}

# ─── Building a version ──────────────────────────────────────────────────────
# `git archive` rather than a copy: it emits exactly the TRACKED files, so an
# engine can never inherit a developer's untracked scratch file, a stray
# `node_modules`, or a `.env`. The tree is assembled beside its final name and
# moved into place, so an interrupted build never leaves a half-written version
# that `verify_manifest` would then have to catch.
build_version() {    # build_version <git-repo> <dest-dir> [ref]
  local repo="$1" dest="$2" ref="${3:-HEAD}" tmp
  tmp="$dest.building.$$"
  rm -rf "$tmp" && mkdir -p "$tmp" || return 1
  if ! git -C "$repo" archive --format=tar "$ref" | tar -x -C "$tmp"; then
    rm -rf "$tmp"; return 1
  fi
  write_manifest "$tmp" || { rm -rf "$tmp"; return 1; }
  rm -rf "$dest" && mv "$tmp" "$dest" || { rm -rf "$tmp"; return 1; }
}

# ─── The mirror the updater fetches into ─────────────────────────────────────
# WHY IT EXISTS. The old updater ran `git fetch` inside the user's own clone,
# because that clone WAS the engine. Now that it is not, the update path needs a
# repository of its own — or it would have to reach back into a directory it has
# just promised never to touch. A bare mirror costs nothing and keeps the
# promise structural rather than careful.
mirror_source() {    # mirror_source <git-repo> <mirror-dir>
  local repo="$1" mirror="$2"
  git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || return 0   # zip download: no mirror
  if [ -d "$mirror" ]; then
    git -C "$mirror" fetch --tags --force --quiet origin '+refs/heads/*:refs/heads/*' 2>/dev/null || true
  else
    git clone --bare --quiet "$repo" "$mirror" 2>/dev/null || return 1
    # Point the mirror at the SOURCE's own origin, not at the user's clone: an
    # update must follow the published repository, not a copy on this disk that
    # may never be fetched again.
    local up
    up="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
    [ -n "$up" ] && git -C "$mirror" remote set-url origin "$up" 2>/dev/null || true
  fi
}

# ─── The shared Electron runtime ─────────────────────────────────────────────
# MEASURED: `capsule/node_modules` is 250 MB, against 11.6 MB for the whole
# exported engine. Installing it per version would make a version cost 22 times
# what its code costs, for a dependency that is identical across versions whose
# `capsule/package.json` is identical — so the runtime is keyed by the hash of
# that file. Same dependencies → same runtime, shared. Different → a new one,
# automatically, with no version of ours to bump.
#
# npm also REWRITES `package-lock.json` where it runs. Running it inside the
# version would mutate an immutable tree at every install and make `doctor`
# report an anomaly the installer had caused itself. So npm runs in the runtime
# directory, and the version only ever holds a symlink.
runtime_dir() {      # runtime_dir <version-dir> <runtime-root> → prints the path
  local eng="$1" root="$2" key
  key="$(shasum -a 256 "$eng/capsule/package.json" 2>/dev/null | cut -c1-12)"
  [ -n "$key" ] || key="nokey"
  printf '%s/capsule-%s\n' "$root" "$key"
}

link_runtime() {     # link_runtime <version-dir> <runtime-root>
  local eng="$1" root="$2" rt
  [ -f "$eng/capsule/package.json" ] || return 0
  rt="$(runtime_dir "$eng" "$root")"
  mkdir -p "$rt" || return 1
  cp "$eng/capsule/package.json" "$rt/package.json" 2>/dev/null || return 1
  [ -f "$eng/capsule/package-lock.json" ] && cp "$eng/capsule/package-lock.json" "$rt/" 2>/dev/null
  mkdir -p "$rt/node_modules"
  rm -rf "$eng/capsule/node_modules"
  ln -s "$rt/node_modules" "$eng/capsule/node_modules"
}
