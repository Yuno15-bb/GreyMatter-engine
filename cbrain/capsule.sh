#!/usr/bin/env bash
# capsule.sh — open, close and locate the floating orb.  `brain capsule [stop|status]`
#
# WHY THIS VERB EXISTS (decided 2026-09-20, C bis entry B3).
# The installer installs the capsule, then PROVES the Electron binary answers
# `--version`, and stops there. It never says how to get a window on screen.
# The only documented gesture was `cd ~/.c-brain/trunk/capsule && npm start`
# in capsule/README.md: a terminal gesture, inside a directory whose leading dot
# makes Finder hide it, in a README nothing else points to.
#
# WHY A CLI VERB AND NOT A SECOND DESKTOP APP. The planet gets a Desktop bundle
# because its reader is anyone with a browser. The capsule animates what the
# AGENTS are doing during a session — its reader is already in a terminal
# running `brain doctor`. A second bundle would add an icon, a PATH shim and a
# second Desktop item; install.sh's own note says "the capsule's future is not
# more Electron plumbing". This verb adds no Electron surface at all.
#
# WHY IT DOES NOT CALL npm. `npm start` runs `electron .`, and npm is declared
# OPTIONAL in INSTALL.md. The binary is what actually has to answer, so this
# starts the binary — resolved exactly the way install.sh's capsule_ok resolves
# it, through the `path.txt` electron writes only on a successful extraction.
set -euo pipefail

SELF="${SELF:-$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CAPSULE="$SELF/capsule"
ED="$CAPSULE/node_modules/electron"

# `path.txt` is electron's own answer to "where did I put the binary". It is
# written ONLY when the extraction succeeded, so its absence is itself the
# symptom install.sh repairs. The fallback keeps a pre-path.txt install working.
rel="$(cat "$ED/dist/path.txt" 2>/dev/null || true)"
[ -n "$rel" ] || rel="Electron.app/Contents/MacOS/Electron"
BIN="$ED/dist/$rel"

# The marker the capsule writes on startup: { pid, since, dir }. Its directory
# is Electron's userData, named after the capsule's package name — read from
# package.json rather than spelled here, because the author's trunk and the
# shipped package do not carry the same name.
name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' \
        "$CAPSULE/package.json" 2>/dev/null || echo c-brain-capsule)"
MARK="$HOME/Library/Application Support/$name/instance.json"

alive() { kill -0 "$1" 2>/dev/null; }

# WHO IS RUNNING, and from where. Two sources, in this order, because they fail
# differently. The marker is precise (pid, start time, directory) but it only
# exists for capsules started after 2026-09-19 and only for THIS package name.
# `pgrep` sees every capsule on the machine — which is the right scope, since
# the lock is machine-wide: one capsule at a time, whichever trunk it came from.
running_pid() {
  local pid dir
  pid="$(python3 - "$MARK" <<'PY' 2>/dev/null || true
import json,sys
try: print(json.load(open(sys.argv[1]))["pid"])
except Exception: pass
PY
)"
  if [ -n "$pid" ] && alive "$pid"; then echo "$pid marker"; return 0; fi
  # The main process, never a helper: helpers carry `--type=` on their command line.
  for pid in $(pgrep -f "capsule/node_modules/electron/dist" 2>/dev/null || true); do
    dir="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    case "$dir" in *--type=*) continue ;; esac
    echo "$pid pgrep"; return 0
  done
  return 1
}

case "${1:-start}" in
  status)
    if found="$(running_pid)"; then
      pid="${found% *}"; src="${found#* }"
      echo "capsule: running   pid $pid   (seen by $src)"
      ps -o command= -p "$pid" 2>/dev/null | sed 's|^|  |' | cut -c1-110
    else
      echo "capsule: not running"
      [ -x "$BIN" ] && echo "  the binary is installed — \`brain capsule\` opens it" \
                    || echo "  the Electron binary is missing — re-run ./install.sh"
    fi
    ;;

  stop)
    if found="$(running_pid)"; then
      pid="${found% *}"
      kill "$pid" 2>/dev/null || true
      # ⚠ THE SECOND CONTROL. `kill` returning 0 says the signal was delivered,
      # not that the process left. macOS also keeps ghost layers of these
      # transparent always-on-top windows, so "the orb is gone from the screen"
      # is not a sensor either. The pid is.
      for _ in 1 2 3 4 5 6 7 8 9 10; do alive "$pid" || break; sleep 0.2; done
      if alive "$pid"; then
        echo "capsule: pid $pid did not leave on SIGTERM.   To insist:  kill -9 $pid"
        exit 1
      fi
      echo "capsule: stopped (pid $pid)"
    else
      echo "capsule: not running — nothing to stop"
    fi
    ;;

  start|"")
    if [ ! -x "$BIN" ]; then
      echo "The Electron binary is not there: $BIN"
      # The remedy that WORKS. `npm install` is the step that already failed —
      # install.sh unpacks the archive npm downloaded, which npm's own
      # extraction leaves truncated. Sending the reader back round that loop is
      # worse than saying nothing.
      echo "Re-run ./install.sh — it unpacks what npm downloaded. Everything else works without it."
      exit 1
    fi
    # Detached, or the terminal is held for as long as the orb is on screen.
    # stdout is dropped; stderr is KEPT, because a second launch explains
    # itself there — who holds the lock, since when, from which directory.
    ( cd "$CAPSULE" && exec "$BIN" . >/dev/null ) &
    disown 2>/dev/null || true
    echo "capsule: opening…   (⌘⇧B shows / hides it · drag it · hover → ×)"
    echo "         a second launch does not start a second orb: it brings this one back."
    ;;

  *)
    echo "Usage: brain capsule [start|stop|status]"
    exit 1
    ;;
esac
