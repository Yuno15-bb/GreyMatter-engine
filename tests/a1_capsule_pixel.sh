#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# a1_capsule_pixel.sh — A1: does the capsule of an INSTALLED engine actually put
# an orb on the screen, and does the renderer agree about what it shows?
#
# ─── WHY THIS FILE IS SHAPED LIKE THIS ───────────────────────────────────────
#
# The obvious version of this test — launch the capsule, take a screenshot, look
# for an orb — cannot work, and the capsule's own source says so (`main.js`:
# "on macOS the window server keeps ghost layers of these transparent
# always-on-top windows, so a killed instance can still be on screen").
#
# A positive screenshot is therefore uninterpretable on its own. So the order is
# inverted: BEFORE proving anything about the capsule, this proves things about
# the INSTRUMENT.
#
# ⚠ A BLACK IMAGE MUST NEVER PASS THE NEGATIVE CONTROL. Without Screen Recording
# permission `screencapture` succeeds, exits 0, and returns a desktop-only or
# black frame. That is a perfect false negative: the control we rely on to detect
# contamination would be satisfied precisely when the sensor is blind.
#
# ⚠ AND "NO FILE" IS NEVER "NOTHING THERE". On 2026-08-17 the rectangle was
# computed from `system_profiler` (panel pixels) and handed to `screencapture -R`
# (points). It captured nothing at all — and the first shape of this harness
# would have read that as an empty corner. `a1_pixel_lib.capture()` has no code
# path that returns emptiness for a missing file; every caller must handle
# UNREADABLE.
#
# ⚠ AND THE ENGINE MUST BE THE INSTALLED ONE. The capsule usually running on the
# author's machine comes from ~/claude-brain — the author's own layout, which no
# user has. Certifying that one would repeat the blind spot that let chantier #9
# survive six weeks: the author's machine never walks the installer's path.
#
# ─── WHAT --self-check GUARANTEES, AND WHAT IT CANNOT ─────────────────────────
#
# The previous version of this file announced seven steps in its own usage text
# and implemented two. `--self-check` was green throughout, because it only ever
# tested the checks that existed. So the rule here is structural: EVERY step
# `--run` declares must have at least one sabotage that turns it red for a named
# reason. A stub cannot satisfy that — a stub never goes red. The declaration
# table below is the single source of both the run order and the coverage audit.
#
# What it still cannot see: whether a sabotage is aimed at the same failure the
# real world would produce. That judgement stays human.
#
# Usage:
#   tests/a1_capsule_pixel.sh --prepare      everything that needs no screen
#   tests/a1_capsule_pixel.sh --sensor       step 0 alone: is the instrument sound?
#   tests/a1_capsule_pixel.sh --run          the full A1, after a fresh login
#   tests/a1_capsule_pixel.sh --self-check   prove each step can FAIL
set -uo pipefail

MODE="${1:---prepare}"
REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
LIB="$REPO/tests/a1_pixel_lib.py"
WORK="${A1_WORK:-$HOME/.c-brain-a1}"
export A1_WORK="$WORK"
fails=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1${2:+  — $2}"; fails=$((fails + 1)); }
info() { echo "     $1"; }
halt() { echo; echo "⛔ $1"; echo "   A1 is NOT PROVEN. No workaround."; exit 2; }
lib()  { python3 "$LIB" "$@"; }

# ═══════════════════════════════════════════════════════════════════════════
# THE DECLARATION — run order and coverage audit read the SAME table
# ═══════════════════════════════════════════════════════════════════════════
STEPS=(
  "0|check_sensor|the sensor itself"
  "1|check_discrimination|calibration: can it tell a window from no window?"
  "2|check_negative|the negative control, before anything is launched"
  "3|check_engine_identity|which capsule is about to be launched"
  "4|check_launch|launching THAT capsule"
  "5|check_drive|driving busy, then idle, and collecting both observables"
  "6|check_dom|what the RENDERER says it is showing"
  "7|check_pixels|what the SCREEN actually shows"
  "8|check_cross|the crossed verdict"
)
# Steps whose sabotage lives in this file rather than in the library.
SHELL_SABOTAGED=""

