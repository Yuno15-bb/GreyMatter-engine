#!/usr/bin/env python3
"""Ligne « modifications » de la barre de bas de session.

No window: the tracker lives INSIDE the session, at the very bottom, permanently.
Imported by ~/.claude/statusline.py, which passes it the session_id.

INCREMENTAL aggregation with a cursor: the whole stream is never re-read on every
redraw. The cursor only advances after the lines have been processed successfully
— advancing it first would let one exception swallow the whole batch.
"""

import json
import os
import socket
import time

BASE = os.path.expanduser("~/.claude/companion")
SESSIONS = os.path.join(BASE, "sessions")
AGG = os.path.join(BASE, "agg")
PORTS = (3000, 5173, 4321, 8080, 8000, 4200)
PORT_TTL = 6           # seconds: we do not probe ports on every redraw
MAX_NAME = 34


def c(code, s):
    return "\033[" + code + "m" + s + "\033[0m"


def _load_agg(sid):
    try:
        with open(os.path.join(AGG, sid + ".json")) as f:
            a = json.load(f)
        if isinstance(a.get("files"), list):
            a["files"] = set(a["files"])
            return a
    except Exception:
        pass
    return {"offset": 0, "files": set(), "add": 0, "rem": 0,
            "last": None, "last_add": 0, "last_rem": 0, "last_ts": 0,
            "masked": 0, "ended": False}


def _save_agg(sid, a):
    try:
        os.makedirs(AGG, exist_ok=True)
        out = dict(a)
        out["files"] = sorted(a["files"])
        tmp = os.path.join(AGG, sid + ".json.tmp")
        with open(tmp, "w") as f:
            json.dump(out, f)
        os.replace(tmp, os.path.join(AGG, sid + ".json"))   # remplacement atomique
    except Exception:
        pass


def aggregate(sid):
    """Re-reads only the new bytes of the stream and updates the totals."""
    feed = os.path.join(SESSIONS, sid + ".jsonl")
    a = _load_agg(sid)
    try:
        size = os.path.getsize(feed)
    except OSError:
        return None
    if size < a["offset"]:
        a = _load_agg("__empty__")         # stream recreated: we start over
        a["offset"] = 0
    if size == a["offset"]:
        return a if a["files"] or a["last"] else None

    with open(feed, "r", encoding="utf-8", errors="replace") as f:
        f.seek(a["offset"])
        chunk = f.read(size - a["offset"])

    lines = chunk.split("\n")
    tail = lines.pop()                     # incomplete line: next round
    consumed = 0
    for line in lines:
        consumed += len(line.encode("utf-8")) + 1
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue                        # unreadable line: we move on anyway
        if ev.get("type") == "end":
            a["ended"] = True
            continue
        if ev.get("type") != "diff":
            continue
        a["files"].add(ev.get("file") or "?")
        a["add"] += ev.get("added") or 0
        a["rem"] += ev.get("removed") or 0
        if ev.get("masked"):
            a["masked"] += 1
        a["last"] = ev.get("rel") or ev.get("file") or "?"
        a["last_add"] = ev.get("added") or 0
        a["last_rem"] = ev.get("removed") or 0
        a["last_ts"] = ev.get("ts") or 0
    a["offset"] += consumed                 # cursor advanced AFTER processing
    _save_agg(sid, a)
    return a


def _probe(port):
    s = socket.socket()
    s.settimeout(0.06)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def dev_port():
    """An open dev port, with a short cache: the "the app is running" signal."""
    cache = os.path.join(BASE, "port.json")
    now = time.time()
    try:
        with open(cache) as f:
            d = json.load(f)
        if now - d.get("ts", 0) < PORT_TTL:
            return d.get("port")
    except Exception:
        pass
    found = next((p for p in PORTS if _probe(p)), None)
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(cache, "w") as f:
            json.dump({"ts": now, "port": found}, f)
    except Exception:
        pass
    return found


def ago(ts):
    if not ts:
        return ""
    d = int(time.time() - ts)
    if d < 60:
        return str(d) + "s"
    if d < 3600:
        return str(d // 60) + "min"
    return str(d // 3600) + "h"


def line(sid, color=True):
    """The line to display, or '' when there is nothing to say."""
    if not sid:
        return ""
    a = aggregate(sid)
    if not a or not a["files"]:
        return ""

    def col(code, s):
        return c(code, s) if color else s

    parts = [col("90", "✎") + " " + col("1;37", str(len(a["files"])) + "f")
             + " " + col("32", "+" + str(a["add"]))
             + " " + col("31", "−" + str(a["rem"]))]

    if a["last"]:
        name = a["last"]
        if len(name) > MAX_NAME:
            name = "…" + name[-(MAX_NAME - 1):]
        parts.append(col("37", name)
                     + col("32", " +" + str(a["last_add"]))
                     + col("31", " −" + str(a["last_rem"]))
                     + col("90", " " + ago(a["last_ts"])))

    if a["masked"]:
        parts.append(col("33", "🔒" + str(a["masked"])))

    p = dev_port()
    parts.append(col("32", "app :" + str(p)) if p else col("90", "app —"))

    # Last browser-tab reload: the "what I see is up to date" signal
    r = reload_state()
    if r.get("ts"):
        parts.append(col("36", "↻ " + ago(r["ts"])))

    return col("90", " │ ").join(parts)


def reload_state():
    try:
        with open(os.path.join(BASE, "reload.json")) as f:
            return json.load(f)
    except Exception:
        return {}


if __name__ == "__main__":
    import sys
    print(line(sys.argv[1] if len(sys.argv) > 1 else "", color=True) or "(rien)")
