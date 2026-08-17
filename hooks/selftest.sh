#!/usr/bin/env bash
# selftest — checks that the hooks do not crash and exit with code 0.
# Un hook qui plante en silence est pire qu'absent : ce test l'attrape.
#
# Usage: selftest.sh [engine]
#
# WITH NO ARGUMENT it behaves exactly as it always has: the code under test is
# reached through the trunk's mounts, i.e. the ACTIVE engine.
#
# WITH AN ENGINE PATH it tests THAT engine, active or not. This is what lets an
# update check a candidate version BEFORE anything points at it — a version may
# only become `~/.c-brain/engine` after passing its own controls, so there is no
# window, however short, in which the active version is one nobody has checked.
#
# ⚠ THE POINT IS THAT IT MUST NOT MIX THE TWO. Handing the candidate's path to a
# test that still resolves `hooks/…` through the trunk would produce a green on
# the wrong object — the active engine's code, wearing the candidate's name. So
# every script under test is read from $SRC, never from the trunk's symlinks.
# The trunk stays what it is: the DATA the hooks run against.
set -u
BRAIN="$HOME/.c-brain/trunk"
ENGINE="${1:-}"
cd "$BRAIN"
# The code under test. Empty argument → the trunk's mounts → the active engine,
# byte for byte the historical behaviour.
if [ -n "$ENGINE" ]; then
  SRC="$(cd "$ENGINE" 2>/dev/null && pwd -P)" || { echo "❌ selftest: no such engine: $ENGINE"; exit 1; }
else
  SRC="$BRAIN"
fi
fail=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1"; fail=1; }

echo "== C Brain — hook selftest =="

