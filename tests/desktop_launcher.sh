#!/usr/bin/env bash
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# desktop_launcher.sh — THE DESKTOP APP IS OURS TO REBUILD, AND ONLY OURS.
#
# WHY IT EXISTS. The launcher was renamed "GreyMatter.app" on 2026-09-27 (it was
# "GreyMatter Planet.app" for one unreleased day, "C Brain Planet.app" before).   # pre-rename
# The installer rebuilds it with `rm -rf` and the uninstaller removes it. Under a
# name that plain, another app can sit there — a download, a future release
# built elsewhere — and an `rm -rf` on the name alone would delete it without a
# word. So both scripts first read the bundle id (org.greymatter.planet).
#
# WHAT IS MEASURED: the Desktop on disk after install and uninstall, plus the
# warning printed. A foreign app must come out byte-identical; ours must appear,
# then go.
#
# Usage: tests/desktop_launcher.sh [--sabotage no-guard]
#   no-guard  removes the install-side check; the foreign app must then be lost.
set -uo pipefail
SABOTAGE=""
[ "${1:-}" = "--sabotage" ] && SABOTAGE="${2:-}"
case "$SABOTAGE" in ""|no-guard) ;; *) echo "❌ unknown sabotage: $SABOTAGE (known: no-guard)"; exit 2 ;; esac

[ "$(uname)" = "Darwin" ] || { echo "⤳ skipped: install.sh targets macOS"; exit 0; }
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
[ "$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" = "$ROOT" ] \
  || { echo "⤳ skipped: $ROOT is not a Git checkout (a managed install ships none)"; exit 0; }

H="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$H"' EXIT
export HOME="$H"
export GREYMATTER_NO_AUTO_UPDATE=1

# The fake launchd: `launchctl` indexes jobs by label, not by $HOME, so the real
# one would register this test's jobs on the machine running it.
mkdir -p "$H/bin" "$H/.claude" "$H/Desktop" "$H/src"
python3 -c "import sys; sys.path.insert(0, '$ROOT/tests'); import _fake_launchd as f; print(f.FAKE, end='')" \
  > "$H/bin/launchctl"
chmod +x "$H/bin/launchctl"
export FAKE_REG="$H/launchd-registry" FAKE_LOG="$H/launchd.log"
: > "$FAKE_REG"
export PATH="$H/.local/bin:$H/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# The source is the WORKING TREE, uncommitted changes included.
( cd "$ROOT" && git ls-files -z | xargs -0 tar -c ) | tar -x -C "$H/src"
if [ "$SABOTAGE" = "no-guard" ]; then
  python3 - "$H/src/install.sh" <<'PY' || exit 2
import sys
p = sys.argv[1]; s = open(p).read()
old = 'elif [ -d "$APP" ] && ! grep -q "org.greymatter.planet"'
if old not in s: sys.exit("SABOTAGE DID NOT APPLY — the pattern matched nothing")
open(p, "w").write(s.replace(old, 'elif false && [ -d "$APP" ]', 1))
PY
  echo "   SABOTAGE: no-guard"
fi
# install.sh builds its engine from a Git checkout, so the copy becomes one.
git -C "$H/src" init -q && git -C "$H/src" add -A \
  && git -C "$H/src" -c user.email=t -c user.name=t commit -q -m "working tree" \
  || { echo "❌ could not commit the source copy"; exit 1; }

FAILS=0
check() { if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi; }
APP="$H/Desktop/GreyMatter.app"

foreign() {  # somebody else's app under our name
  mkdir -p "$APP/Contents/MacOS"
  printf '<plist><dict><key>CFBundleIdentifier</key><string>com.example.other</string></dict></plist>\n' \
    > "$APP/Contents/Info.plist"
  echo "not yours" > "$APP/Contents/MacOS/other"
}
sum_app() { find "$APP" -type f -exec shasum {} + 2>/dev/null | sort | shasum | cut -d' ' -f1; }

echo "▸ 1. install with a foreign GreyMatter.app on the Desktop"
foreign; BEFORE="$(sum_app)"
( cd "$H/src" && ./install.sh ) >"$H/install1.log" 2>&1; check $? "install exits 0" "$(tail -3 "$H/install1.log")"
[ "$(sum_app)" = "$BEFORE" ]; check $? "the foreign app is byte-identical"
grep -q "is not this launcher" "$H/install1.log"; check $? "the installer says why it made no launcher"
! grep -q "GreyMatter.app opens the map" "$H/install1.log"; check $? "…and does not announce a launcher it did not make"

echo "▸ 2. uninstall with the foreign app still there"
( cd "$H/src" && ./uninstall.sh --yes ) >"$H/uninstall1.log" 2>&1 </dev/null; check $? "uninstall exits 0" "$(tail -3 "$H/uninstall1.log")"
[ "$(sum_app)" = "$BEFORE" ]; check $? "the uninstaller left the foreign app alone"

echo "▸ 3. install on a free Desktop"
rm -rf "$APP"
( cd "$H/src" && ./install.sh ) >"$H/install2.log" 2>&1; check $? "install exits 0" "$(tail -3 "$H/install2.log")"
grep -q "org.greymatter.planet" "$APP/Contents/Info.plist" 2>/dev/null; check $? "GreyMatter.app is ours"
[ -x "$APP/Contents/MacOS/planet" ]; check $? "…and it launches the planet"
# v2.2: with the Apple developer tools present, the launcher is the native map
# app (a Mach-O binary), not the shell script that opens the browser.
if command -v swift >/dev/null 2>&1; then
  file "$APP/Contents/MacOS/planet" | grep -q "Mach-O"; check $? "…as the native app, not the browser fallback"
  L=$(/usr/libexec/PlistBuddy -c "Print :GMTRLaunch" "$APP/Contents/Info.plist" 2>/dev/null)
  [ -x "$L" ]; check $? "…pointed at a map launcher that exists"
fi
grep -q "GreyMatter.app opens the map" "$H/install2.log"; check $? "the install screen names the Desktop app it made"
[ ! -e "$H/Desktop/GreyMatter Planet.app" ]; check $? "no second launcher under the longer name"

echo "▸ 4. a second install rebuilds ours in place"
( cd "$H/src" && ./install.sh ) >"$H/install3.log" 2>&1; check $? "re-install exits 0"
grep -q "org.greymatter.planet" "$APP/Contents/Info.plist" 2>/dev/null; check $? "still ours, still one"

echo "▸ 5. uninstall removes ours"
( cd "$H/src" && ./uninstall.sh --yes ) >"$H/uninstall2.log" 2>&1 </dev/null; check $? "uninstall exits 0"
[ ! -e "$APP" ]; check $? "GreyMatter.app is gone"

echo
if [ "$FAILS" = 0 ]; then echo "✅ the Desktop launcher touches its own app, and nothing else"; exit 0; fi
echo "❌ $FAILS check(s) failed"; exit 1