# State carried between steps.
ENGINE_ROOT=""; ENGINE_CAPSULE=""; ORB_RECT=""; POINTS_W=""; POINTS_H=""
SIZE=""; EDGE=""; PROBE_BUSY=""; PROBE_IDLE=""; DOM_OK="no"; PIXEL_OK="no"
CAPSULE_PID=""; STATUS_FILE=""; STATUS_BACKUP=""; UDD=""

cleanup() {
  [ -n "$CAPSULE_PID" ] && kill "$CAPSULE_PID" 2>/dev/null
  # The user's own state file is put back exactly as it was found. A test that
  # leaves the trunk driving a state nobody set is a test that broke the thing
  # it measured.
  if [ -n "$STATUS_FILE" ]; then
    if [ -n "$STATUS_BACKUP" ] && [ -f "$STATUS_BACKUP" ]; then
      mv -f "$STATUS_BACKUP" "$STATUS_FILE"
    else
      rm -f "$STATUS_FILE"
    fi
  fi
  [ -n "$UDD" ] && rm -rf "$UDD"
}
trap cleanup EXIT

# Constants are READ FROM THE SOURCE, never copied here: a copy in this test
# would keep passing after somebody moved the orb.
read_const() { grep -E "^const $2 *=" "$1" | grep -oE '[0-9]+' | head -1; }

