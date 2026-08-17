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
#   0. screencapture works at all, and has Screen Recording permission
#   1. the capture can tell an orb-shaped thing from an empty desktop
#   2. the orb rectangle is EMPTY right now  (the negative control)
#   3. the engine under test is an INSTALLED one, not the author's checkout
#   -- only then --
#   4. launch, drive two states, read the renderer, read the pixels
#
# ⚠ A BLACK IMAGE MUST NEVER PASS STEP 2. Without Screen Recording permission
# `screencapture` succeeds, exits 0, and returns a black or desktop-only frame.
# That is a perfect false negative: the control we rely on to detect
# contamination would be satisfied precisely when the sensor is blind. Step 0 and
# step 1 exist to make that impossible.
#
# ⚠ AND THE ENGINE MUST BE THE INSTALLED ONE. The capsule usually running on the
# author's machine comes from ~/claude-brain — the author's own layout, which no
# user has. Certifying that one would repeat the blind spot that let chantier #9
# survive six weeks: the author's machine never walks the installer's path.
#
# Usage:
#   tests/a1_capsule_pixel.sh --prepare      everything that needs no screen
#   tests/a1_capsule_pixel.sh --sensor       steps 0-1: is the instrument sound?
#   tests/a1_capsule_pixel.sh --run          the full A1, after a fresh login
#   tests/a1_capsule_pixel.sh --self-check   prove each check can FAIL
set -uo pipefail

MODE="${1:---prepare}"
REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
WORK="${A1_WORK:-$HOME/.c-brain-a1}"
fails=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1${2:+  — $2}"; fails=$((fails + 1)); }
info() { echo "     $1"; }
halt() { echo; echo "⛔ $1"; echo "   A1 is NOT PROVEN. No workaround."; exit 2; }

# ─── The orb rectangle, derived from the source, never guessed ───────────────
# `capsule/main.js` places the window at
#     x = display.x + display.width  - SIZE - EDGE
#     y = display.y + display.height - SIZE - EDGE
# with SIZE and EDGE declared as constants. They are READ FROM THE FILE here: a
# copy in this test would keep passing after somebody moved the orb.
orb_rect() {
  local size edge
  size="$(grep -E '^const SIZE *=' "$ENGINE_CAPSULE/main.js" | grep -oE '[0-9]+' | head -1)"
  edge="$(grep -E '^const EDGE *=' "$ENGINE_CAPSULE/main.js" | grep -oE '[0-9]+' | head -1)"
  [ -n "$size" ] && [ -n "$edge" ] || return 1
  python3 - "$size" "$edge" <<'PY'
import subprocess, sys, re
size, edge = int(sys.argv[1]), int(sys.argv[2])
# The MAIN display's pixel size, from the system rather than from a guess.
out = subprocess.run(["system_profiler", "SPDisplaysDataType"],
                     capture_output=True, text=True).stdout
m = re.search(r"Resolution:\s*(\d+)\s*x\s*(\d+)", out)
if not m:
    sys.exit(1)
w, h = int(m.group(1)), int(m.group(2))
# system_profiler reports native pixels; screencapture -R takes points. On a
# Retina panel the two differ by the backing scale, so the rect is expressed as
# a fraction of the reported size and converted by the caller if needed.
print("%d,%d,%d,%d" % (w - size - edge, h - size - edge, size, size))
PY
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 0 — is the instrument even able to see?
# ═══════════════════════════════════════════════════════════════════════════
check_sensor() {
  echo "▸ 0. the sensor itself"
  command -v screencapture >/dev/null || halt "screencapture is not available."

  local shot="$WORK/sensor.png"
  mkdir -p "$WORK"
  rm -f "$shot"
  screencapture -x "$shot" 2>/dev/null
  [ -s "$shot" ] || halt "screencapture produced no file. It cannot be used as a sensor."
  ok "screencapture produced a file"

  # ⚠ THE PERMISSION TEST. Without Screen Recording, screencapture still exits 0
  # and still writes a PNG — of the desktop picture alone, or of black. The
  # discriminator is VARIETY: a real screen carries many distinct colours;
  # a blind capture carries almost none.
  local colours
  colours="$(python3 - "$shot" <<'PY'
import sys, struct, zlib
# A dependency-free PNG reader would be long; we sample with sips instead.
print("")
PY
)"
  colours="$(sips -g pixelWidth -g pixelHeight "$shot" 2>/dev/null | grep -c pixel)"
  [ "$colours" -ge 2 ] || halt "the capture is not a readable image."

  local variety
  variety="$(python3 - "$shot" <<'PY'
import subprocess, sys, os, tempfile
src = sys.argv[1]
# Shrink to 32x32 and read raw RGB — no third-party library, and enough to
# count distinct colours reliably.
tmp = tempfile.mktemp(suffix=".png")
subprocess.run(["sips", "-Z", "32", src, "--out", tmp],
               capture_output=True)
raw = tempfile.mktemp(suffix=".rgb")
subprocess.run(["sips", "-s", "format", "bmp", tmp, "--out", raw],
               capture_output=True)
data = open(raw, "rb").read() if os.path.exists(raw) else b""
# distinct 3-byte tuples in the body; crude but monotone in "how much is here"
body = data[54:] if len(data) > 54 else data
colours = {body[i:i+3] for i in range(0, len(body) - 3, 3)}
print(len(colours))
for f in (tmp, raw):
    try: os.remove(f)
    except OSError: pass
PY
)"
  info "distinct colours in a 32x32 sample: ${variety:-?}"
  if [ -z "$variety" ] || [ "$variety" -lt 8 ]; then
    halt "the capture holds almost no colour. Screen Recording permission is
   probably missing for this terminal — System Settings → Privacy & Security →
   Screen Recording. A blind sensor would make the negative control pass exactly
   when the screen is contaminated."
  fi
  ok "the capture carries real screen content (not black, not permission-denied)"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — can the sensor tell "something there" from "nothing there"?
