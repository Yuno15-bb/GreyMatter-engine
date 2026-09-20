#!/bin/zsh
# C Brain — capsule: a refused second instance must NAME the one holding the lock.
#
# WHAT THIS BENCH MEASURES: not an exit code — the PRINTED output. Before the
# 2026-09-19 fix, a second capsule launched by hand exited 0 with zero bytes on
# stdout and zero on stderr. A capsule that refuses without saying anything is
# indistinguishable from a capsule that is broken, and the known-friction note
# in main.js says it cost half an hour of chasing exactly that.
#
# WHY IT CANNOT DISTURB A RUNNING CAPSULE. Electron's lock lives in `userData`,
# and `--user-data-dir` moves that directory: the witness and the refused
# instance share a THROWAWAY lock inside a temporary folder. Any capsule already
# running keeps its own and is never killed, never even queried. (Checked: under
# `--user-data-dir`, `app.getPath('userData')` follows the flag and so does the
# lock — without that, every assertion here would be about the wrong instance.)
#
# ⚠️ THIS BENCH PUTS A SECOND ORB ON SCREEN for a few seconds. That is the price
#    of testing the real capsule instead of a copy of its logic: the witness has
#    to be main.js itself, since main.js is what writes the identity marker that
#    the refused instance reads back.
#
# WHERE THIS LIVES, AND WHY IT IS NOT IN THE AUTHOR'S TRUNK. `capsule/main.js`
# is frozen on both sides — sync.sh excludes it, because the author's copy is a
# V2 work in progress. A test follows the file it measures, so this one is
# excluded too, under its own name, alongside the author's French bench. Both
# names are listed in sync.sh; removing either one would let the next copy
# overwrite or delete this file.
#
# Run: ./capsule/test_lock_speaks.sh
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ELECTRON="$HERE/node_modules/.bin/electron"
TMP="$(mktemp -d)"
FAILURES=0
PID_NODE=""; PID_APP=""; PID_D_NODE=""; PID_D_APP=""

cleanup() {
  [ -n "$PID_APP" ] && kill "$PID_APP" 2>/dev/null
  [ -n "$PID_NODE" ] && kill "$PID_NODE" 2>/dev/null
  [ -n "$PID_D_APP" ] && kill "$PID_D_APP" 2>/dev/null
  [ -n "$PID_D_NODE" ] && kill "$PID_D_NODE" 2>/dev/null
  rm -rf "$TMP"
}
trap cleanup EXIT

check() {  # $1 = label, $2 = 1 if held, $3 = what was seen
  if [ "$2" = "1" ]; then print -r -- "  ✅ $1"
  else print -r -- "  ❌ $1"; print -r -- "       saw: $3"; FAILURES=$((FAILURES+1)); fi
}

witness() {  # $1 = script to run — a real capsule taking the throwaway lock
  "$ELECTRON" "$1" --user-data-dir="$TMP/ud" >/dev/null 2>"$TMP/witness.err" &
  PID_NODE=$!
  local i
  for i in $(seq 1 60); do
    [ -s "$TMP/ud/instance.json" ] && { PID_APP=$(sed -n 's/.*"pid":\([0-9]*\).*/\1/p' "$TMP/ud/instance.json"); return 0; }
    sleep 0.3
  done
  return 1
}

refused() {  # $1 = script to run; captures its output, sets EXIT_B
  "$ELECTRON" "$1" --user-data-dir="$TMP/ud" >"$TMP/b.out" 2>"$TMP/b.err"
  EXIT_B=$?
}

[ -x "$ELECTRON" ] || { print -r -- "⏭️  electron missing — bench skipped"; exit 0; }

print -r -- "── A. the refusal speaks, and names who holds the lock ──"
witness "$HERE/main.js" || { print -r -- "❌ the witness never took the lock within 18s"; exit 1; }
refused "$HERE/main.js"
MSG="$(cat "$TMP/b.err")"
PID_SAID="$(print -r -- "$MSG" | sed -n 's/.*pid \([0-9][0-9]*\).*/\1/p' | head -1)"

check "the refusal is no longer mute: stderr has something to say" \
      "$([ -s "$TMP/b.err" ] && echo 1 || echo 0)" "$(wc -c < "$TMP/b.err") bytes"
check "…and nothing goes to stdout (normal output stays clean)" \
      "$([ ! -s "$TMP/b.out" ] && echo 1 || echo 0)" "$(head -c 120 "$TMP/b.out")"
check "…it names a pid, and that pid really is running a capsule" \
      "$([ -n "$PID_SAID" ] && ps -p "$PID_SAID" -o command= 2>/dev/null | grep -q capsule && echo 1 || echo 0)" \
      "announced pid « $PID_SAID » → $(ps -p "${PID_SAID:-0}" -o command= 2>/dev/null | head -c 90)"
