#!/usr/bin/env python3
"""At session start, shows the morning/evening round that has not been seen.

WHY THIS HOOK EXISTS. The `etat_projets.py` round announced itself through a macOS banner
(`osascript display notification`). On 2026-08-14 the author noticed nothing had arrived in the morning.
Investigation: the service HAD run (`runs = 4`, `last exit code = 0`, a "morning" line in
the round's log) and `osascript` had returned 0 — but Script Editor, the app on whose behalf
a launchd agent posts its notifications, appears nowhere in `com.apple.ncprefs`, even
after a forced attempt. So the channel failed silently while returning a green code.

It is the rule "an exit code is never the observable", applied this time to the announcement
channel: the round was good, its measurement was good, and nobody ever read it.

The remedy is not to repair the banner — its delivery cannot be proved from a
script. It is to announce **where the author is certainly looking**: their working
session. The marker stays pending until it has been shown once, then it goes quiet.

Usage: called with no argument by the SessionStart hook. Never writes to stderr, never
blocks startup: a failure here must not cost a session.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # CODE_ROOT, legitimate
from brain_racine import brain_root

# I-1 (2026-08-21). Before: `os.path.expanduser("~/.c-brain/trunk")` — a literal NO
# variable could redirect. This module was the last I1-FAIL keeping an orchestrator that was
# ALREADY compliant in E0*: its SessionStart hook has carried BRAIN_HOME since L1.0, and the child
# ignored it. A parent that correctly passes on an identity the child throws away produces
# nominal compliance — more misleading than no anchoring at all.
BRAIN = brain_root(__file__)
ANNONCE = os.path.join(BRAIN, "state", "round-to-announce.json")

# Beyond this, the round is no longer worth announcing: it describes an outdated state, and
# announcing it would pass an old measurement off as the new one.
PEREMPTION_H = 18


def main() -> int:
    try:
        with open(ANNONCE, encoding="utf-8") as f:
            marque = json.load(f)
    except FileNotFoundError:
        return 0
    except Exception:
        return 0

    if marque.get("announced_at"):
        return 0                                    # already seen: not repeated

    texte = (marque.get("text") or "").strip()
    if not texte:
        return 0

    try:
        ecrit = dt.datetime.fromisoformat(marque["written_at"])
        heures = (dt.datetime.now() - ecrit).total_seconds() / 3600
    except Exception:
        heures = 0.0

    if heures > PEREMPTION_H:
        _marquer_vue(marque, "expired")
        return 0

    quand = "just now" if heures < 1 else f"{int(heures)} h ago"
    print(f"<project-status-round>\nUnread project round, written {quand} "
          f"(the macOS banner does not show: see hooks/ronde_annonce.py).\n\n"
          f"{texte}\n</project-status-round>")
    _marquer_vue(marque, "shown")
    return 0


def _marquer_vue(marque: dict, raison: str) -> None:
    marque["announced_at"] = dt.datetime.now().isoformat()
    marque["reason"] = raison
    try:
        with open(ANNONCE, "w", encoding="utf-8") as f:
            json.dump(marque, f, ensure_ascii=False, indent=2)
    except Exception:
        pass                                        # at worst, it will show once more


if __name__ == "__main__":
    sys.exit(main())
