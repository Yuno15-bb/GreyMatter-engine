#!/usr/bin/env python3
"""brain_battement — the desk companion's pulse.

PostToolUse hook on ALL tools: a tool call is the very definition
of "something is working".

2026-09-24 — also on UserPromptSubmit and PreToolUse, and `--end` on Stop.
With the orb in the notch, PostToolUse alone was no longer enough: while
Claude thinks or writes its answer, no tool finishes, the pulse goes stale
and the orb went back in the middle of the work. The user: "I can't see it working anymore".

⚠ THE DEFECT IT FIXES (2026-07-31). `on_fiche_write` wrote `busy` into
state/status.json, and NOTHING ever wrote `idle` back before the session ended.
`touch_status()` existed in brain_status.py but was called by NO
hook. Result: the file stayed on `busy` with a stale timestamp —
measured at 1754 s — the capsule applied its 30 s freshness guard, fell back
to rest, and the companion froze WHILE Claude was working.
The user: "it's frozen still on the desktop and it often does that".

A happy side effect: the freshness guard becomes the END detector. No more
tool calls → no more heartbeat → after 30 s the companion stops
by itself. No end-of-turn hook is needed.

⚠ We do not take over from an agent: if an agent is working and its status is
fresh, we only refresh its timestamp — its tint and its label
stay its own.

Always exits 0: a pulse must never make a tool fail.
"""
import sys, os, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    try:
        from brain_status import write_status, touch_status, STATUS
    except Exception:
        return
    try:
        try:
            with open(STATUS, "r", encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = {}
        frais = (time.time() - cur.get("ts", 0)) < 30
        # --end (Stop hook, 2026-09-24): the answer is finished, the orb goes back into
        # the notch at once instead of waiting for the pulse to go stale.
        # Only if it is OUR status: a running agent keeps its own.
        if "--end" in sys.argv:
            if cur.get("source", "you") == "you":
                write_status("idle")
            return
        if cur.get("state") == "busy" and frais:
            touch_status()                      # extend what is already running
        else:
            write_status("busy", "working", None, source="you")
    except Exception:
        pass

if __name__ == "__main__":
    main()
    sys.exit(0)
