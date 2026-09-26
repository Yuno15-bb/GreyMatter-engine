#!/usr/bin/env python3
"""
git_guard — the lock DEDICATED to git mutations. Phase 2B of ADR-0017.

WHAT IT IS
    An isolated primitive: it takes a lock, lets the transaction happen, CERTIFIES the
    real result by observation, then releases and logs. It knows no producer and
    modifies none. Producers opt in one by one — `commit_par_zone.py` is the first.

WHAT IT IS NOT
    It is not "git is governed". As long as the producers do not go through it, a correct
    lock protects nothing of what really runs at SessionEnd.

WHY NOT `maintenance.lock` (ADR-0017)
    *maintenance in progress* ≠ *git transaction in progress*. The two sometimes overlap,
    they are not identical, and a permission granted to maintenance must never
    implicitly become a git permission. The MECHANISM of `hooks/brain_guard.py` is
    reused — atomic `O_CREAT|O_EXCL` creation, an identifiable owner, zombie
    recovery; its FILE is not.

THE TTL COMES FROM A MEASUREMENT, NOT A COPY — 300 s
    `brain_guard` uses 20 minutes; copying them here would have had no justification.
    Measured on 2026-08-26 on a clone of the trunk: an `add + commit` transaction with the
    real hooks takes **2.0 to 2.7 s**. But a `push` carries `timeout=180` in the
    publishing script — so a transaction that publishes can legitimately last ~3 minutes.
    300 s covers that longest case with margin, and stays 4 times shorter than
    `brain_guard`, whose scale is that of a maintenance run, not of a git operation.

⚠️ THE TTL NEVER STEALS A LOCK. This is the most important rule in this file.
    A lock can only be recovered if its owner is PROVEN DEAD — process
    gone, or PID reused by another process. A LIVE owner keeps its
    lock whatever its age: the TTL then only raises the tone of the log
    (`old_lock_but_alive`). Stealing a live lock because it is "old"
    would replace a race with silent corruption — a slow `git push` is not
    a zombie.

THE PID IS NOT ENOUGH TO IDENTIFY AN OWNER
    A PID gets reused. `os.kill(pid, 0)` answers "alive" for a process that has
    nothing to do with the one that took the lock, and the lock would then be kept
    forever by an innocent. So the process's START TIME is recorded
    (`ps -o lstart=`): same PID + different time = the original owner is dead.
    If `ps` does not answer, nothing is concluded — we stay careful and do not recover.

NO WAY OUT — ADR-0017
    No environment variable, no `--force`, no `skip`. A way out would be
    readable and settable by the very agent it is meant to constrain, which would make
    the prohibition decorative.

IDENTITY IS MANDATORY
    `acteur` must be a non-empty string. Without it, acquisition is REFUSED and
    logged: today's defect is precisely that no log carries the identity of who
    mutated what.

Usage:
    from git_guard import transaction
    with transaction("commit_par_zone", "commit", ["lessons/x.md"]) as t:
        ...                       # t is None if the lock was not obtained
    git_guard.py state            inspect the current lock
    git_guard.py log [n]          show the last n events
"""
import contextlib
import json
import os
import subprocess
import sys
import time

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))

TTL = 300.0          # seconds — justified in the docstring, NOT a theft threshold
SONDAGE = 0.05       # polling step when a caller agrees to wait


def _chemins(depot, etat_dir=None, nom="git"):
    """(repository, lock, log). The lock may live ELSEWHERE than in the governed repository.

    WHY THIS FLEXIBILITY EXISTS — measured, not anticipated. Governing the PUBLIC repository
    meant writing `state/git.lock` into it. But its `leakcheck.py` sweeps EVERY file
    (`ROOT.rglob("*")`), does NOT honour `.gitignore`, and `state` is not in its
    `SKIP_DIRS`: the lock — which carries the caller's origin, hence a `/Users/…` path —
    would have been scanned and could have turned the check red, so BLOCKED publication.
    A safeguard that prevents the operation it protects is not one.
    So the package's lock lives in the trunk's `state/`, under a name of its own.

    AN ACCEPTED LIMIT: only an actor that knows the trunk sees that lock. In practice
    the publishing script is the only one touching the package; a `git push` typed by hand
    in the package folder would not see it. It is an exclusion between governed actors, not
    a universal exclusion."""
    d = os.path.realpath(depot or BRAIN)
    e = os.path.realpath(etat_dir) if etat_dir else os.path.join(d, "state")
    suffixe = "" if nom == "git" else "-" + nom
    return d, os.path.join(e, "git%s.lock" % suffixe), os.path.join(e, "git-journal.jsonl")