# 1. compilation Python
for f in "$SRC"/hooks/*.py; do
  python3 -m py_compile "$f" 2>/dev/null && ok "compile $f" || ko "compile $f"
done

# 2. capsule main.js
node --check "$SRC/capsule/main.js" 2>/dev/null && ok "node --check main.js" || ko "node --check main.js"

# 3. SessionEnd: auto_maintain must exit 0 even on empty input / a trivial session.
# CLAUDE_BRAIN_GARDENING=1 = ZERO SIDE EFFECTS: without it, if the Inbox has work and the quota
# is open, the test would cross the guards, pull a REAL session off the backlog and launch a
# claude agent (token spend + race risk). A test must never mutate real state.
CLAUDE_BRAIN_GARDENING=1 bash -c "echo '{}' | python3 '$SRC/hooks/auto_maintain.py'"; [ $? -eq 0 ] && ok "auto_maintain exit 0 (empty input, no side effects)" || ko "auto_maintain"

# 4. PostToolUse: on_fiche_write must exit 0 on a target outside the trunk
echo '{"tool_input":{"file_path":"/tmp/horstronc.md"}}' | python3 "$SRC/hooks/on_fiche_write.py"; [ $? -eq 0 ] && ok "on_fiche_write exit 0 (outside the trunk)" || ko "on_fiche_write"

# 5. brain_guard: interpreting a 429 must return 7 (a handled failure, not 0)
tmp=$(mktemp); echo '{"is_error":true,"api_error_status":429,"result":"limit resets 2:50pm"}' > "$tmp"
python3 "$SRC/hooks/brain_guard.py" interpret "$tmp" "selftest-sid"; [ $? -eq 7 ] && ok "brain_guard interpret 429 → exit 7" || ko "brain_guard interpret"
# clean up the test state left behind by interpret.
# CRITICAL: interpret(429) writes state/quota.json = {blocked_until: <future>} (a DICT).
# The old cleanup handled ONLY lists → the quota marker stayed poisoned
# and autonomous maintenance was silently blocked until the fictitious reset time.
# We remove the test sid from the queue AND reset the quota to 0 (unblocked).
python3 - <<'PY' 2>/dev/null
import json,os
B=os.path.expanduser("~/.c-brain/trunk/")
p=B+"state/pending-distill.json"
if os.path.exists(p):
    try:
        d=json.load(open(p))
        if isinstance(d,list): json.dump([s for s in d if s!="selftest-sid"],open(p,"w"))
    except Exception: pass
# reset the quota (and login) — test state must NEVER survive the selftest
try: json.dump({"blocked_until":0,"msg":"ok"},open(B+"state/quota.json","w"))
except Exception: pass
PY
rm -f "$tmp"

# 6. doctor must run (0 healthy / 1 anomalies) without crashing
python3 "$SRC/hooks/brain_doctor.py" --quiet; rc=$?; { [ $rc -eq 0 ] || [ $rc -eq 1 ]; } && ok "brain_doctor runs (rc=$rc)" || ko "brain_doctor crash"

# 7. INVARIANTS — doc↔code relations, sensors that come back down, legacy tolerance.
#    Each past bug is engraved there as a relation, not as a special case.
python3 "$SRC/tests/invariants_brain.py" >/dev/null 2>&1 \
  && ok "invariants_brain (7 relations)" \
  || ko "invariants_brain — a trunk invariant is violated (python3 $SRC/tests/invariants_brain.py)"

# 8. THE FRONT DOOR — the `brain` CLI itself (added 2026-08-04).
#    THE HOLE THAT COST 6 WEEKS: this selftest exercised ONLY hooks. `brain` is not a hook, so
#    nothing ever ran it — and since 2026-06-22 `brain status` had been calling a
#    `brain_status.py show` that DID NOT EXIST. The word "show" was taken for a STATE and WRITTEN
#    into status.json: empty output, exit 0, corrupted capsule. The commit that introduced the
#    bug is THE VERY ONE THAT CREATED THIS SELFTEST, and it announced "12/12 OK".
#    The lesson is in the criterion: "exits 0" does not test a command whose job is to DISPLAY.
#    So we assert on the OUTPUT, and on the ABSENCE of side effects.
#    ⚠ TWO FAULTS IN THIS BLOCK, PAID FOR IN CI ON 2026-08-13:
#      · it assumed `./brain` inside the trunk. That is true FOR THE AUTHOR, whose trunk IS
#        the repository. After a real install there is no `trunk/brain`: install.sh links
#        `~/.c-brain/engine/brain` to `~/.local/bin/brain`. So the CLI is RESOLVED, never
#        guessed.
#      · `$(./brain 2>&1)` captured the shell's "No such file or directory" — so the
#        assertion "it produces output" went GREEN on a MISSING command. That is exactly
#        the fault this block exists to catch, committed inside the block itself.
#        We read stdout ALONE, and we require exit 0 as well.
#      · and, since versions live side by side, `$BRAIN/brain` and `command -v brain` BOTH
#        resolve to the ACTIVE engine. Testing a candidate through either of them would
#        exercise the installed CLI while reporting on the candidate — a green on the wrong
#        object, which is the one failure mode this whole file exists to prevent. When an
#        engine is named, its OWN `brain` is the only one allowed.
BRAIN_CLI=""
if [ -n "$ENGINE" ]; then
  [ -x "$SRC/brain" ] && BRAIN_CLI="$SRC/brain"
else
  for c in "$BRAIN/brain" "$(command -v brain 2>/dev/null || true)"; do
    [ -n "$c" ] && [ -x "$c" ] && { BRAIN_CLI="$c"; break; }
  done
fi
if [ -z "$BRAIN_CLI" ]; then
  ko "brain CLI not found (looked in ${ENGINE:+$SRC}${ENGINE:-$BRAIN/brain and on PATH}) — the front door is not being tested"
else
before=$(cat state/status.json 2>/dev/null)
for c in "" next; do
  # stdout ALONE: an error message on stderr must NEVER count as output.
  out=$("$BRAIN_CLI" $c 2>/dev/null); rc=$?
  [ $rc -eq 0 ] && [ -n "$out" ] \
    && ok "brain ${c:-status} produces output ($(echo "$out" | wc -l | tr -d ' ') line(s))" \
    || ko "brain ${c:-status}: exit $rc, $([ -n "$out" ] && echo 'non-empty output' || echo 'NOTHING on stdout') — a silent display command is broken, even at exit 0"
done
# a READ command must never mutate the state the capsule reads
[ "$(cat state/status.json 2>/dev/null)" = "$before" ] \
  && ok "brain status did not modify state/status.json (pure read)" \
  || ko "brain status MUTATED status.json — this is exactly the 2026-06-22 bug"
# an unknown state must be REFUSED, not recorded (otherwise a typo poisons the capsule)
python3 "$SRC/hooks/brain_status.py" bogus-state >/dev/null 2>&1
[ $? -eq 2 ] && [ "$(cat state/status.json 2>/dev/null)" = "$before" ] \
  && ok "brain_status refuses an unknown state (exit 2, file intact)" \
  || ko "brain_status accepted an unknown state — any typo breaks the capsule"
# do all the subcommands announced in the usage really exist in the case?
if BRAIN_CLI="$BRAIN_CLI" python3 - <<'PYEOF'
import re, subprocess, sys, os
brain = os.environ["BRAIN_CLI"]          # resolved by the script, never guessed
usage = subprocess.run([brain, "no-such-command"], capture_output=True, text=True)
m = re.search(r"brain <([^>]*)>", usage.stdout + usage.stderr)
announced = set(m.group(1).split("|")) if m else set()
src = open(brain).read()
# every alternative of every `case` label
implemented = set()
for lab in re.findall(r"^\s{2}([a-z|]+)\)", src, re.M):
    implemented |= set(lab.split("|"))
missing = sorted(announced - implemented)
if not announced:
    print("usage not found", file=sys.stderr); sys.exit(1)
if missing:
    print("announced but absent: " + " ".join(missing), file=sys.stderr); sys.exit(1)
print(f"{len(announced)} subcommands announced, all implemented")
PYEOF
then ok "usage <-> case: no subcommand announced into the void"
else ko "brain's usage announces a subcommand that does not exist (this is THE kind of gap that created the 2026-06-22 bug)"
fi
fi

echo
[ $fail -eq 0 ] && echo "✅ selftest OK — every hook healthy" || echo "❌ selftest: some hooks are broken"
exit $fail