check "…it names the DIRECTORY it runs from, not just a pid" \
      "$(print -r -- "$MSG" | grep -qF "$HERE" && echo 1 || echo 0)" "$MSG"
check "…and it says what to do about it" \
      "$(print -r -- "$MSG" | grep -q "kill $PID_SAID" && echo 1 || echo 0)" "$MSG"
print -r -- "     (exit code: $EXIT_B — informative only: a refusal is not a failure,"
print -r -- "      the other instance was told to show itself again)"

print -r -- "── B. no marker: say you do not know, do not guess ──"
# The real case: the capsule holding the lock predates this fix, so it never
# announced itself. The refusal has to say so instead of falling silent again.
rm -f "$TMP/ud/instance.json"
refused "$HERE/main.js"
MSG2="$(cat "$TMP/b.err")"
check "with no marker, the refusal still speaks…" \
      "$([ -s "$TMP/b.err" ] && echo 1 || echo 0)" "$(wc -c < "$TMP/b.err") bytes"
check "…and admits it does not know who, instead of naming one by guesswork" \
      "$(print -r -- "$MSG2" | grep -q "did not announce itself" && echo 1 || echo 0)" "$MSG2"

print -r -- "── C. sabotage: put the silence back, A must go red ──"
# ⚠ The sabotage must produce VALID code. A syntax error would make Electron
#   exit with its own trace on stderr — the bench would pass on a message that
#   is not ours, or fail for the wrong reason.
sed 's|^  process.stderr.write(explainRefusal());$|  // mute, the way it was before 2026-09-19|' \
    "$HERE/main.js" > "$HERE/main-sabotaged.js"
if ! grep -q "mute, the way it was" "$HERE/main-sabotaged.js"; then
  print -r -- "  ❌ the sabotage replaced nothing — the targeted line has changed shape"
  FAILURES=$((FAILURES+1))
else
  refused "$HERE/main-sabotaged.js"
  check "SABOTAGE: without that line the refusal falls mute again (so the bench bites)" \
        "$([ ! -s "$TMP/b.err" ] && echo 1 || echo 0)" "$(head -c 200 "$TMP/b.err")"
fi
rm -f "$HERE/main-sabotaged.js"

print -r -- "── D. the scope of the lock: one userData, not one machine ──"
# WHY THIS CASE EXISTS. Section A's label used to end with "(the lock is shared
# machine-wide)", and this bench was the proof that it is not — without noticing.
# Every launch above is forced onto ONE throwaway `--user-data-dir` precisely so
# it cannot touch a capsule already running: that isolation only works because
# the lock follows userData. MEASURED outside the bench on 2026-09-20: the
# author's trunk (package name `claude-brain-capsule`) and the shipped package
# (`c-brain-capsule`) had two orbs on screen at the same time. A different
# package name is a different userData is a different lock.
#
# The true statement, which section A now carries and main.js now prints: ONE
# capsule per installation. Two differently-named installations make two.
#
# ITS CALIBRATION IS SECTION A, and that is why no extra sabotage is needed here.
# A launches onto the SAME userData and must be REFUSED; D launches onto another
# and must NOT be. If the lock ever became machine-wide, D's second launch would
# be refused and both of its checks would go red. The pair is the measurement.
"$ELECTRON" "$HERE/main.js" --user-data-dir="$TMP/ud2" >/dev/null 2>"$TMP/d.err" &
PID_D_NODE=$!
for i in $(seq 1 60); do
  [ -s "$TMP/ud2/instance.json" ] && break
  sleep 0.3
done
PID_D_APP="$(sed -n 's/.*"pid":\([0-9]*\).*/\1/p' "$TMP/ud2/instance.json" 2>/dev/null)"
check "a second userData takes its OWN lock: two capsules alive at once" \
      "$([ -n "$PID_D_APP" ] && [ "$PID_D_APP" != "$PID_APP" ] \
          && kill -0 "$PID_APP" 2>/dev/null && kill -0 "$PID_D_APP" 2>/dev/null \
          && echo 1 || echo 0)" \
      "section A pid « $PID_APP » · section D pid « $PID_D_APP »"
check "…and it was never refused — its stderr stays empty" \
      "$([ ! -s "$TMP/d.err" ] && echo 1 || echo 0)" "$(head -c 160 "$TMP/d.err")"

print -r -- ""
if [ "$FAILURES" = "0" ]; then
  print -r -- "✅ the refusal names the instance holding the lock, the sabotage mutes it, and the lock's"
  print -r -- "   scope is one userData — not the machine."
  exit 0
fi
print -r -- "❌ $FAILURES check(s) failed."
exit 1
