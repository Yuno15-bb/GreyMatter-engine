#!/usr/bin/env bash
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# engine-lib.sh — building, verifying and mounting an ENGINE VERSION.
#
# Sourced by install.sh and greymatter/update.sh. One definition, two consumers: the
# installer builds the first version, the updater builds every one after it, and
# they must agree byte for byte on what a version IS — or `doctor` would report
# an anomaly on a tree the updater had just written correctly.
#
# A VERSION IS IMMUTABLE. It is an export: no `.git`, no history, no remote —
# code and nothing else. Two things are added to it, both by us, both known:
# `.greymatter-manifest` (the integrity oracle) and `capsule/macos/.build` (a link
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
    # hash. `capsule/macos/.build` is pruned because it is a link into the shared
    # runtime — a build output that belongs to no version in particular.
    find . -type f ! -name .greymatter-manifest -not -path './capsule/macos/.build/*' -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 shasum -a 256 > .greymatter-manifest ) || return 1
}

manifest_of() {      # manifest_of <version-dir> → the manifest's file name, or nothing
  # A version built by an updater from before the rename carries its manifest
  # under the old name — it is still that version's own, honest oracle.
  local dir="$1"
  if [ -f "$dir/.greymatter-manifest" ]; then echo .greymatter-manifest
  elif [ -f "$dir/.cbrain-manifest" ]; then echo .cbrain-manifest   # pre-rename
  fi
}

verify_manifest() {  # verify_manifest <version-dir> → 0 intact, 1 changed/missing
  local dir="$1" m
  m="$(manifest_of "$dir")"
  [ -n "$m" ] || return 1
  ( cd "$dir" && shasum -a 256 -c --status "$m" ) 2>/dev/null
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
    git clone --bare --quiet "$repo" "$mirror" || return 1   # git says why; the caller says what
    # Point the mirror at the SOURCE's own origin, not at the user's clone: an
    # update must follow the published repository, not a copy on this disk that
    # may never be fetched again.
    local up
    up="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
    [ -n "$up" ] && git -C "$mirror" remote set-url origin "$up" 2>/dev/null || true
  fi
}

# ─── The native capsule, built beside the version ───────────────────────────
# The capsule is a small Swift app (capsule/macos). Its build output cannot live
# inside the version: a version is immutable, and `swift build` writes a 120 MB
# scratch folder where it runs. So the build happens in the runtime directory,
# only the binary (under 1 MB) is kept, and the version holds one symlink,
# `capsule/macos/.build` — the path the hooks and `brain capsule` launch.
#
# The runtime is keyed by the hash of the Swift sources: two versions whose
# capsule code is identical share one binary, and a version that changes the
# capsule gets its own, with no version of ours to bump.
capsule_dir() {      # capsule_dir <version-dir> <runtime-root> → prints the path
  local eng="$1" root="$2" key
  key="$( cd "$eng/capsule/macos" 2>/dev/null \
          && find Package.swift Sources -type f 2>/dev/null | LC_ALL=C sort \
          | xargs shasum -a 256 2>/dev/null | shasum -a 256 | cut -c1-12 )"
  [ -n "$key" ] || key="nokey"
  printf '%s/capsule-native-%s\n' "$root" "$key"
}

capsule_bin() {      # capsule_bin <version-dir> → the binary the hooks launch
  printf '%s/capsule/macos/.build/release/Capsule\n' "$1"
}

link_capsule() {     # link_capsule <version-dir> <runtime-root>
  local eng="$1" root="$2" rt
  [ -f "$eng/capsule/macos/Package.swift" ] || return 0
  rt="$(capsule_dir "$eng" "$root")"
  mkdir -p "$rt/release" || return 1
  rm -rf "$eng/capsule/macos/.build"
  ln -s "$rt" "$eng/capsule/macos/.build"
}

# build_capsule <version-dir> <runtime-root> [log] → 0 when the binary exists.
# Needs Apple's Command Line Tools (Swift 6). Nothing is downloaded: the package
# has no dependency. Already built for these sources → nothing to do.
build_capsule() {
  local eng="$1" root="$2" log="${3:-/dev/null}" rt scratch
  [ -f "$eng/capsule/macos/Package.swift" ] || return 1
  link_capsule "$eng" "$root" || return 1
  rt="$(capsule_dir "$eng" "$root")"
  [ -x "$rt/release/Capsule" ] && return 0
  command -v swift >/dev/null 2>&1 && xcode-select -p >/dev/null 2>&1 || return 1
  scratch="$rt.building.$$"
  rm -rf "$scratch"
  if swift build -c release --package-path "$eng/capsule/macos" --scratch-path "$scratch" >"$log" 2>&1 \
     && [ -x "$scratch/release/Capsule" ]; then
    cp "$scratch/release/Capsule" "$rt/release/Capsule.tmp" && mv "$rt/release/Capsule.tmp" "$rt/release/Capsule"
  fi
  rm -rf "$scratch"
  [ -x "$rt/release/Capsule" ]
}
