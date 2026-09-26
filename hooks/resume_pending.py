#!/usr/bin/env python3
"""resume_pending — reprise autonome du backlog de distillation.

Run periodically (launchd, roughly every 10 min). If:
  - le quota est revenu (preflight_ok),
  - la file pending-distill.json n'est pas vide,
  - no maintenance is already running (the lock is free),
alors il distille la session en attente la plus ancienne (une par passage).

→ Answers: "window closed + quota exhausted → does it resume by itself on reset?"
  YES: without opening anything, the backlog drains as soon as the quota resets.

Always exits 0. Does nothing (and costs nothing) with no work, or while the quota is still spent.
"""
import os, sys, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_maintain as am          # reuses launch_agent + session_msg_count
try:
    import brain_guard as guard
except Exception:
    guard = None

QUEUE = os.path.join(am.BRAIN, "state", "pending-distill.json")
CATCHUP_LOG = os.path.join(am.BRAIN, "state", "catchup.json")

# --- Catching up on the backlog: sessions that never reached the queue ---
#
# Three brakes, because here we spend on work NOBODY asked for:
#   - a grace delay: a transcript still warm may be an OPEN session;
#   - a slow cadence: the backlog has slept for weeks, there is no urgency in
#     draining it within the hour — and an agent costs ~$1, against the
#     ~$0.00003 of the credit probe;
#   - a cap on attempts: a session that fails in a loop is given up VISIBLY
#     rather than burning budget in silence.
OPEN_SESSION_GRACE = 2 * 3600     # transcript idle for 2 h → session really closed
CATCHUP_INTERVAL = 3600           # at most one backlog catch-up per hour
MIN_BACKLOG_LINES = 60            # substance required: > MIN_MSG (20) of the current flow
MAX_ATTEMPTS = 2

CATCHUP_PICKED = set()            # sids chosen by backlog_to_catch_up() on this pass


def _log():
    try:
        return json.load(open(CATCHUP_LOG, encoding="utf-8"))
    except Exception:
        return {}


def note_attempt(sid):
    """Records the attempt BEFORE launching — otherwise an agent that dies without
    writing does not count, and the same session restarts forever (the dead-loop
    trap, cf. [[a-guessed-delay-does-not-know-you-topped-up]])."""
    j = _log()
    j[sid] = {"attempts": j.get(sid, {}).get("attempts", 0) + 1, "ts": time.time()}
    j["_last"] = time.time()
    try:
        json.dump(j, open(CATCHUP_LOG, "w", encoding="utf-8"))
    except Exception:
        pass


def backlog_to_catch_up():
    """The most recent orphan session we allow ourselves to distil, or None.

    Reuses `brain_audit.collect()`: it already knows how to cross the transcripts
    on disk with the distilled ones and the queue. We do not re-cut that
    computation, we finally wire it to an action."""
    j = _log()
    if time.time() - (j.get("_last") or 0) < CATCHUP_INTERVAL:
        return None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import brain_audit
        candidates = brain_audit.collect()["post_infra"]     # already sorted newest first
    except Exception:
        return None
    for t in candidates:
        if t["n"] < MIN_BACKLOG_LINES:
            continue
        if time.time() - t["mtime"] < OPEN_SESSION_GRACE:
            continue                                        # may still be open
        if j.get(t["sid"], {}).get("attempts", 0) >= MAX_ATTEMPTS:
            continue                                        # visible give-up, not a silent one
        CATCHUP_PICKED.add(t["sid"])
        return t["sid"]
    return None


def main():
    if guard is None:
        return
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return                              # we are already a headless run

    # The freeze on autonomous writers lives in auto_maintain.main(), and THIS path
    # does not go through main(): it calls launch_agent directly. So the freeze was
    # bypassable every ten minutes by launchd, without anyone seeing it. Same mistake
    # as [[desarmer-le-hook-ne-suffit-pas-la-session-voisine-commite-aussi]]: a lock
    # placed at ONE caller does not protect against the others.
    # The queue keeps filling up — nothing is lost, everything waits for the thaw.
    if os.path.exists(os.path.join(am.BRAIN, "state", "FREEZE")):
        return

    # Notes whose processing is UNFINISHED, before looking at the queue — otherwise a
    # half-written note with an empty queue would never be seen (the early return
    # below cuts the path off). The check only reads local files: zero tokens, ~20 ms
    # over 314 notes. It caps its own retries.
    try:
        guard.requeue_unfinished()
    except Exception:
        pass

    try:
        pending = json.load(open(QUEUE, encoding="utf-8"))
    except Exception:
        pending = []

    # The queue only holds what ENTERED it, that is, sessions whose SessionEnd
    # fired. A session killed outright — crash, sleep, terminal closed in one go —
    # runs no code at all, so it never queues itself: the credit coming back does
    # not concern it, it is not waiting anywhere. Observed on 2026-08-13: empty
    # queue, and yet 8 real work sessions (22/07 → 03/08) never distilled.
    # `brain audit` had been listing them for weeks — the knowledge was there, it
    # was simply wired to NO action. Same pattern as the quota block of that same
    # day: a sensor that observes but does not act.
    if not pending:
        orphan = backlog_to_catch_up()
        if not orphan:
            return                          # nothing pending, nothing orphaned
        pending = [orphan]                  # handled like the rest, one per pass

    if not guard.preflight_ok():
        return                              # quota still spent → retry on the next tick

    if not guard.acquire_lock():
        return                              # maintenance is already running

    # take the oldest one ATOMICALLY (flock): safe even if a SessionEnd queues
    # a new session at the very same moment.
    sid = guard.dequeue_one() or pending[0]
    if not sid:                             # queue drained meanwhile by another process
        guard.release_lock()
        return
    if sid in CATCHUP_PICKED:
        note_attempt(sid)                   # trace BEFORE launching: one attempt = one trace
    n = am.session_msg_count(sid) or am.MIN_MSG
    am.launch_agent(sid, n, to_distill=True)   # the wrapper releases the lock at the end of the run


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
