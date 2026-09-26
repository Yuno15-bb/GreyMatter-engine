#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# fresh_mac_path.sh — a Mac that has only what Apple ships.
#
# WHY THIS EXISTS. A new Mac has no Homebrew and no Node. Once the Command Line
# Tools are in, it has Apple's git and Apple's python3 (3.9), and nothing else.
# The installer supports that Mac on purpose — "only the capsule is skipped" —
# but the selftest called `node` unconditionally, so the same install ended on
# "❌ selftest: some hooks are broken". Worse, the updater switches versions
# only on a green selftest: on such a Mac every release was refused, for good.
# Every CI runner ships Node, so nothing ever ran the product the way a new
# user's Mac runs it. Found on 2026-09-26, preparing a test install for a blank Mac.
#
# The same blank Mac found a second lock, on EVERY Mac this time. The planet's ↻
# badge had a detector of its own — a regex that lit any note merely MENTIONING a
# resume point — while the selftest compares that badge with the real resume
# points. The shipped agents/narcissus.md only describes "resume points": the
# first regeneration of the graph, which every session does, lit it, and the
# selftest stayed red from then on. The author's engine had dropped that regex on
# 2026-08-14; the English port had kept it.
#
# And a third, found the same day: right after an update the maintenance starts,
# its heartbeat rewrites state/status.json every few seconds, and the selftest —
# which checks that `brain status` leaves that file untouched — read the
# heartbeat's writes as the CLI's. A false red at the update gate.
#
# This bench installs from a clone of this repo with PATH reduced to Apple's own
# directories, asks `brain selftest` for its verdict, then regenerates the graph
# as a first session would and asks again, then asks once more while a
# maintenance is writing.
#
# Run: bash tests/fresh_mac_path.sh [--sabotage node-required|badge-regex|lock-ignored]
#   node-required — puts back the unconditional `node --check`; must go RED.
#   badge-regex   — puts back the badge's own regex detector; must go RED.
#   lock-ignored  — the selftest stops reading the maintenance lock; must go RED.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
SABOTAGE=""
[ "${1:-}" = "--sabotage" ] && SABOTAGE="${2:-}"
APPLE_PATH="/usr/bin:/bin:/usr/sbin:/sbin"
FAILS=0

