#!/usr/bin/env python3
"""brain_guard — rend la maintenance autonome increvable face aux tokens / au compte.

Garanties :
  - never a crash (everything fails gently),
  - never a half state (lock + resume),
  - never a lost session (a retried queue),
  - never a false "distilled" on a 429 (we read the RESULT, not the exit code).

Principle: the structural consistency of the brain NEVER depends on an LLM call.
A quota or account problem only DEFERS distillation; it never breaks the system.
"""
import os, sys, json, time, subprocess, hashlib, re, fcntl

def _transcripts_key() -> str:
    """The folder name Claude Code uses for this HOME, under ~/.claude/projects.

    It encodes the absolute home path by replacing BOTH "/" and "." with "-".
    Replacing only "/" works for a plain account name and breaks silently for a
    home like /Users/john.smith: the transcripts folder is never found, so
    distillation runs and finds nothing to do. No error, no signal.
    """
    return os.path.expanduser("~").replace("/", "-").replace(".", "-")


BRAIN = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
STATE = os.path.join(BRAIN, "state")
LOCK  = os.path.join(STATE, "maintenance.lock")
QUEUE = os.path.join(STATE, "pending-distill.json")   # sessions to distil later
QUOTA = os.path.join(STATE, "quota.json")             # {"blocked_until": epoch, "msg": ...}
LOGIN = os.path.join(STATE, "login.json")             # {"logged_out": bool, "ts": ..., "msg": ...}
LOCK_TTL = 20 * 60   # past this: the lock is presumed dead (zombie process / machine asleep)


