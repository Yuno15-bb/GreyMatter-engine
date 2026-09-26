#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# changelog.sh — rewrites CHANGELOG.md from the annotated tags.
#
# WHY IT IS GENERATED. A hand-written changelog is a second place to say what a
# release did, and the second place is the one that rots: the tag message is
# what `publish.sh` demands and what the GitHub release shows, so it is always
# written. Deriving the file from the tags means the file cannot drift from the
# thing it describes — at worst it is stale, never wrong.
#
# The `-fr` tags are left out: they are the same releases in the other
# language, and listing both would double every line for no reader.
#
# Usage: ./cbrain/changelog.sh        (writes CHANGELOG.md at the repo root)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$ROOT"
OUT="CHANGELOG.md"

{
  echo "# Changelog"
  echo
  echo "Generated from the annotated git tags by \`cbrain/changelog.sh\` — do not edit by hand."
  echo "Every entry is the message that was attached to the tag when the version was published."
  echo
  echo "The \`fr\` branch stopped being a released product on 2026-08-13 — it is the staging"
  echo "buffer the engine is synced onto, and \`publish.sh\` refuses to tag from it. The \`-fr\`"
  echo "tags up to v1.27.0-fr stay published (moving a tag breaks the fetch of anyone still on"
  echo "it), and are not listed here."
  echo

  git tag --sort=-creatordate --format='%(refname:short)|%(creatordate:short)|%(contents:subject)' \
  | grep -v -- '-fr|' \
  | while IFS='|' read -r tag date subject; do
      [ -n "$tag" ] || continue
      # Older tags carried their own version number in the subject; strip it so
      # the heading is not "## v1.2.0 — v1.2.0 — …".
      subject="${subject#"$tag" — }"
      echo "## $tag — $date"
      echo
      echo "$subject"
      echo
    done
} > "$OUT"

echo "✅ $OUT rewritten — $(grep -c '^## ' "$OUT") versions"