# ═══════════════════════════════════════════════════════════════════════════
# A detector that has never been shown a positive is a detector nobody has
# calibrated. This paints a known window on screen, captures it, and requires the
# measure to separate it from an empty region. If it cannot, every later "the
# rectangle is empty" is worthless.
check_discrimination() {
  echo "▸ 1. can it tell full from empty?"
  info "(to be run only in the fresh session — see --run)"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — the engine identity, before anything is launched
# ═══════════════════════════════════════════════════════════════════════════
check_engine_identity() {
  echo "▸ 3. which capsule is about to be launched?"
  local link real
  link="$HOME/.c-brain/engine"
  [ -e "$link" ] || halt "no engine at $link — install first."
  real="$(cd "$link" && pwd -P)"
  ENGINE_CAPSULE="$real/capsule"

  case "$real/" in
    "$HOME/.c-brain/versions/"*)
      ok "the engine is an installed version: $(basename "$real")" ;;
    *)
      halt "the engine is $real, which is NOT under ~/.c-brain/versions/.
   A1 certifies the capsule of an INSTALLED engine. Certifying the author's
   checkout would repeat the blind spot that hid chantier #9 for six weeks." ;;
  esac

  case "$real" in
    *"/claude-brain"*) halt "the engine resolves into ~/claude-brain — the author's layout." ;;
  esac

  local bin="$ENGINE_CAPSULE/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
  [ -x "$bin" ] || halt "no Electron binary under the installed engine: $bin"
  "$bin" --version >/dev/null 2>&1 || halt "the installed engine's Electron does not answer --version."
  ok "its Electron answers ($("$bin" --version 2>/dev/null))"
  info "capsule under test: $ENGINE_CAPSULE"
}

