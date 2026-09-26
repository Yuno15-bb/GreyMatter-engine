#!/usr/bin/env python3
"""track_read — the truth loop: logs when a note in the trunk is actually READ.

Hook PostToolUse (Read). Si un Read cible une fiche du tronc, on l'enregistre dans
state/read_log.jsonl. Cross-referenced with recall_log.jsonl (what was surfaced), it gives
the real USEFULNESS of each note: surfaced often but never read = of little use;
never surfaced nor read for a long time = dead weight (an archiving candidate).

A signal grounded in REAL usage, not introspection. Always exits 0.
"""
import sys, os, json, time

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
LOG = os.path.join(BRAIN, "state", "read_log.jsonl")
STRUCTURAL_MAPS = {"MEMORY.md", os.path.join("lessons", "INDEX.md")}


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    ti = data.get("tool_input", {}) or {}
    fp = ti.get("file_path") or ti.get("path")
    if not fp:
        return
    real = os.path.realpath(fp)
    # uniquement les fiches du tronc (pas les hooks/capsule/etc.)
    if not real.startswith(BRAIN + os.sep) or not real.endswith(".md"):
        return
    rel = os.path.relpath(real, BRAIN)
    if rel in STRUCTURAL_MAPS or rel.split(os.sep)[0] not in ("projects", "lessons", "life", "meta"):
        return
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()),
                                "sid": data.get("session_id") or "",
                                "path": rel}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    refresh_live()


def refresh_live():
    """Light the note up on the planet RIGHT NOW (~0.15 s): without this, "live" activity would
    only surface at the next note written or at session end — so never live.
    Best-effort and silent: a failure here must break nothing in the hook."""
    import subprocess
    # recall_feedback: closes the usage → ranking loop. Recomputed here, at the moment a
    # read has just happened, rather than by adding one more periodic task.
    for script in ("coactivation.py", "graph_export.py", "recall_feedback.py"):
        try:
            subprocess.run([sys.executable, os.path.join(BRAIN, "hooks", script)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