def _rj(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def _wj(p, o):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _status_idle():
    try:
        subprocess.run([sys.executable, os.path.join(BRAIN, "hooks", "brain_status.py"), "idle"],
                       timeout=10)
    except Exception:
        pass


# --- A. Lock with zombie reclaim (fixes the stuck 'busy' state) -----
def acquire_lock(sid=None) -> bool:
    """True if we take the lock. Reclaims a stale lock or a dead process,
    re-queues the interrupted session and unblocks a status stuck on 'busy'."""
    payload = {"pid": os.getpid(), "ts": time.time(),
               "sid": sid, "account": account_fingerprint()}
    # ATOMIC creation (O_EXCL): closes the race where "two SessionEnd hooks read
    # 'no lock' at the same time and both take it". If the file does not exist we create it
    # in a single syscall; otherwise we fall through to the zombie-reclaim logic below.
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, json.dumps(payload, ensure_ascii=False).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        pass
    except Exception:
        pass                                 # filesystem without O_EXCL → fall back to reclaim
    cur = _rj(LOCK, None)
    if cur and _alive(cur.get("pid")) and (time.time() - cur.get("ts", 0)) < LOCK_TTL:
        return False                         # une VRAIE maintenance tourne → on n'en lance pas 2
    if cur:                                  # stale lock or dead process → we take it over
        if cur.get("sid"):
            enqueue(cur["sid"])              # la session interrompue repart en file
        _status_idle()                       # unblock a status stuck on 'busy'
    _wj(LOCK, payload)
    return True


def update_lock_pid(pid):
    """Rewrites the lock with the PID of the DETACHED WORKER. Essential: the hook that takes
    the lock (auto_maintain / resume_pending) DIES right after spawning the worker; without this,
    `_alive(pid)` sees a dead PID → the next session declares the lock stale and starts a
    maintenance run IN PARALLEL (a git/Inbox race). We therefore write
    the PID of the detached `sh -c`, alive for the whole pass; the worker calls `release` at the end."""
    cur = _rj(LOCK, None) or {}
    cur["pid"] = int(pid)
    cur["ts"] = time.time()
    _wj(LOCK, cur)


def release_lock():
    try:
        os.remove(LOCK)
    except FileNotFoundError:
        pass
    except Exception:
        pass


# --- B. Compte actif (creds en Keychain → empreinte indirecte) -------------
def account_fingerprint() -> str:
    """Approximate identity of the active account, without reading any secret. Claude Code
    credentials live in the macOS Keychain: we rely on the account_uuid present in
    recent transcripts (a reliable signal of which account ran)."""
    try:
        tdir = os.path.join(os.path.expanduser("~/.claude/projects"), _transcripts_key())
        jsonls = sorted(
            (os.path.join(tdir, f) for f in os.listdir(tdir) if f.endswith(".jsonl")),
            key=os.path.getmtime, reverse=True)
        for p in jsonls[:1]:
            for line in open(p, encoding="utf-8"):
                m = re.search(r'"(?:accountUuid|account_uuid)"\s*:\s*"([^"]+)"', line)
                if m:
                    return hashlib.sha256(m.group(1).encode()).hexdigest()[:12]
    except Exception:
        pass
    return "unknown"


# --- C. Preflight: are we allowed to spend tokens right now? -----
PROBE_INTERVAL = 900            # 15 min between two probes, asked for by the author on 2026-08-13


def preflight_ok(probe: bool = True) -> bool:
    """The right to spend is no longer GUESSED, it is ASKED for.

    Not blocked → no call, no cost (the ordinary case).

    Blocked → we no longer merely wait out an assumed delay, because that delay
    cannot know the user has just topped up their cap or switched accounts (lived
    on 2026-08-13: cap raised at 08:35, maintenance frozen for nothing until 09:32,
    unblocked by hand). Two checks:

      1. the account changed (different token) → immediate green light, FREE;
      2. otherwise, at most every 15 min, a ONE-token probe (~$0.00003) asks the
         API whether a real request goes through (cf. quota_probe).

    This is NOT the dead loop of [[account-quota-resilience]] coming back: what
    looped there was restarting a FULL AGENT (~$1) on the expiry of a guessed
    delay. Here the repetition is a near-free probe, and the agent only starts on
    an OBSERVED green light.

    `probe=False` for a caller that wants the old, purely local behaviour."""
    q = _rj(QUOTA, None)
    if not q or time.time() >= q.get("blocked_until", 0):
        return True                          # not blocked: nothing to ask
    if not probe:
        return False

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import quota_probe as qp
    except Exception:
        return False                         # probe unavailable → old behaviour

    # 1. Account switch: the token changes the second the user switches over.
    fp = qp.token_fingerprint()
    if fp and q.get("fingerprint") and fp != q["fingerprint"]:
        _wj(QUOTA, {"blocked_until": 0, "family": None, "failures": 0,
                    "msg": "ok — account changed", "fingerprint": fp,
                    "last_probe": time.time()})
        return True

    # 2. Cadence: one probe at most every 15 min.
    if time.time() - (q.get("last_probe") or 0) < PROBE_INTERVAL:
        return False
    v = qp.probe()
    if v["ok"]:
        _wj(QUOTA, {"blocked_until": 0, "family": None, "failures": 0, "msg": "ok",
                    "fingerprint": v["fingerprint"], "last_probe": v["ts"],
                    "limits": v["limits"]})
        return True

    q["last_probe"] = v["ts"]
    q["fingerprint"] = v["fingerprint"] or q.get("fingerprint", "")
    q["probe_reason"] = v["reason"]
    q["limits"] = v["limits"]
    # The API gives the EXACT time of the return: it replaces the guessed backoff.
    # Except on 401 (stale token): that is not a verdict about credit.
    if v["http"] not in (None, 401) and v.get("reset"):
        q["blocked_until"] = v["reset"]
    _wj(QUOTA, q)
    return False


# Progressive backoff when the message does NOT say when it restarts (in hours).
# Measured on 2026-08-07: "monthly spend limit" and "weekly limit" carry no reset
# time at all. The old +1h default therefore treated a WEEKLY cap as a one-hour
# pause: every hour the block expired, maintenance restarted, got refused, blocked
# for another hour — in a loop all day long, never distilling anything. The defect
# was not the queue, it was its waiting time. cf. [[account-quota-resilience]].
_BACKOFF_H = [1, 2, 4, 8, 12, 24]


def _limit_family(msg: str) -> str:
    """Three families, because they do NOT restart at the same rhythm.
    'session' carries its reset time in the message; the other two do not."""
    m = msg.lower()
    if "monthly spend limit" in m or "spend limit" in m:
        return "cap"              # spend cap: monthly reset / raised by hand
    if "weekly limit" in m or "week" in m:
        return "weekly"           # weekly limit
    return "session"


def _parse_reset_epoch(msg: str, failures: int = 0):
    """When do we restart? Two regimes:
      - the message gives the time ('... resets 2:50pm') → we read it, it is exact;
      - it does not (spend cap, weekly) → PROGRESSIVE backoff indexed on the number
        of consecutive failures, never one retry per hour until the end of time.
    `failures` = counter carried by the quota marker (0 on the first failure)."""
    try:
        m = re.search(r'resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)', msg, re.I)
        if m:
            h = int(m.group(1)) % 12
            if m.group(3).lower() == "pm":
                h += 12
            mn = int(m.group(2) or 0)
            now = time.localtime()
            target = list(now); target[3] = h; target[4] = mn; target[5] = 0
            t = time.mktime(time.struct_time(tuple(target)))
            if t < time.time():
                t += 24 * 3600                # resets tomorrow
            return t
        # no time in the message → progressive backoff, capped at 24 h
        step = _BACKOFF_H[min(max(failures, 0), len(_BACKOFF_H) - 1)]
        return time.time() + step * 3600
    except Exception:
        return time.time() + 3600


# --- D. Reading the result: THE fix for the 429 trap -------------------
def interpret_result(last_cost_line: str, sid: str, is_distill: bool = True) -> bool:
    """True if the run REALLY succeeded. Otherwise: re-queue (if distilling) + the right marker.
    Fixes two traps where the CLI exits 0 with is_error=true:
      - 429 (quota)        → we read the RESULT and set the quota marker.
      - "Not logged in"    → the detached headless run starts unauthenticated and
        fails in under a second. We set a login marker AND re-queue the session so it
        replays at the next authenticated SessionEnd → no session is ever lost."""
    try:
        r = json.loads(last_cost_line)
    except Exception:
        r = {}
    res = str(r.get("result", ""))
    rl = res.lower()
    # --- garde-fou NOT LOGGED IN -----------------------------------------
    if "not logged in" in rl or "please run /login" in rl:
        _wj(LOGIN, {"logged_out": True, "ts": time.time(), "msg": res[:200]})
        if is_distill:
            enqueue(sid)                      # nothing distilled → we replay once logged in
        return False
    if r.get("is_error") or r.get("api_error_status"):
        if is_distill:
            enqueue(sid)                      # NOT distilled → retried later
        if r.get("api_error_status") == 429 or "limit" in rl:
            # The CONSECUTIVE failure counter drives the backoff and doubles as a
            # sensor: without it, nothing told a "first refusal" apart from a "ninth
            # refusal in a row", and the system restarted identically every time.
            prev = _rj(QUOTA, None) or {}
            fam = _limit_family(res)
            failures = (prev.get("failures", 0) + 1) if prev.get("family") == fam else 1
            # The fingerprint of the blocked account: if the user switches to another
            # account, preflight_ok sees it in the token and restarts at once, without
            # waiting out the backoff. The backoff stays as the net for when the probe
            # is unreachable; the first probe (≤ 15 min) replaces it with the API's
            # exact time.
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import quota_probe as qp
                fp = qp.token_fingerprint()
            except Exception:
                fp = ""
            _wj(QUOTA, {"blocked_until": _parse_reset_epoch(res, failures - 1),
                        "family": fam, "failures": failures,
                        "since": prev.get("since") if prev.get("family") == fam else time.time(),
                        "fingerprint": fp, "last_probe": 0,
                        "msg": res[:200]})
        return False
    _wj(LOGIN, {"logged_out": False, "ts": time.time()})   # run OK → the session was authenticated
    # tokens are back → lift the block AND reset the failure counter, otherwise the
    # next refusal would restart at the last backoff step.
    _wj(QUOTA, {"blocked_until": 0, "family": None, "failures": 0, "msg": "ok"})
    return True


# --- E. File d'attente : aucune session perdue -----------------------------
# Toutes les mutations de la file passent par _with_queue, qui prend un verrou
# EXCLUSIF (flock) sur le fichier le temps du read-modify-write. Indispensable :
# when SEVERAL sessions are closed at once, that many SessionEnd hooks run in
# parallel and call enqueue() simultaneously; without a lock, the last write
# overwrites the previous ones → sessions vanish from the queue. The flock serializes.
def _with_queue(mutate):
    """Ouvre la file sous verrou exclusif, applique mutate(list)->(new_list, ret),
    rewrites atomically, returns ret. Tolerates a missing fcntl (best-effort fallback)."""
    try:
        os.makedirs(STATE, exist_ok=True)
        f = open(QUEUE, "a+", encoding="utf-8")
    except Exception:
        q = _rj(QUEUE, [])
        nq, ret = mutate(list(q))
        _wj(QUEUE, nq)
        return ret
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
        except Exception:
            pass
        f.seek(0)
        raw = f.read().strip()
        try:
            q = json.loads(raw) if raw else []
        except Exception:
            q = []
        if not isinstance(q, list):
            q = []
        nq, ret = mutate(list(q))
        f.seek(0)
        f.truncate()
        f.write(json.dumps(nq, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())
        return ret
    finally:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        except Exception:
            pass
        f.close()


def enqueue(sid):
    if not sid:
        return
    def m(q):
        if sid not in q:
            q.append(sid)
        return q, None
    _with_queue(m)


def drain_queue():
    """Empties the queue and returns all of its content, atomically."""
    return _with_queue(lambda q: ([], q))


def dequeue_one():
    """Retire et renvoie la session la plus ancienne (None si vide), atomiquement.
    Preferable to drain+re-queue when only ONE session is handled per pass."""
    def m(q):
        if not q:
            return q, None
        s = q.pop(0)
        return q, s
    return _with_queue(m)


# --- F. Notes whose processing is UNFINISHED -------------------------------
# The hole the author named on 2026-08-07: the queue tracks SESSIONS, not notes.
# A distillation killed mid-flight re-queues its session (good). But a distillation
# that FINISHES while leaving a note half written marks the session as processed:
# the hole becomes invisible, and no counter moves.
# This check looks at the RESULT on disk, not at the run's exit code.
_NOTE_SKIP = ("sessions", "corpus", "node_modules", "capsule", "capsule-v2",
              "planet", "audits", "tools", "state", "companion", "tests", ".git")
MIN_BODY = 120           # below this, the note carries no useful content


def _read_note(path):
    """(frontmatter, body) or None when the file does not have the shape of a note."""
    try:
        t = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return None
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', t, re.S)
    return (m.group(1), m.group(2)) if m else None


def incomplete_notes(brain=None):
    """Lists the notes whose processing never went all the way through.
    Three symptoms, each observable on the file itself:
      - no frontmatter            → writing interrupted before the header
      - name/description missing  → header started, never filled in
      - body < MIN_BODY           → header laid down, content never written
    Measured on the real trunk at the time of writing: 0 notes reported out of 314.
    A check that shouts on a healthy trunk is a check people learn to ignore."""
    brain = brain or BRAIN
    out = []
    for root, dirs, files in os.walk(brain):
        rel_root = os.path.relpath(root, brain)
        head = rel_root.split(os.sep)[0]
        if head in _NOTE_SKIP:
            dirs[:] = []
            continue
        for f in files:
            # MEMORY.md / INDEX.md / README.md are MAPS, not notes: by design they
            # have no frontmatter. Reporting them is how you teach people to ignore
            # the check.
            if not f.endswith(".md") or f in ("MEMORY.md", "README.md", "INDEX.md"):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, brain)
            fm_body = _read_note(p)
            if fm_body is None:
                out.append({"note": rel, "reason": "no frontmatter", "sid": None})
                continue
            fm, body = fm_body
            reasons = []
            if not re.search(r'^\s*name\s*:', fm, re.M):
                reasons.append("name missing")
            if not re.search(r'^\s*description\s*:', fm, re.M):
                reasons.append("description missing")
            if len(body.strip()) < MIN_BODY:
                reasons.append("empty body")
            if reasons:
                m = re.search(r'originSessionId\s*:\s*([0-9a-fA-F-]+)', fm)
                out.append({"note": rel, "reason": ", ".join(reasons),
                            "sid": m.group(1) if m else None})
    return out


MAX_RETRIES = 2           # past this, we stop replaying and we SAY so


def requeue_unfinished(brain=None, journal=None):
    """Re-queues the sessions of unfinished notes that carry their origin.

    ⚠ The trap closed here: a note that stays incomplete AFTER reprocessing would
    re-queue itself on every tick of the timer — a loop burning tokens every ten
    minutes, exactly what we are trying to avoid. Hence a per-session attempt
    counter, capped: past it, the session is no longer replayed, it is reported.
    A visible give-up beats an invisible loop.

    Returns (notes_reported, sessions_requeued, sessions_given_up)."""
    journal = journal or os.path.join(STATE, "unfinished.json")
    inc = incomplete_notes(brain)
    hist = _rj(journal, {}) or {}
    sids = {x["sid"] for x in inc if x["sid"]}
    requeued, given_up = 0, 0
    for s in sids:
        tries = hist.get(s, {}).get("tries", 0)
        if tries >= MAX_RETRIES:
            given_up += 1
            continue
        enqueue(s)
        hist[s] = {"tries": tries + 1, "ts": time.time()}
        requeued += 1
    # a session whose notes became healthy again drops out of the history
    for s in list(hist):
        if s not in sids:
            hist.pop(s, None)
    _wj(journal, hist)
    return len(inc), requeued, given_up


# --- CLI: used by auto_maintain's shell wrapper -------------------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "interpret":
        # interpret <cost.jsonl> <sid> [distill 0|1] → exit 0 on success, 7 otherwise
        try:
            last = open(sys.argv[2], encoding="utf-8").read().splitlines()[-1]
        except Exception:
            last = "{}"
        sid = sys.argv[3] if len(sys.argv) > 3 else ""
        is_distill = (sys.argv[4] != "0") if len(sys.argv) > 4 else True
        ok = interpret_result(last, sid, is_distill)
        if not ok and _rj(LOGIN, {}).get("logged_out"):
            print("[brain_guard] not logged in — session re-queued, it will replay at the "
                  "next SessionEnd. Run `claude /login` to reactivate the agents.",
                  file=sys.stderr)
        sys.exit(0 if ok else 7)
    elif cmd == "release":
        release_lock(); sys.exit(0)
    elif cmd == "preflight":
        sys.exit(0 if preflight_ok() else 7)
    elif cmd == "unfinished":
        # unfinished [--requeue] → lists the notes whose processing never finished.
        # Exit 0 when the trunk is healthy, 7 when some remain — so an automatic
        # check can REACT instead of merely displaying.
        inc = incomplete_notes()
        for x in inc:
            print(f"  ⚠ {x['note']} — {x['reason']}"
                  + (f" (session {x['sid'][:8]})" if x["sid"] else " (origin unknown)"))
        if "--requeue" in sys.argv:
            n, s, giv = requeue_unfinished()
            print(f"[brain_guard] {n} unfinished note(s), {s} session(s) re-queued"
                  + (f", {giv} given up after {MAX_RETRIES} attempts" if giv else ""))
        elif not inc:
            print("[brain_guard] no unfinished note")
        sys.exit(0 if not inc else 7)
    sys.exit(0)