# ═══════════════════════════════════════════════════════════════════════════
# STEP 0 — is the instrument even able to see?
# ═══════════════════════════════════════════════════════════════════════════
check_sensor() {
  command -v screencapture >/dev/null || halt "screencapture is not available."
  mkdir -p "$WORK"
  local shot="$WORK/00-sensor.png"
  lib capture - "$shot" >/dev/null || halt "screencapture produced no file. It cannot be used as a sensor."
  ok "screencapture produced a file"
  local verdict; verdict="$(lib sensor "$shot")"; local rc=$?
  echo "$verdict" | sed -n 's/^WHY=/     /p'
  [ "$rc" -eq 0 ] || halt "the capture holds almost no colour — Screen
   Recording is probably missing for this terminal: System Settings → Privacy &
   Security → Screen Recording. A blind sensor would make the negative control
   pass exactly when the screen is contaminated."
  ok "the capture carries real screen content (not black, not permission-denied)"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — can the sensor tell "a window is there" from "it is not"?
# ═══════════════════════════════════════════════════════════════════════════
# ⚠ Step 0 is NOT this. Step 0 proves the capture is not uniform — and a capture
# taken WITHOUT Screen Recording permission returns the desktop picture, which is
# not uniform either. A1 is entirely about a WINDOW, so the calibration has to be
# made of windows: one appearing, one leaving, and the same scene twice for a
# noise floor. Measured on 2026-08-17: 20.8% / 20.8% / 0.0%.
check_discrimination() {
  local region="${CAL_REGION:-}"
  if [ -z "$region" ]; then
    read_points || halt "the coordinate space could not be established."
    region="$(( (POINTS_W - 600) / 2 )),$(( (POINTS_H - 400) / 2 )),600,400"
  fi
  info "calibration region: $region (points)"

  local a="$WORK/10-before.png" b="$WORK/11-window.png" c="$WORK/12-after.png"
  lib capture "$region" "$a" >/dev/null || halt "the calibration region did not capture."

  osascript -e 'display dialog "A1 SENSOR CALIBRATION" buttons {"ok"} default button 1 giving up after 8' \
    >/dev/null 2>&1 &
  local dlg=$!
  sleep 2
  lib capture "$region" "$b" >/dev/null || halt "the calibration region did not capture with the window up."
  kill "$dlg" 2>/dev/null
  wait "$dlg" 2>/dev/null            # reap it quietly: the job notice is not a finding
  sleep 3
  lib capture "$region" "$c" >/dev/null || halt "the calibration region did not capture after the window left."

  local appear vanish drift
  appear="$(lib diff "$a" "$b" | sed 's/^DIFF=//')"
  vanish="$(lib diff "$b" "$c" | sed 's/^DIFF=//')"
  drift="$(lib diff "$a" "$c" | sed 's/^DIFF=//')"
  info "window appeared: ${appear}%   window left: ${vanish}%   same scene twice: ${drift}%"
  lib judge-discrimination "$appear" "$vanish" "$drift" \
    || halt "the sensor does not separate a window from no window. Every later
   'the rectangle is empty' would be worthless."
  ok "the sensor sees windows, and its noise floor is known"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — the negative control, on the REAL rectangle
# ═══════════════════════════════════════════════════════════════════════════
read_points() {
  [ -n "$POINTS_W" ] && [ -n "$POINTS_H" ] && return 0    # established once per run
  local out; out="$(lib screen-points)" || { echo "$out" | sed 's/^/     /'; return 1; }
  POINTS_W="$(echo "$out" | sed -n 's/^POINTS_W=//p')"
  POINTS_H="$(echo "$out" | sed -n 's/^POINTS_H=//p')"
  echo "$out" | sed -n 's/^FINDER=/     window server says  /p;s/^CAPTURE=/     capture math says   /p'
  [ -n "$POINTS_W" ] && [ -n "$POINTS_H" ]
}

check_negative() {
  read_points || halt "two independent instruments disagree about the size of the
   screen in points. The rectangle cannot be computed until they agree."
  ok "the coordinate space is ${POINTS_W}x${POINTS_H} points, agreed by two instruments"

  # SIZE/EDGE come from the repo's capsule here, because the engine is not
  # identified until step 3 and this control must precede the engine. Step 3
  # re-reads them from the INSTALLED engine and halts if they differ, so a
  # divergence can never quietly invalidate this rectangle.
  SIZE="$(read_const "$REPO/capsule/main.js" SIZE)"
  EDGE="$(read_const "$REPO/capsule/main.js" EDGE)"
  [ -n "$SIZE" ] && [ -n "$EDGE" ] || halt "SIZE/EDGE could not be read from capsule/main.js."

  local out; out="$(lib orb-rect "$SIZE" "$EDGE" "$POINTS_W" "$POINTS_H")"
  ORB_RECT="$(echo "$out" | sed -n 's/^RECT=//p')"
  echo "$out" | grep -q '^ON_SCREEN=yes' \
    || halt "the orb rectangle $ORB_RECT is not on a ${POINTS_W}x${POINTS_H} screen.
   This is the 2026-08-17 bug: a rectangle computed in the wrong coordinate space
   captures nothing, and nothing must never be read as an empty corner."
  ok "the orb rectangle is $ORB_RECT, inside the screen"

  local empty="$WORK/20-empty.png" status
  status="$(lib capture "$ORB_RECT" "$empty" | sed 's/^CAPTURE=//')"

  local facts alive procs start
  facts="$(lib machine-facts "$HOME/.c-brain/trunk/state/capsule-alive" \
                             "$HOME/claude-brain/state/capsule-alive")"
  procs="$(echo "$facts" | sed -n 's/^CAPSULE_PROCESSES=//p')"
  alive="$(echo "$facts" | sed -n 's/^ALIVE_MTIME=//p')"
  start="$(echo "$facts" | sed -n 's/^SESSION_START=//p')"
  info "capsule processes now: $procs   last capsule heartbeat: $alive   session opened: $start"

  lib judge-negative "$status" "$procs" "$alive" "$start" \
    || halt "the negative control is not trustworthy. On a session that has run a
   capsule, macOS ghost layers make any later positive uninterpretable — this is
   exactly the contamination A1 must be free of."
  ok "the orb rectangle is a trustworthy BEFORE picture"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — the engine identity, before anything is launched
# ═══════════════════════════════════════════════════════════════════════════
check_engine_identity() {
  local link real
  link="$HOME/.c-brain/engine"
  [ -e "$link" ] || halt "no engine at $link — install first."
  real="$(cd "$link" && pwd -P)"
  ENGINE_ROOT="$real"
  ENGINE_CAPSULE="$real/capsule"

  # The predicate itself lives in the library, where it is shown both a path it
  # must refuse and a path it must accept. Deciding it here would leave the
  # accepting half untested unless an engine were fabricated to test it with.
  local verdict; verdict="$(lib judge-engine-path "$real" "$HOME")"; local rc=$?
  echo "$verdict"
  [ "$rc" -eq 0 ] || halt "this is not an installed engine. Certifying the author's
   checkout would repeat the blind spot that hid chantier #9 for six weeks."

  # The rectangle of step 2 was computed from the repo's constants. If the
  # installed engine disagrees, the BEFORE picture was of the wrong corner.
  if [ -n "$SIZE" ]; then
    local esize eedge
    esize="$(read_const "$ENGINE_CAPSULE/main.js" SIZE)"
    eedge="$(read_const "$ENGINE_CAPSULE/main.js" EDGE)"
    { [ "$esize" = "$SIZE" ] && [ "$eedge" = "$EDGE" ]; } \
      || halt "the installed engine places the orb at SIZE=$esize EDGE=$eedge, but the
   negative control was taken on SIZE=$SIZE EDGE=$EDGE. The BEFORE picture is of a
   different rectangle than the one the orb will use."
    ok "the installed engine agrees on the orb geometry (SIZE=$SIZE EDGE=$EDGE)"
  fi

  local bin="$ENGINE_CAPSULE/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
  [ -x "$bin" ] || halt "no Electron binary under the installed engine: $bin"
  "$bin" --version >/dev/null 2>&1 || halt "the installed engine's Electron does not answer --version."
  ok "its Electron answers ($("$bin" --version 2>/dev/null))"
  info "capsule under test: $ENGINE_CAPSULE"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — launch THAT capsule, and prove it is the one reporting
# ═══════════════════════════════════════════════════════════════════════════
check_launch() {
  local bin="$ENGINE_CAPSULE/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
  UDD="$(mktemp -d "${TMPDIR:-/tmp}/a1-udd.XXXXXX")"
  PROBE_BUSY="$WORK/40-probe-busy.json"
  PROBE_IDLE="$WORK/70-probe-idle.json"
  rm -f "$PROBE_BUSY" "$PROBE_IDLE"

  # ⚠ --user-data-dir is not optional. The single-instance lock makes a second
  #   capsule quit INSTANTLY and SILENTLY: no message, no log, no exit code
  #   anyone sees. Without its own data dir this launch would die and the orb
  #   already on screen would be measured instead.
  CBRAIN_PROBE_OUT="$WORK/probe.json" \
    "$bin" "$ENGINE_CAPSULE" --user-data-dir="$UDD" >"$WORK/41-capsule.log" 2>&1 &
  CAPSULE_PID=$!
  info "launched pid $CAPSULE_PID with its own user-data-dir"

  local i
  for i in $(seq 1 30); do
    [ -s "$WORK/probe.json" ] && break
    sleep 1
  done
  lib judge-launch "$WORK/probe.json" "$ENGINE_CAPSULE" \
    || halt "the capsule under test did not report. See $WORK/41-capsule.log"
  ok "the capsule under test is running and reporting"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — drive busy then idle, collecting BOTH observables in each state
# ═══════════════════════════════════════════════════════════════════════════
check_drive() {
  STATUS_FILE="$HOME/.c-brain/trunk/state/status.json"
  mkdir -p "$(dirname "$STATUS_FILE")"
  if [ -f "$STATUS_FILE" ]; then
    STATUS_BACKUP="$WORK/50-status.backup.json"
    cp "$STATUS_FILE" "$STATUS_BACKUP"
  fi

  local liveness idle_hide_ms
  liveness="$(python3 -c "import json,sys;print(json.load(open('$ENGINE_ROOT/hooks/status_freshness.json'))['liveness_stale_seconds'])" 2>/dev/null || echo 30)"
  idle_hide_ms="$(read_const "$ENGINE_CAPSULE/main.js" IDLE_BEFORE_HIDE)"
  [ -n "$idle_hide_ms" ] || halt "IDLE_BEFORE_HIDE could not be read from the engine's main.js."

  # ── busy ──────────────────────────────────────────────────────────────────
  python3 - "$STATUS_FILE" <<'PY'
import json, sys, time
now = time.time()
json.dump({"state": "busy", "ts": now, "activity": "distilling",
           "activity_ts": now, "detail": "a1-capsule-pixel-proof"},
          open(sys.argv[1], "w"))
PY
  # The path on the left is the one main.js derives from os.homedir(); the one on
  # the right is what this harness just wrote. They must be the same file.
  lib judge-drive "$HOME/.c-brain/trunk/state/status.json" "$STATUS_FILE" "$STATUS_FILE" "$liveness" \
    || halt "the harness is not driving the file this capsule reads."
  ok "busy/distilling written to the file the capsule reads"

  sleep 4
  cp -f "$WORK/probe.json" "$PROBE_BUSY" 2>/dev/null
  lib capture "$ORB_RECT" "$WORK/51-busy-a.png" >/dev/null || halt "the busy capture failed."
  sleep 1
  lib capture "$ORB_RECT" "$WORK/52-busy-b.png" >/dev/null || halt "the second busy capture failed."
  ok "busy: renderer read and two captures taken"

  # ── idle ──────────────────────────────────────────────────────────────────
  # The label clears within a renderer tick, but the WINDOW only leaves after
  # IDLE_BEFORE_HIDE. Waiting less would compare an orb to itself.
  python3 -c "import json,sys,time;json.dump({'state':'idle','ts':time.time()},open(sys.argv[1],'w'))" "$STATUS_FILE"
  local wait_s=$(( idle_hide_ms / 1000 + 10 ))
  info "waiting ${wait_s}s for the window to hide (IDLE_BEFORE_HIDE=${idle_hide_ms}ms, read from the engine)"
  sleep "$wait_s"
  cp -f "$WORK/probe.json" "$PROBE_IDLE" 2>/dev/null
  lib capture "$ORB_RECT" "$WORK/71-idle-a.png" >/dev/null || halt "the idle capture failed."
  sleep 1
  lib capture "$ORB_RECT" "$WORK/72-idle-b.png" >/dev/null || halt "the second idle capture failed."
  ok "idle: renderer read and two captures taken"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 6 — what the RENDERER says
# ═══════════════════════════════════════════════════════════════════════════
check_dom() {
  if lib judge-dom "$PROBE_BUSY" "$PROBE_IDLE" "/.c-brain/versions/"; then
    DOM_OK="yes"; ok "the renderer reports the two states, and they differ"
  else
    DOM_OK="no";  ko "the renderer's report does not hold"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 7 — what the SCREEN shows
# ═══════════════════════════════════════════════════════════════════════════
check_pixels() {
  local appear vanish drift_busy drift_idle
  appear="$(lib diff "$WORK/20-empty.png" "$WORK/51-busy-a.png" | sed 's/^DIFF=//')"
  vanish="$(lib diff "$WORK/51-busy-a.png" "$WORK/71-idle-a.png" | sed 's/^DIFF=//')"
  drift_busy="$(lib diff "$WORK/51-busy-a.png" "$WORK/52-busy-b.png" | sed 's/^DIFF=//')"
  drift_idle="$(lib diff "$WORK/71-idle-a.png" "$WORK/72-idle-b.png" | sed 's/^DIFF=//')"
  info "orb appeared: ${appear}%   orb left: ${vanish}%"
  info "noise floor — busy twice: ${drift_busy}%   idle twice: ${drift_idle}%"
  if lib judge-pixels "$appear" "$vanish" "$drift_busy" "$drift_idle"; then
    PIXEL_OK="yes"; ok "the screen changed with the orb, clear of the noise"
  else
    PIXEL_OK="no";  ko "the screen does not carry the orb"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 8 — the crossed verdict
# ═══════════════════════════════════════════════════════════════════════════
check_cross() {
  if lib judge-cross "$DOM_OK" "$PIXEL_OK"; then
    echo; echo "✅ A1 PROVEN — the capsule of the installed engine draws an orb, and the"
    echo "   renderer agrees about what it shows. Artefacts: $WORK"
  else
    echo; echo "⛔ A1 NOT PROVEN. Artefacts: $WORK"
    fails=$((fails + 1))
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# --self-check — every declared step must be able to FAIL
# ═══════════════════════════════════════════════════════════════════════════
self_check() {
  echo "== a1 harness — can each declared step fail? =="
  echo
  echo "▸ the sabotages — every judgement fed a state it must REFUSE"
  local sab; sab="$(lib sabotages)"; local sab_rc=$?
  echo "$sab" | sed 's/^/  /'
  [ "$sab_rc" -eq 0 ] || fails=$((fails + 1))

  echo
  echo "▸ the positive controls — every judgement fed a state it must ACCEPT"
  # Without this half, a judgement that refuses everything would look rigorous
  # and would fail A1 for ever. A constant is not a measurement, in either
  # direction. See lessons/calibrer-l-instrument-avant-de-lui-demander-un-verdict.
  local pos; pos="$(lib positives)"; local pos_rc=$?
  echo "$pos" | sed 's/^/  /'
  [ "$pos_rc" -eq 0 ] || fails=$((fails + 1))

  echo
  echo "▸ the shell's own halt: a missing engine (step 3)"
  local t; t="$(mktemp -d)"
  ( HOME="$t/empty"; mkdir -p "$t/empty"; SIZE=""; check_engine_identity ) >"$t/out" 2>&1
  grep -q "no engine at" "$t/out" && ok "rejected a missing engine" \
    || ko "it accepted a missing engine"
  rm -rf "$t"

  # ── THE COVERAGE AUDIT ───────────────────────────────────────────────────
  # This is the check the old harness did not have, and the reason it stayed
  # green while announcing five steps it never ran.
  echo
  echo "▸ coverage: every step --run declares can go red AND green, and is not a stub"
  local id fn title cov sabotaged positived
  cov="$(lib covered-steps)"
  sabotaged=" $(echo "$cov" | sed -n 's/^SABOTAGED=//p') $SHELL_SABOTAGED "
  positived=" $(echo "$cov" | sed -n 's/^POSITIVE=//p') "
  for entry in "${STEPS[@]}"; do
    IFS='|' read -r id fn title <<<"$entry"

    if ! declare -F "$fn" >/dev/null; then
      ko "step $id ($fn) is declared by --run but the function does not exist"
      continue
    fi

    # A stub in the sense that bit us: a body made only of messages. Strip the
    # signature, braces, comments and every echo/info/ok line — if nothing is
    # left, the step measures nothing. This is syntactic and it knows it; the
    # sabotage requirement below is the load-bearing half.
    local body
    body="$(declare -f "$fn" | sed '1,2d;$d' \
            | sed -E '/^[[:space:]]*(#|echo|info|ok|:)/d;/^[[:space:]]*}?[[:space:]]*$/d')"
    if [ -z "$body" ]; then
      ko "step $id ($fn) has a body made only of messages — it is a stub"
      continue
    fi

    case "$sabotaged" in
      *" $id "*) ;;
      *) ko "step $id ($title) is announced by --run but NO sabotage proves it can fail" \
            "add one, or --run is claiming coverage it does not have"; continue ;;
    esac
    case "$positived" in
      *" $id "*) ;;
      *) ko "step $id ($title) has no positive control" \
            "a judgement that only ever refuses is a constant, not a measurement"; continue ;;
    esac
    ok "step $id — $title"
  done

  echo
  [ "$fails" -eq 0 ] && { echo "✅ every declared step measures something and can fail"; return 0; }
  echo "❌ $fails harness check(s) failed"; return 1
}

HOME_REAL="$HOME"
case "$MODE" in
  --sensor)     check_sensor ;;
  --self-check) self_check ;;
  --prepare)
    echo "== A1 harness — preparation only, nothing graphical is concluded =="
    echo
    check_engine_identity 2>&1 | sed 's/^/  /' || true
    echo
    echo "  Prepared. The graphical proof is deliberately NOT run here: it needs a"
    echo "  login session in which no capsule has ever run, because macOS ghost"
    echo "  layers make any positive capture uninterpretable otherwise."
    echo
    echo "  After a fresh macOS login:  tests/a1_capsule_pixel.sh --run"
    ;;
  --run)
    mkdir -p "$WORK"
    for entry in "${STEPS[@]}"; do
      IFS='|' read -r id fn title <<<"$entry"
      echo "▸ $id. $title"
      "$fn"
      echo
    done
    ;;
  *) echo "Usage: $0 [--prepare|--sensor|--run|--self-check]"; exit 2 ;;
esac

exit $(( fails > 0 ))
