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
# AND WHEREVER THE USER MOVES IT (2026-09-30). Moved to ~/Applications and
# renamed, the app was left stale by the update, doubled by a new one on the
# Desktop, and orphaned by the uninstall. Section 6 moves it, updates, uninstalls,
# with a decoy beside it: our bundle id, another trunk — it must not be touched.
# And since those updates already left a Desktop duplicate beside the moved app,
# the second update carries both: a copy left unbuilt keeps the old binary.
#
# Usage: tests/desktop_launcher.sh [--sabotage no-guard|desktop-only]
#   no-guard      removes the install-side check; the foreign app must then be lost.
#   desktop-only  both scripts look at the Desktop alone again; section 6 must fail.
set -uo pipefail
SABOTAGE=""
[ "${1:-}" = "--sabotage" ] && SABOTAGE="${2:-}"
case "$SABOTAGE" in ""|no-guard|desktop-only) ;; *) echo "❌ unknown sabotage: $SABOTAGE (known: no-guard, desktop-only)"; exit 2 ;; esac

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
if [ "$SABOTAGE" = "desktop-only" ]; then
  python3 - "$H/src/greymatter/engine-lib.sh" "$H/src/uninstall.sh" <<'PY' || exit 2
import sys
for p in sys.argv[1:]:
    s = open(p).read(); old = "map_apps() {"
    if old not in s: sys.exit("SABOTAGE DID NOT APPLY — no map_apps in " + p)
    open(p, "w").write(s.replace(old, "map_apps() { return 0; }\n_unused() {", 1))
PY
  echo "   SABOTAGE: desktop-only"
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
( cd "$H/src" && ./install.sh --no-capsule ) >"$H/install1.log" 2>&1; check $? "install exits 0" "$(tail -3 "$H/install1.log")"
[ "$(sum_app)" = "$BEFORE" ]; check $? "the foreign app is byte-identical"
grep -q "is not this launcher" "$H/install1.log"; check $? "the installer says why it made no launcher"
! grep -q "GreyMatter.app opens the map" "$H/install1.log"; check $? "…and does not announce a launcher it did not make"

echo "▸ 2. uninstall with the foreign app still there"
( cd "$H/src" && ./uninstall.sh --yes ) >"$H/uninstall1.log" 2>&1 </dev/null; check $? "uninstall exits 0" "$(tail -3 "$H/uninstall1.log")"
[ "$(sum_app)" = "$BEFORE" ]; check $? "the uninstaller left the foreign app alone"

echo "▸ 3. install on a free Desktop"
rm -rf "$APP"
( cd "$H/src" && ./install.sh --no-capsule ) >"$H/install2.log" 2>&1; check $? "install exits 0" "$(tail -3 "$H/install2.log")"
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
( cd "$H/src" && ./install.sh --no-capsule ) >"$H/install3.log" 2>&1; check $? "re-install exits 0"
grep -q "org.greymatter.planet" "$APP/Contents/Info.plist" 2>/dev/null; check $? "still ours, still one"

echo "▸ 5. uninstall removes ours"
( cd "$H/src" && ./uninstall.sh --yes ) >"$H/uninstall2.log" 2>&1 </dev/null; check $? "uninstall exits 0"
[ ! -e "$APP" ]; check $? "GreyMatter.app is gone"

echo "▸ 6. moved and renamed by the user, then an update, then an uninstall"
( cd "$H/src" && ./install.sh --no-capsule ) >"$H/install4.log" 2>&1; check $? "install exits 0"
MOVED="$H/Applications/My map.app"; DECOY="$H/Applications/Other trunk.app"
mkdir -p "$H/Applications" && mv "$APP" "$MOVED"
touch "$MOVED/Contents/Resources/stale"      # a rebuild starts from nothing: this goes
mkdir -p "$DECOY/Contents/MacOS"             # ours by its id, but another trunk's
printf '<plist><dict><key>CFBundleIdentifier</key><string>org.greymatter.planet</string><key>GMTRLaunch</key><string>/elsewhere/trunk/gmtr/launch.sh</string></dict></plist>\n' \
  > "$DECOY/Contents/Info.plist"
DECOY_SUM="$(find "$DECOY" -type f -exec shasum {} + | sort | shasum)"
( cd "$H/src" && ./install.sh ) >"$H/install5.log" 2>&1; check $? "update exits 0" "$(tail -3 "$H/install5.log")"
[ ! -e "$APP" ]; check $? "no second app on the Desktop"
[ ! -e "$MOVED/Contents/Resources/stale" ] && grep -q "org.greymatter.planet" "$MOVED/Contents/Info.plist" 2>/dev/null
check $? "the moved app is rebuilt where the user put it"
grep -q "My map.app opens the map" "$H/install5.log"; check $? "the install screen names it where it is"
[ "$(find "$DECOY" -type f -exec shasum {} + | sort | shasum)" = "$DECOY_SUM" ]; check $? "another trunk's app is left byte-identical"
# The duplicate the old updates made on the Desktop, beside the moved one.
ditto "$MOVED" "$APP" && touch "$MOVED/Contents/Resources/stale" "$APP/Contents/Resources/stale"
( cd "$H/src" && ./install.sh ) >"$H/install6.log" 2>&1; check $? "update with two copies exits 0" "$(tail -3 "$H/install6.log")"
[ ! -e "$MOVED/Contents/Resources/stale" ] && [ ! -e "$APP/Contents/Resources/stale" ] \
  && grep -q "org.greymatter.planet" "$MOVED/Contents/Info.plist" 2>/dev/null \
  && grep -q "org.greymatter.planet" "$APP/Contents/Info.plist" 2>/dev/null
check $? "both copies are rebuilt, none left with the old app"
grep -q "My map.app opens the map" "$H/install6.log" && grep -q "Desktop: GreyMatter.app opens the map" "$H/install6.log"
check $? "the install screen names both"
( cd "$H/src" && ./uninstall.sh --yes ) >"$H/uninstall3.log" 2>&1 </dev/null; check $? "uninstall exits 0"
[ ! -e "$MOVED" ] && [ ! -e "$APP" ]; check $? "the moved app and its duplicate are gone"
[ "$(find "$DECOY" -type f -exec shasum {} + 2>/dev/null | sort | shasum)" = "$DECOY_SUM" ]; check $? "…and the other trunk's is still there"

echo
if [ "$FAILS" = 0 ]; then echo "✅ the map app is ours to rebuild wherever it is, and nothing else"; exit 0; fi
echo "❌ $FAILS check(s) failed"; exit 1
