#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# publish.sh — publish a version. The ONLY sanctioned path to a `git push`.
#
# Why this script exists: the leak check was once run at the end of a pipe
# (`leakcheck.py | tail -1 && git push`). `tail` always succeeds — so the `&&`
# tested the wrong exit code, and a push went out while the check was RED. The
# guard existed; it was simply short-circuited by how it was called.
#
# Here there is no pipe and no `&&`: the check is an explicit `if`, and its
# failure stops everything.
#
# Usage: ./publish.sh v1.2.3 "tag message"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)"
cd "$ROOT"

TAG="${1:-}"
MSG="${2:-}"
[ -n "$TAG" ] || { echo "Usage: ./publish.sh v1.2.3 \"tag message\""; exit 1; }
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-z]+)?$ ]] || { echo "❌ Expected a vX.Y.Z tag"; exit 1; }
[ -n "$MSG" ] || { echo "❌ A tag message is required."; exit 1; }

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# --- `main` IS THE PRODUCT, `fr` IS A STAGING BUFFER (decision of 2026-08-13) --
# `fr` used to be a released product too, with its own `-fr` tag family. That cost
# more than it gave:
#   · `sort -V` places `v1.27.0-fr` AFTER `v1.27.0`, so any "latest tag" selector
#     that scans every tag moves an English install onto the French tree. It stayed
#     invisible only while `fr` lagged behind; bringing it level ARMED it.
#   · `fr` cannot be published without a clean sync from the author's living Brain,
#     so unfinished work on that machine blocks a release that has nothing to do
#     with it — measured the same day.
# `fr` remains what it always really was: the French landing strip of the sync,
# read by nobody but the translation step. Published tags stay published — a moved
# tag breaks the fetch of anyone still on it — so the `-fr` family simply stops
# growing at v1.27.0-fr.
if [ "$BRANCH" = "fr" ] && [ "${CBRAIN_ALLOW_TAG_ON_FR:-}" != "1" ]; then
  echo "❌ \`fr\` is a staging buffer, not a product — nothing is published from it."
  echo "   The engine ships from \`main\`, which is the translated, public branch."
  echo "   → git checkout main    (or CBRAIN_ALLOW_TAG_ON_FR=1 if you know why)"
  exit 1
fi

echo "▸ Does the package still match the living Brain?"
if [ "$BRANCH" = "fr" ]; then
  if ! ./sync.sh --check >/dev/null 2>&1; then
    echo "❌ The package has drifted. Run ./sync.sh, read the diff, then retry."
    exit 1
  fi
  echo "  ✅ up to date"
else
  # Only `fr` is synced from the living Brain; `main` is translated from `fr`.
  # Running the drift check here would compare English files against a French
  # source and always fail.
  echo "  ⤳ skipped on \`$BRANCH\` (only \`fr\` syncs from the Brain)"
fi

# Prose has no test, so it never fails — it just quietly describes a program that
# stopped behaving that way. `docs_aligned.py` does not read the prose; it asks
# one mechanical question: has the code a document claims to describe moved since
# that document was last edited? A version that ships with unreviewed docs ships a
# manual for a different program, and the reader has no way to tell.
# IT REFUSES. It only warned for a few hours, while four documents were behind:
# a gate nobody can satisfy teaches people to skip the script, which is worse than
# no gate. The backlog reached zero the same day, so the gate closed — a promise
# to tighten "later" is a promise nobody keeps.
# The cost of being wrong here is one doc edit. The cost of being wrong the other
# way is a published version whose manual describes a different program.
echo "▸ Do the docs still describe this code?"
if ! python3 tests/docs_aligned.py; then
  echo
  echo "⛔ A document has not been reviewed since the code it describes moved."
  echo "   Open it, check the claim, edit it — that commit is the new baseline."
  echo "   Nothing is published."
  exit 1
fi
echo "  ✅ every document reviewed since the code it describes last moved"

echo "▸ Is the working tree clean?"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "❌ Uncommitted changes. Commit first."
  exit 1
fi
echo "  ✅ clean"

echo "▸ Leak check (history included)"
if ! python3 leakcheck.py --history; then
  echo
  echo "⛔ LEAK — nothing is published."
  exit 1
fi

echo "▸ Is the tag already taken?"
if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "❌ $TAG already exists. Take the next number."
  echo "   NEVER move a published tag: for users still on an older version the"
  echo "   fetch fails and updates lock up for good."
  exit 1
fi

# The plugin manifest carries an explicit version, and Claude Code will NOT
# hand users an update until that string changes — pushing commits alone does
# nothing. Leaving it to a human is the same class of gesture as translating,
# and we already know how that ends. So the tag writes it, here, once.
PLUGIN_MANIFEST=".claude-plugin/plugin.json"
if [ -f "$PLUGIN_MANIFEST" ]; then
  python3 - "$PLUGIN_MANIFEST" "${TAG#v}" <<'PYEOF'
import json, re, sys
path, version = sys.argv[1], sys.argv[2].removesuffix("-fr")
raw = open(path, encoding="utf-8").read()
# A targeted substitution, not a re-dump: json.dump would reflow the whole file
# and turn every release into a diff nobody can read.
new = re.sub(r'("version"\s*:\s*)"[^"]*"', lambda m: m.group(1) + '"%s"' % version, raw, count=1)
if new != raw:
    open(path, "w", encoding="utf-8").write(new)
    print("  plugin.json version → %s" % version)
else:
    print("  plugin.json already at %s" % version)
PYEOF
  if ! git diff --quiet -- "$PLUGIN_MANIFEST"; then
    git add "$PLUGIN_MANIFEST"
    git commit -q -m "Plugin manifest: version $TAG"
    echo "  committed the version bump"
  fi
fi

# The CURRENT branch, never a hardcoded `main` — BRANCH is already resolved at
# the top of this script. Hardcoding it meant a publish from `fr` pushed the tag
# and an already up-to-date main branch, while the French commits never left.
# The tag hid the hole, since it carries the objects: `brain update` worked, but
# the remote `fr` branch stayed frozen. Fixed here in c91c10d; `fr` only caught
# up on 2026-07-27, after two releases had gone out with the branch behind.
git tag -a "$TAG" -m "$MSG"
git push origin "$BRANCH" "$TAG"
echo
echo "✅ $TAG published on $BRANCH."
