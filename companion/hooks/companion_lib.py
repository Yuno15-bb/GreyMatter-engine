#!/usr/bin/env python3
"""Socle commun des hooks du Companion (suivi live des modifs, rendu dans la barre).

Non-negotiable constraints:
  - stdlib seule (Python 3.9 sur la machine cible) ;
  - NEVER blocking: everything is wrapped on the caller side, a failure is silent;
  - NEVER a secret shown: sensitive files are reported, not displayed.
"""

import hashlib
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".claude", "companion")
SESSIONS = os.path.join(BASE, "sessions")   # <sid>.jsonl: the event stream
SNAP = os.path.join(BASE, "snap")           # before-images stored by PreToolUse
AGG = os.path.join(BASE, "agg")             # totaux par session, pour la barre

MAX_DIFF_LINES = 500        # beyond this we truncate: no point storing a wall of text
MAX_FILE_BYTES = 2_000_000  # beyond this we do not diff (binary, bundle, asset)

# --- Secrets : liste noire de chemins, puis de lignes ------------------------
SECRET_PATH = re.compile(
    r"(^|/)(\.env(\.|$)|secrets?/|\.pem$|\.key$|id_rsa|credentials|"
    r"\.npmrc$|\.netrc$|service.?account.*\.json$)", re.I)
SECRET_LINE = re.compile(
    r"(?i)(secret|token|passwd|password|api[_-]?key|access[_-]?key|bearer|"
    r"private[_-]?key|client[_-]?secret|sk-[A-Za-z0-9]|ghp_|xox[baprs]-)")


def now():
    return time.time()


def ensure_dirs():
    for d in (SESSIONS, SNAP, AGG):
        os.makedirs(d, exist_ok=True)


def read_hook_input():
    """Lit le JSON du hook sur stdin. Renvoie {} si illisible."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def target_path(tool_input):
    """The path of the targeted file, whichever editing tool was used."""
    if not isinstance(tool_input, dict):
        return None
    for key in ("file_path", "notebook_path", "path"):
        p = tool_input.get(key)
        if isinstance(p, str) and p.strip():
            return os.path.abspath(os.path.expanduser(p))
    return None


def snap_path(sid, fpath):
    h = hashlib.sha1(fpath.encode("utf-8")).hexdigest()[:16]
    return os.path.join(SNAP, sid, h)


def is_secret_path(fpath):
    return bool(SECRET_PATH.search(fpath))


def mask_line(line):
    """Masks the VALUE of a sensitive line, keeps the key (useful for diagnosis)."""
    if not SECRET_LINE.search(line):
        return line
    m = re.match(r"^([+\-\s]?\s*[\w\.\-\[\]\"']{0,60}?\s*[:=]\s*)(.+)$", line)
    if m:
        return m.group(1) + "••• masked"
    return (line[:1] if line[:1] in "+- " else "") + "••• line masked"


def append_event(sid, event):
    """Appends an event to the session stream. Append-only: never a wholesale
    rewrite of the file, which would drop writes that landed in between."""
    ensure_dirs()
    event.setdefault("ts", now())
    path = os.path.join(SESSIONS, sid + ".jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path


def project_name(cwd):
    if not cwd:
        return "?"
    cwd = cwd.rstrip("/")
    base = os.path.basename(cwd)
    return base or cwd


# --- No window at all -------------------------------------------------------
# Le suivi est rendu par ~/.claude/statusline.py (2e ligne, via status_part.py) :
# INTEGRATED into the session, at the very bottom, permanently. Anchoring an Electron
# window to the Terminal window was removed — a floating window always ends up
# recouvrir ce qu'on veut lire, et deux sessions donnaient deux panneaux illisibles.
