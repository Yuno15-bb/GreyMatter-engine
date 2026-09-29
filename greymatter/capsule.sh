#!/usr/bin/env bash
# capsule.sh — open, close and locate the menu bar pill.  `brain capsule [stop|status]`
#
# WHY THIS VERB EXISTS (decided 2026-09-20, C bis entry B3).
# The installer builds and starts the capsule once. After a reboot, a `stop`, or
# a crash, the reader needs one gesture to get it back — not a path inside a
# directory whose leading dot makes Finder hide it.
#
# WHY A CLI VERB AND NOT A SECOND DESKTOP APP. The capsule shows what the AGENTS
# are doing during a session — its reader is already in a terminal running
# `brain doctor`. The pill lives in the menu bar; a Desktop icon would add a
# second surface for the same thing.
#
# WHY THROUGH THE TRUNK PATH. hooks/auto_maintain.py recognises the pill with
# `pgrep -f <trunk>/capsule/macos/.build/release/Capsule`. Started from the
# version directory, the same binary would be invisible to it, and the hook
# would start a second pill next to this one.
set -euo pipefail

TRUNK="$(cd "${BRAIN_HOME:-$HOME/.greymatter/trunk}" 2>/dev/null && pwd -P)" || {
  echo "capsule: no trunk at ~/.greymatter/trunk — run ./install.sh"; exit 1; }
BIN="$TRUNK/capsule/macos/.build/release/Capsule"
# The pre-2.2 Electron capsule, still running after an update, would sit next
# to the native pill: `start` retires it, `status` names it. Its command line
# holds the resolved path, never the trunk's: engine-lib.sh says why.
. "$(cd "$(dirname "$0")" && pwd -P)/engine-lib.sh"
ORBS="$(orb_patterns "$TRUNK" "$HOME/.greymatter/runtime")"
orb_running() {
  local p
  while IFS= read -r p; do
    [ -n "$p" ] && pgrep -f "$p" >/dev/null 2>&1 && return 0
  done <<<"$ORBS"
  return 1
}
orb_stop() {
  local p
  while IFS= read -r p; do
    [ -n "$p" ] && { pkill -f "$p" 2>/dev/null || true; }
  done <<<"$ORBS"
  return 0
}

alive() { kill -0 "$1" 2>/dev/null; }
running_pid() { pgrep -f "$BIN" 2>/dev/null | head -1; }

case "${1:-start}" in
  status)
    if pid="$(running_pid)" && [ -n "$pid" ]; then
      echo "capsule: running   pid $pid"
      # The heartbeat, not the pid, says the window is drawing: the pill writes
      # state/capsule-alive every 5 s while its panel is on screen.
      hb="$TRUNK/state/capsule-alive"
      if [ -f "$hb" ]; then
        age=$(( $(date +%s) - $(stat -f %m "$hb") ))
        [ "$age" -le 15 ] && echo "  heartbeat ${age}s ago — drawing" \
                          || echo "  heartbeat ${age}s ago — stale: \`brain capsule stop\` then \`brain capsule\`"
      fi
    else
      echo "capsule: not running"
      [ -x "$BIN" ] && echo "  the pill is built — \`brain capsule\` opens it" \
                    || echo "  the pill is not built — \`brain capsule\` says how to add it"
    fi
    orb_running && echo "  an old Electron capsule is still running — \`brain capsule\` retires it"
    [ -e "$TRUNK/state/no-capsule" ] && echo "  light mode is on (state/no-capsule): the hooks never start it"
    true
    ;;

  stop)
    if pid="$(running_pid)" && [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
      # ⚠ THE SECOND CONTROL. `kill` returning 0 says the signal was delivered,
      # not that the process left. The pid is the sensor.
      for _ in 1 2 3 4 5 6 7 8 9 10; do alive "$pid" || break; sleep 0.2; done
      if alive "$pid"; then
        echo "capsule: pid $pid did not leave on SIGTERM.   To insist:  kill -9 $pid"
        exit 1
      fi
      echo "capsule: stopped (pid $pid)"
      echo "  the hooks start it again at the next session — \`touch $TRUNK/state/no-capsule\` keeps it off"
    else
      echo "capsule: not running — nothing to stop"
    fi
    ;;

  start|"")
    if [ ! -x "$BIN" ]; then
      echo "capsule: the pill is not built ($BIN)"
      # A re-run keeps the choices of the last install: when the pill was one of
      # the pieces declined, "re-run ./install.sh" alone would skip it again.
      if grep -qx 'capsule=0' "$HOME/.greymatter/state/install-choices" 2>/dev/null; then
        echo "The install choices mark it as declined (~/.greymatter/state/install-choices): chosen"
        echo "at install, or read on the update to v2.2.0 when no orb was there. A re-run keeps that."
        echo "To add it: re-run ./install.sh with only the options you still want (--no-launchd,"
        echo "--no-planet, --no-shortcut) — or, for every piece, delete that file first."
      else
        echo "Re-run ./install.sh — it builds it with Swift (xcode-select --install first if Swift is missing)."
      fi
      exit 1
    fi
    orb_stop
    if pid="$(running_pid)" && [ -n "$pid" ]; then
      echo "capsule: already running (pid $pid) — look for \"GreyMatter\" in the menu bar"
      exit 0
    fi
    # Detached, or the terminal is held for as long as the pill is on screen.
    CAPSULE_BRAIN="$TRUNK" nohup "$BIN" </dev/null >/dev/null 2>&1 &
    disown 2>/dev/null || true
    echo "capsule: opening — look for \"GreyMatter idle\" in the menu bar; click it for the panel"
    ;;

  *)
    echo "Usage: brain capsule [start|stop|status]"
    exit 1
    ;;
esac
