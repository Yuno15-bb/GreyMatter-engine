#!/usr/bin/env python3
"""Reloads the app's browser tab after a burst of modifications.

Launched DETACHED by post_diff.py. The "changed reality" is watched where it lives
vraiment : dans un navigateur, pas dans un panneau maison.

Trois garde-fous :
  - DEBOUNCE: a burst of eight files = ONE reload, not eight.
  - LOCK: only one reloader waiting at a time (per session).
  - JAMAIS de vol de focus : `reload` sur l'onglet, sans `activate`.
"""

import json
import os
import socket
import subprocess
import sys
import time

BASE = os.path.expanduser("~/.claude/companion")
STATE = os.path.join(BASE, "reload.json")
LOCKDIR = os.path.join(BASE, "reload.lock")
PORTS = (3000, 5173, 4321, 8080, 8000, 4200)

QUIET = 1.2          # secondes de silence avant de recharger
POLL = 0.25
MAX_WAIT = 25        # une rafale interminable ne doit pas bloquer un recharcheur


def dev_port():
    for p in PORTS:
        s = socket.socket()
        s.settimeout(0.08)
        try:
            s.connect(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return None


def feed_mtime(sid):
    try:
        return os.path.getmtime(os.path.join(BASE, "sessions", sid + ".jsonl"))
    except OSError:
        return 0


# Chrome puis Safari : on recharge l'onglet existant ; on n'en ouvre un que si
# none of them shows the app (once only, recorded in reload.json).
AS_CHROME_RELOAD = """
tell application "System Events"
  if not (exists process "Google Chrome") then return "absent"
end tell
tell application "Google Chrome"
  set n to 0
  repeat with w in windows
    repeat with t in tabs of w
      if URL of t contains "{host}" then
        tell t to reload
        set n to n + 1
      end if
    end repeat
  end repeat
  return (n as text)
end tell
"""

AS_SAFARI_RELOAD = """
tell application "System Events"
  if not (exists process "Safari") then return "absent"
end tell
tell application "Safari"
  set n to 0
  repeat with w in windows
    repeat with t in tabs of w
      if URL of t contains "{host}" then
        set URL of t to (URL of t)
        set n to n + 1
      end if
    end repeat
  end repeat
  return (n as text)
end tell
"""


def osa(script):
    try:
        out = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=6)
        return out.stdout.strip()
    except Exception:
        return ""


def reload_tabs(port):
    host = "localhost:%d" % port
    total = 0
    for tpl in (AS_CHROME_RELOAD, AS_SAFARI_RELOAD):
        res = osa(tpl.format(host=host))
        if res.isdigit():
            total += int(res)
    if total == 0:
        # Fallback: the same app served on 127.0.0.1 instead of localhost
        for tpl in (AS_CHROME_RELOAD, AS_SAFARI_RELOAD):
            res = osa(tpl.format(host="127.0.0.1:%d" % port))
            if res.isdigit():
                total += int(res)
    return total


def open_once(port):
    """Ouvre l'onglet une seule fois par port : ensuite on ne fait que recharger."""
    st = read_state()
    if st.get("opened_port") == port:
        return False
    subprocess.run(["open", "-g", "http://localhost:%d" % port],   # -g = sans focus
                   capture_output=True, timeout=6)
    write_state(dict(st, opened_port=port))
    return True


def read_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def write_state(d):
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(STATE, "w") as f:
            json.dump(d, f)
    except Exception:
        pass


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else ""
    if not sid:
        return
    os.makedirs(BASE, exist_ok=True)
    try:
        os.mkdir(LOCKDIR)          # mkdir = verrou atomique, pas de course
    except FileExistsError:
        age = time.time() - os.path.getmtime(LOCKDIR)
        if age < MAX_WAIT + 10:
            return                  # a reloader is already waiting: nothing to do
        os.utime(LOCKDIR, None)     # stale lock (process killed): we take it over

    try:
        deadline = time.time() + MAX_WAIT
        while time.time() < deadline:
            if time.time() - feed_mtime(sid) >= QUIET:
                break
            time.sleep(POLL)

        port = dev_port()
        if not port:
            return                  # no app served: nothing to show
        n = reload_tabs(port)
        if n == 0:
            open_once(port)
            n = 1
        write_state(dict(read_state(), ts=time.time(), port=port, tabs=n))
    finally:
        try:
            os.rmdir(LOCKDIR)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