def _sh(args, cwd, timeout=60):
    """(code, output). Never raises: a git failure is data."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:                                    # pragma: no cover
        return 127, str(e)


def _demarrage(pid):
    """The process's start time, or None if it cannot be known.

    None is NOT "dead": it is "I do not know", and the caller must stay careful."""
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))],
                           capture_output=True, text=True, timeout=10)
        s = r.stdout.strip()
        return s or None
    except Exception:
        return None


def _vivant(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists, but belongs to someone else
    except Exception:
        return None          # undetermined — above all not "dead"


def _lire_verrou(lock):
    try:
        return json.load(open(lock, encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return {"_unreadable": True}


def journaliser(_depot, _evenement, _etat_dir=None, _nom="git", **champs):
    """Parameters prefixed with `_` ON PURPOSE, and it is not cosmetic.

    Without it, a caller logging a field named `depot` or `nom` triggers
    "got multiple values for argument 'depot'" — a TypeError raised BEFORE the function
    body, so before any try/except. Measured on 2026-08-27: the publisher passed
    `extra={"depot": …}`, the exception came up from `acquerir()` AFTER the lock's atomic
    write but BEFORE the `with` was entered, so with no `finally` to
    release. Result: an orphan lock, an empty log, a silent publication.

    The log must not be breakable by what it is given to write."""
    # JSONL: an appended log does not get corrupted when two actors write,
    # unlike a global JSON that is read, modified and rewritten.
    _, _, jr = _chemins(_depot, _etat_dir, _nom)
    ligne = dict(champs, event=_evenement, ts=time.time(),
                 when=time.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        os.makedirs(os.path.dirname(jr), exist_ok=True)
        with open(jr, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return ligne


def diagnostic(depot=None, etat_dir=None, nom="git"):
    """Describes the current lock WITHOUT touching it. Also returns the recoverability verdict.

    Three states only, and "old" is not one of them:
      free · held (by a live owner, young or old) · recoverable (owner proven dead)
    """
    d, lock, _ = _chemins(depot, etat_dir, nom)
    v = _lire_verrou(lock)
    if v is None:
        return {"state": "free"}
    if v.get("_unreadable"):
        # An unreadable lock can designate no owner: nobody can be harmed by its
        # recovery, and leaving it would block the repository forever.
        return {"state": "recoverable", "reason": "unreadable lock", "owner": None}

    pid, age = v.get("pid"), time.time() - float(v.get("ts") or 0)
    vivant = _vivant(pid)
    demarrage_actuel = _demarrage(pid)
    base = {"owner": v, "age_s": round(age, 1), "pid_alive": vivant,
            "ttl_s": TTL, "ttl_exceeded": age > TTL}

    if vivant is False:
        return dict(base, state="recoverable", reason="process %s gone" % pid)
    if (v.get("started") and demarrage_actuel and demarrage_actuel != v["started"]):
        return dict(base, state="recoverable",
                    reason="PID %s reused — the original owner is dead" % pid)
    if vivant is None and demarrage_actuel is None:
        # We do not know. We do not recover: a visible block is better than a theft.
        return dict(base, state="held", reason="owner undetermined — no recovery")
    if base["ttl_exceeded"]:
        # ⚠️ The only place where the TTL speaks. It does NOT grant the right to take.
        return dict(base, state="held", reason="old_lock_but_alive")
    return dict(base, state="held", reason="owner alive")


def _ecrire_atomique(lock, charge):
    """True if we created the file. O_EXCL closes the "two actors see it free" race."""
    try:
        os.makedirs(os.path.dirname(lock), exist_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, json.dumps(charge, ensure_ascii=False).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:
        return False


def acquerir(acteur, operation, perimetre=None, depot=None, sid=None, attente=0.0,
             extra=None, etat_dir=None, nom="git"):
    """Returns a token, or None if the lock was not obtained. Logs in both cases."""
    d, lock, _ = _chemins(depot, etat_dir, nom)
    if not isinstance(acteur, str) or not acteur.strip():
        # Missing identity: an EXPLICIT refusal. Never a silent attribution.
        journaliser(depot, "refused_missing_identity", etat_dir, nom, operation=operation,
                    scope=perimetre, pid=os.getpid())
        return None

    # `extra`: what the CALLER knows about itself and the primitive cannot
    # guess — its origin, the zone it handles. The core keys are never
    # overwritten: an identity is not replaced from outside.
    charge = dict(extra or {})
    charge.update({"actor": acteur.strip(), "pid": os.getpid(),
                   "started": _demarrage(os.getpid()), "sid": sid,
                   "operation": operation, "scope": perimetre, "ts": time.time(),
                   "head_before": _sh(["git", "rev-parse", "HEAD"], d)[1]})

    limite = time.time() + max(0.0, float(attente))
    while True:
        if _ecrire_atomique(lock, charge):
            try:
                journaliser(depot, "acquired", etat_dir, nom, **charge)
            except Exception as e:                 # belt AND braces
                # The lock is ALREADY taken; failing here without giving it back would leave
                # an orphan nobody asked for. We remove it and refuse
                # plainly rather than govern without a trace.
                try:
                    os.unlink(lock)
                except Exception:
                    pass
                print("git_guard: log impossible (%s) — acquisition CANCELLED" % e)
                return None
            return charge

        diag = diagnostic(depot, etat_dir, nom)
        if diag["state"] == "recoverable":
            # GOVERNED recovery: we record whom we remove, and why, BEFORE removing.
            journaliser(depot, "zombie_recovery", etat_dir, nom, actor=charge["actor"],
                        pid=charge["pid"], reason=diag.get("reason"),
                        removed_owner=diag.get("owner"))
            try:
                os.unlink(lock)
            except Exception:
                pass
            continue                       # retry the atomic creation, without forcing it

        if time.time() >= limite:
            journaliser(depot, "refused", etat_dir, nom, actor=charge["actor"], pid=charge["pid"],
                        operation=operation, scope=perimetre,
                        current_owner=diag.get("owner"),
                        reason=diag.get("reason"), lock_age_s=diag.get("age_s"))
            return None
        time.sleep(SONDAGE)


def liberer(jeton, depot=None, resultat=None, etat_dir=None, nom="git"):
    """Releases, and CERTIFIES the real result by observation — not by what the caller believes.

    ADR-0017: "A validated plan ≠ an assumed result." HEAD after, and the list of files
    really committed, are READ from the repository, never copied from the intention."""
    d, lock, _ = _chemins(depot, etat_dir, nom)
    if not jeton:
        return None
    head_apres = _sh(["git", "rev-parse", "HEAD"], d)[1]
    bouge = head_apres != jeton.get("head_before")
    fichiers = []
    if bouge and head_apres:
        fichiers = [x for x in _sh(["git", "diff-tree", "--no-commit-id", "--name-only",
                                    "-r", head_apres], d)[1].splitlines() if x]
    # We remove ONLY our own lock: otherwise releasing would commit exactly the theft
    # the TTL rule forbids.
    v = _lire_verrou(lock)
    a_nous = bool(v) and not v.get("_unreadable") and v.get("pid") == jeton.get("pid") \
        and v.get("ts") == jeton.get("ts")
    if a_nous:
        try:
            os.unlink(lock)
        except Exception:
            pass
    bilan = journaliser(depot, "released", etat_dir, nom, actor=jeton.get("actor"), pid=jeton.get("pid"),
                        operation=jeton.get("operation"), scope=jeton.get("scope"),
                        head_before=jeton.get("head_before"), head_after=head_apres,
                        head_moved=bouge, committed_files=fichiers,
                        out_of_scope=sorted(set(fichiers) - set(jeton.get("scope") or []))
                        if jeton.get("scope") else None,
                        announced_result=resultat, lock_was_ours=a_nous,
                        duration_s=round(time.time() - float(jeton.get("ts") or 0), 3))
    return bilan


@contextlib.contextmanager
def transaction(acteur, operation, perimetre=None, depot=None, sid=None, attente=0.0,
                extra=None, etat_dir=None, nom="git"):
    """`with transaction(...) as t:` — t is None if the lock was not obtained.

    The body MUST check `t`: a `with` that runs anyway would be a decorative
    lock. Release goes through `finally` — a crash of the body leaves a state
    that can be inspected in the log, never an orphan lock taken for a live one."""
    jeton = acquerir(acteur, operation, perimetre, depot, sid, attente, extra, etat_dir, nom)
    try:
        yield jeton
    finally:
        if jeton:
            liberer(jeton, depot, None, etat_dir, nom)


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "state"
    if cmd == "state":
        print(json.dumps(diagnostic(), ensure_ascii=False, indent=1))
        return 0
    if cmd == "log":
        n = int(args[1]) if len(args) > 1 else 20
        _, _, jr = _chemins(None)
        try:
            lignes = open(jr, encoding="utf-8").read().splitlines()[-n:]
        except FileNotFoundError:
            print("empty log")
            return 0
        for l in lignes:
            try:
                o = json.loads(l)
                print("%s  %-22s %-18s %s" % (o.get("when"), o.get("event"),
                                              o.get("actor"), o.get("operation") or ""))
            except Exception:
                print(l)
        return 0
    print(__doc__.strip().splitlines()[-4:][0])
    return 2


if __name__ == "__main__":
    sys.exit(main())