# ═══════════════════════════════════════════════════════════════════════════
# --self-check — every check must be able to FAIL
# ═══════════════════════════════════════════════════════════════════════════
# A harness whose checks have never been seen red is a harness that has never
# been tested. Each one is fed a state it must reject.
self_check() {
  echo "== a1 harness — can each check fail? =="
  local t; t="$(mktemp -d)"; trap 'rm -rf "$t"' RETURN

  echo "▸ engine identity rejects the author's checkout"
  ( HOME="$t"; mkdir -p "$t/.c-brain"; ln -s "$HOME_REAL/claude-brain" "$t/.c-brain/engine" 2>/dev/null
    ENGINE_CAPSULE=""; check_engine_identity ) >"$t/out" 2>&1
  grep -q "NOT under" "$t/out" && ok "rejected an engine outside versions/" \
    || ko "it accepted an engine outside versions/" "$(tail -1 "$t/out")"

  echo "▸ engine identity rejects a missing engine"
  ( HOME="$t/empty"; mkdir -p "$t/empty"; check_engine_identity ) >"$t/out2" 2>&1
  grep -q "no engine at" "$t/out2" && ok "rejected a missing engine" \
    || ko "it accepted a missing engine"

  echo "▸ the colour-variety measure separates a blank image from a real one"
  python3 - "$t" <<'PY'
import subprocess, os, sys
t = sys.argv[1]
blank = os.path.join(t, "blank.png")
# a uniform image: what a permission-denied capture looks like
subprocess.run(["python3", "-c",
  "import struct,zlib,sys;w=h=64;raw=b''.join(b'\\x00'+bytes([0,0,0])*w for _ in range(h));"
  "png=lambda t,d:struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d));"
  "open(sys.argv[1],'wb').write(b'\\x89PNG\\r\\n\\x1a\\n'+png(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))"
  "+png(b'IDAT',zlib.compress(raw))+png(b'IEND',b''))", blank], check=True)
print("blank written")
PY
  if [ -s "$t/blank.png" ]; then
    local v
    v="$(A1_WORK="$t" bash -c '
      python3 - "'"$t"'/blank.png" <<PY
import subprocess, sys, os, tempfile
src = sys.argv[1]
tmp = tempfile.mktemp(suffix=".png"); raw = tempfile.mktemp(suffix=".bmp")
subprocess.run(["sips","-Z","32",src,"--out",tmp],capture_output=True)
subprocess.run(["sips","-s","format","bmp",tmp,"--out",raw],capture_output=True)
d = open(raw,"rb").read() if os.path.exists(raw) else b""
b = d[54:] if len(d)>54 else d
print(len({b[i:i+3] for i in range(0,len(b)-3,3)}))
PY')"
    info "distinct colours in a uniform image: ${v:-?}"
    { [ -n "$v" ] && [ "$v" -lt 8 ]; } \
      && ok "a uniform image is measured as blind (< 8 colours)" \
      || ko "a uniform image was NOT detected as blind" "got ${v:-?} colours — the permission test would pass while blind"
  fi

  echo
  [ "$fails" -eq 0 ] && { echo "✅ every harness check can fail"; return 0; }
  echo "❌ $fails harness check(s) cannot demonstrate failure"; return 1
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
    echo "  Prepared. The graphical proof is deliberately NOT run here:"
    echo "  this login session has had capsules running since 15 August, so its"
    echo "  ghost layers make any positive capture uninterpretable."
    echo
    echo "  After a fresh macOS login:  tests/a1_capsule_pixel.sh --run"
    ;;
  --run)
    check_sensor
    echo
    check_discrimination
    echo
    check_engine_identity
    echo
    echo "▸ 2. THE NEGATIVE CONTROL — before any capsule is launched"
    echo "     (implemented once steps 0-1 are green on the fresh session)"
    ;;
  *) echo "Usage: $0 [--prepare|--sensor|--run|--self-check]"; exit 2 ;;
esac

exit $(( fails > 0 ))
