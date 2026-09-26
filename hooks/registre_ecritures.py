#!/usr/bin/env python3
"""registre_ecritures — make OBSERVABLE which session moved a trunk note.

WHY THIS FILE EXISTS (measured on 2026-08-28)
    `state/manual-saves.jsonl` had not received a single entry since 2026-08-18,
    while 189 knowledge notes carried a later modification date. The
    register was not broken: reproduced on a throwaway trunk, `on_fiche_write.py`
    writes its entry correctly. It was its TRIGGER that no longer saw anything —
    it is armed only on `PostToolUse Write|Edit`, and sweeping the 32 transcripts
    after 18/08 finds only 9 note writes through those two tools, all of them
    from a single session, the very one the register's last entries date from.
    Everything else goes through Bash — heredoc, `sed -i`, a Python script — or through
    the background agents, which the register excludes on purpose.

WHAT IT IS NOT
    It is NOT a replacement for `manual-saves.jsonl`. That one has a narrow contract and
    a single consumer: `auto_maintain.py` reads it to tell the distiller "do not
    recreate these notes, the session wrote them by hand". Pouring script writes
    into it would silence the distiller on knowledge nobody wrote. The two
    registers coexist, each with its own contract.

WHAT IT PROVES, AND WHAT IT DOES NOT
    It observes an EFFECT — a note whose modification date has passed the last
    pass — not a MEANS. So it covers any tool, including those that
    do not exist yet. In return, the identity it records is that of the session
    whose tool has just handed back control: an attribution by COINCIDENCE, not a
    proof of authorship. The `attribution` field says so in every line, so that no
    later reading can take it for more than it is.

OUT OF COVERAGE, AND DECLARED
    A write made while no tool is running (background agent, scheduled task,
    external editor) is seen only at the next pass, and will then be attributed to the
    session of that pass. Two sessions active at the same time can steal a line from each other.
    The register answers "something wrote this note around this time", never
    "this session wrote it".
"""
import json
import os
import sys
import time

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
ZONES = ("projects", "lessons", "meta", "life", "skills")
REGISTRE = os.path.join(BRAIN, "state", "note-writes.jsonl")
JALON = os.path.join(BRAIN, "state", "note-writes.mark")
# A first pass without a mark would see THE WHOLE trunk as "modified" and write 500
# lines of noise. So it is bounded: on the first pass, the mark is set and nothing is logged.
FENETRE_MAX = 3600.0


def _jalon_lu():
    try:
        return float(open(JALON, encoding="utf-8").read().strip())
    except Exception:
        return None


def _jalon_ecrit(t):
    tmp = JALON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("%.6f" % t)
    os.replace(tmp, JALON)


def fiches_modifiees(depuis):
    """The .md notes of the knowledge zones whose mtime is past `depuis`. 3.4 ms measured."""
    out = []
    for z in ZONES:
        racine = os.path.join(BRAIN, z)
        if not os.path.isdir(racine):
            continue
        for root, dirs, files in os.walk(racine):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for nom in files:
                if not nom.endswith(".md"):
                    continue
                chemin = os.path.join(root, nom)
                try:
                    m = os.stat(chemin).st_mtime
                except OSError:
                    continue
                if m > depuis:
                    out.append((os.path.relpath(chemin, BRAIN), m))
    return sorted(out)


def main(data):
    maintenant = time.time()
    precedent = _jalon_lu()
    _jalon_ecrit(maintenant)
    if precedent is None:
        return 0                      # first pass: arm, do not log
    depuis = max(precedent, maintenant - FENETRE_MAX)
    touchees = fiches_modifiees(depuis)
    if not touchees:
        return 0
    sid = (data or {}).get("session_id") or "unknown"
    outil = (data or {}).get("tool_name") or "unknown"
    os.makedirs(os.path.dirname(REGISTRE), exist_ok=True)
    with open(REGISTRE, "a", encoding="utf-8") as f:
        for rel, m in touchees:
            f.write(json.dumps({"ts": int(maintenant), "sid": sid, "path": rel,
                                "mtime": int(m), "gap_s": int(maintenant - m),
                                "tool": outil,
                                "attribution": "coincidence"}, ensure_ascii=False) + "\n")
    return len(touchees)


if __name__ == "__main__":
    try:
        charge = json.loads(sys.stdin.read() or "{}")
    except Exception:
        charge = {}
    try:
        main(charge)
    except Exception:
        pass                          # golden rule of the trunk's hooks: never block
    sys.exit(0)