check() {  # check <exit-code> <label> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

H="$(mktemp -d)"
trap 'rm -rf "$H"' EXIT

# Everything runs with an EMPTY environment: no inherited PATH can slip Node,
# Homebrew or the host's `brain` back in.
fresh() { env -i HOME="$H" USER="${USER:-tester}" LANG=en_US.UTF-8 TERM=dumb \
            PATH="$H/.local/bin:$APPLE_PATH" "$@"; }

echo "▸ the machine this bench claims to be"
# A bench that cannot hide Node would go green for the wrong reason. It says so
# and fails instead: a red here is about the runner, never about the product.
if fresh bash -c 'command -v node' >/dev/null 2>&1; then
  echo "  ❌ node is reachable from $APPLE_PATH — this runner cannot play a new Mac"; exit 1
fi
for tool in python3 git; do
  fresh bash -c "command -v $tool" >/dev/null 2>&1 \
    || { echo "  ❌ $tool missing from $APPLE_PATH — the Command Line Tools are a prerequisite"; exit 1; }
done
echo "  ✅ no node · $(fresh python3 --version 2>&1) · $(fresh git --version 2>&1)"

# install.sh builds the engine from the source's COMMITTED tree, so the bench
# installs from a clone: a sabotage has to be a commit to reach the engine.
SRC="$H/src"
git clone -q "$ROOT" "$SRC" || { echo "  ❌ could not clone $ROOT"; exit 1; }
if [ "$SABOTAGE" = "node-required" ]; then
  sed -i '' 's/^if command -v node >\/dev\/null 2>&1; then$/if true; then/' "$SRC/hooks/selftest.sh"
  git -C "$SRC" diff --quiet && { echo "  ❌ sabotage did not apply"; exit 1; }
  git -C "$SRC" -c user.name=bench -c user.email=bench@localhost \
    commit -qam "sabotage: node-required" || { echo "  ❌ sabotage commit failed"; exit 1; }
  echo "  ⚠ sabotage node-required: node --check is unconditional again"
elif [ "$SABOTAGE" = "badge-regex" ]; then
  sed -i '' 's/"resume": rel_file in resume_points,/"resume": bool(re.search(r"resume point", text, re.I)),/' \
    "$SRC/hooks/graph_export.py"
  git -C "$SRC" diff --quiet && { echo "  ❌ sabotage did not apply"; exit 1; }
  git -C "$SRC" -c user.name=bench -c user.email=bench@localhost \
    commit -qam "sabotage: badge-regex" || { echo "  ❌ sabotage commit failed"; exit 1; }
  echo "  ⚠ sabotage badge-regex: the ↻ badge has its own detector again"
elif [ "$SABOTAGE" = "lock-ignored" ]; then
  sed -i '' 's/\[ -e state\/maintenance.lock \] \&\& busy=1/:/' "$SRC/hooks/selftest.sh"
  git -C "$SRC" diff --quiet && { echo "  ❌ sabotage did not apply"; exit 1; }
  git -C "$SRC" -c user.name=bench -c user.email=bench@localhost \
    commit -qam "sabotage: lock-ignored" || { echo "  ❌ sabotage commit failed"; exit 1; }
  echo "  ⚠ sabotage lock-ignored: the selftest no longer sees the maintenance"
elif [ -n "$SABOTAGE" ]; then
  echo "unknown sabotage: $SABOTAGE"; exit 2
fi

echo "▸ install, the way a new Mac runs it"
# --no-launchd: a bench never registers jobs on the machine running it. The
# capsule is NOT declined — the installer has to find Node missing by itself,
# as it does for a user. stdin is not a terminal, so it asks nothing.
OUT="$(cd "$SRC" && fresh ./install.sh --no-launchd </dev/null 2>&1)"
printf '%s' "$OUT" | grep -q "Node.js is missing"
check $? "the installer noticed Node is missing and skipped only the capsule"
printf '%s' "$OUT" | grep -q "❌"
[ $? -ne 0 ]; check $? "the install output holds no ❌" \
  "$(printf '%s' "$OUT" | grep '❌' | head -3 | tr '\n' ' ')"

echo "▸ the verdict the updater relies on"
ST="$(fresh brain selftest 2>&1)"; rc=$?
check "$rc" "brain selftest is green without Node" \
  "$(printf '%s' "$ST" | grep '❌' | head -3 | tr '\n' ' ')"
printf '%s' "$ST" | grep -q "⏭  capsule syntax not checked"
check $? "the skipped check is named, not silently dropped"

echo "▸ after a first session"
# Every session regenerates the planet's graph (track_read after a read, the
# session-end maintenance). The selftest reads that file, so its verdict before
# the first session proves nothing about the days after.
fresh python3 "$H/.c-brain/trunk/hooks/graph_export.py" >/dev/null 2>&1
fresh python3 -c 'import json,sys; g=json.load(open(sys.argv[1])); sys.exit(0 if "head" in g else 1)' \
  "$H/.c-brain/trunk/planet/graph.json"
check $? "the planet's graph exists and names the HEAD it describes"
ST="$(fresh brain selftest 2>&1)"; rc=$?
check "$rc" "brain selftest is still green once the graph exists" \
  "$(printf '%s' "$ST" | grep '❌' | head -3 | tr '\n' ' ')"

echo "▸ while the maintenance is running"
# What the session-end maintenance does, reduced to the part that matters here:
# it holds the lock, and its heartbeat rewrites status.json until it is done.
T="$H/.c-brain/trunk"
fresh python3 "$T/hooks/brain_status.py" idle >/dev/null 2>&1
: > "$T/state/maintenance.lock"
( while [ -e "$T/state/maintenance.lock" ]; do
    fresh python3 "$T/hooks/brain_status.py" touch >/dev/null 2>&1
  done ) &
HB=$!
ST="$(fresh brain selftest 2>&1)"; rc=$?
rm -f "$T/state/maintenance.lock"; wait "$HB" 2>/dev/null
check "$rc" "brain selftest stays green while the maintenance writes status.json" \
  "$(printf '%s' "$ST" | grep '❌' | head -3 | tr '\n' ' ')"
printf '%s' "$ST" | grep -q "⏭  status.json not compared"
check $? "the skipped comparison is named, not silently passed"

if [ "$FAILS" -eq 0 ]; then
  echo "✅ a Mac with only Apple's tools installs GreyMatter and passes its selftest — before a first session, after it, and while the maintenance runs"
  exit 0
fi
echo "❌ $FAILS check(s) failed"
exit 1
