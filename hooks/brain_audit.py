#!/usr/bin/env python3
"""brain_audit — operational state of the distillation pipeline (not brain_doctor).

brain_doctor checks the CONSISTENCY of the knowledge (links, orphans, front matter).
brain_audit answers a different question: "what has been LOST or is pending, and
is the system healthy?" — without modifying anything.

It cross-references the raw layer (transcripts) with what has been distilled or queued,
and reads the resilience markers (lock, quota, login) to give a verdict.

The reassuring principle: a transcript that exists is NEVER irreversibly lost.
"Lost" only ever means "not distilled yet" → recoverable as long as the .jsonl exists.

Usage :
  brain_audit.py            → rapport lisible
  brain_audit.py --json     → writes state/audit.json (for hooks) + a report
  brain_audit.py --quiet    → exit code seulement (0 sain / 1 attention)
"""
import os, sys, json, time, glob, subprocess

def _transcripts_key() -> str:
    """The folder name Claude Code uses for this HOME, under ~/.claude/projects.

    It encodes the absolute home path by replacing BOTH "/" and "." with "-".
    Replacing only "/" works for a plain account name and breaks silently for a
    home like /Users/john.smith: the transcripts folder is never found, so
    distillation runs and finds nothing to do. No error, no signal.
    """
    return os.path.expanduser("~").replace("/", "-").replace(".", "-")


BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
STATE = os.path.join(BRAIN, "state")
TDIR = os.path.join(os.path.expanduser("~/.claude/projects"), _transcripts_key())   # couche brute (transcripts)
DISTILLED = os.path.join(BRAIN, "sessions", ".distilled.json")
MIN_MSG = 20                                                    # seuil de auto_maintain
# Birth of the automatic system. Before that date there was no auto-distillation
# → knowledge was captured by hand; undistilled is NOT an anomaly back there.
INFRA_BIRTH = time.mktime(time.strptime("2026-06-21", "%Y-%m-%d"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import brain_guard as guard          # reuses queue/quota/login reads + the lock
except Exception:
    guard = None


def _rj(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def _nlines(p):
    try:
        with open(p, "rb") as f:
            return sum(1 for l in f if l.strip())
    except Exception:
        return 0


def _last_commit():
    try:
        r = subprocess.run(["git", "-C", BRAIN, "log", "-1", "--format=%cr · %s"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return "?"


def collect():
    distilled = set(_rj(DISTILLED, []))
    queued = list(_rj(os.path.join(STATE, "pending-distill.json"), []))

    transcripts = []
    for p in glob.glob(os.path.join(TDIR, "*.jsonl")):
        sid = os.path.basename(p)[:-6]
        transcripts.append({"sid": sid, "n": _nlines(p), "mtime": os.path.getmtime(p)})

    pre, post = [], []
    for t in transcripts:
        if t["sid"] in distilled or t["sid"] in queued or t["n"] < MIN_MSG:
            continue
        (post if t["mtime"] >= INFRA_BIRTH else pre).append(t)
    pre.sort(key=lambda t: t["n"], reverse=True)
    post.sort(key=lambda t: t["mtime"], reverse=True)

    # --- pipeline health (resilience markers) ---
    quota = _rj(os.path.join(STATE, "quota.json"), {})
    login = _rj(os.path.join(STATE, "login.json"), {})
    lock = _rj(os.path.join(STATE, "maintenance.lock"), None)
    status = _rj(os.path.join(STATE, "status.json"), {})
    blocked = bool(quota.get("blocked_until", 0) > time.time())
    logged_out = bool(login.get("logged_out"))

    lock_state = "free"
    if lock:
        pid_alive = guard._alive(lock.get("pid")) if guard else False
        stale = (time.time() - lock.get("ts", 0)) > (20 * 60)
        lock_state = "active" if (pid_alive and not stale) else "stale (will be reclaimed)"

    return {
        "transcripts": len(transcripts),
        "distilled": len(distilled),
        "queued": queued,
        "pre_infra": pre,
        "post_infra": post,
        "quota_blocked": blocked,
        "quota_until": quota.get("blocked_until", 0),
        "logged_out": logged_out,
        "lock_state": lock_state,
        "status": status.get("state", "?"),
        "last_metric_ts": None,
        "last_commit": _last_commit(),
    }


def main():
    d = collect()
    # a transcript that exists is recoverable → no IRREVERSIBLE loss is possible
    irreversible_loss = 0
    health_ok = not d["quota_blocked"] and not d["logged_out"] and d["lock_state"] != "stale (will be reclaimed)"

    if "--json" in sys.argv:
        try:
            os.makedirs(STATE, exist_ok=True)
            json.dump(d, open(os.path.join(STATE, "audit.json"), "w"),
                      ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

    if "--quiet" not in sys.argv:
        ico = "✅" if health_ok else "⚠️"
        print(f"{ico} brain audit — distillation pipeline")
        print(f"  Raw layer   : {d['transcripts']} transcripts (never deleted)")
        print(f"  Distilled   : {d['distilled']}   ·   queued: {len(d['queued'])}")
        print(f"  Irreversible loss: {irreversible_loss}  (a transcript that exists is recoverable)")
        print()
        print(f"  Maintenance lock: {d['lock_state']}   ·   capsule status: {d['status']}")
        if d["quota_blocked"]:
            reste = int((d["quota_until"] - time.time()) / 60)
            print(f"  ⚠️  Quota spent — resuming in ~{reste} min (the queue drains on reset)")
        else:
            print(f"  Quota: OK")
        if d["logged_out"]:
            print(f"  ⚠️  Logged out — run `claude /login` (sessions are re-queued meanwhile)")
        print(f"  Last commit: {d['last_commit']}")

        if d["queued"]:
            print(f"\n  📥 Catch-up queue ({len(d['queued'])}) — drained 1 per 10 min by launchd:")
            for sid in d["queued"]:
                print(f"     {sid[:8]}")

        if d["post_infra"]:
            # Since 2026-08-13 this list is no longer merely OBSERVED: launchd drains
            # it (one an hour, cf. resume_pending.backlog_to_catch_up). So we state
            # the fate of each line, otherwise the display suggests a backlog that
            # sleeps — which is exactly what it did for three weeks.
            try:
                import resume_pending as rp
                log = rp._log()
                grace, floor, cap = rp.OPEN_SESSION_GRACE, rp.MIN_BACKLOG_LINES, rp.MAX_ATTEMPTS
            except Exception:
                log, grace, floor, cap = {}, 2 * 3600, 60, 2

            def _fate(t):
                if log.get(t["sid"], {}).get("attempts", 0) >= cap:
                    return "given up (2 failures)"
                if t["n"] < floor:
                    return "too short, ignored"
                if time.time() - t["mtime"] < grace:
                    return "session may still be open"
                return "will be caught up"

            print(f"\n  🟠 Substantial sessions left undistilled SINCE the automatic system "
                  f"({len(d['post_infra'])}) — drained 1/hour by launchd:")
            for t in d["post_infra"]:
                when = time.strftime("%m-%d %H:%M", time.localtime(t["mtime"]))
                print(f"     {when}  {t['n']:>5} lines  {t['sid'][:8]}  → {_fate(t)}")
        else:
            print(f"\n  ✅ No undistilled session since the automatic system started.")

        if d["pre_infra"]:
            print(f"\n  ⚪ {len(d['pre_infra'])} pre-infrastructure sessions undistilled — knowledge was "
                  f"captured by hand back then, transcripts kept as a safety net (not an anomaly).")

    sys.exit(0 if health_ok else 1)


if __name__ == "__main__":
    main()
