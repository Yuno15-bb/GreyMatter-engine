#!/usr/bin/env python3
"""commit_par_zone — saves the trunk into git, ONE ZONE PER COMMIT.

Called at the end of every session by auto_maintain, after the agents have run.
Purely mechanical: no LLM, no network, nothing that leaves the machine.

WHY NOT `git add -A`
    That is what the automatic save did until 2026-08-13, and it is what drowned
    19 files of work in progress in commit e61fd01 (2026-08-03): a catch-all
    commit tells several stories at once and its message can only tell one.
    612 commits of that kind sleep in the author's own history.
    Here each zone goes into its own commit, with its own message — work in
    progress stays identifiable instead of being buried.

UNDER LOCK SINCE 2026-08-26 (ADR-0017 phase 3)
    Each zone is a `git_guard` transaction: dedicated lock `state/git.lock`, attributable
    identity, log, scope carried by the command (`git commit -- <zone>`). If the
    lock is held, the zone is POSTPONED — never forced. If `git_guard` cannot be found,
    this script commits nothing at all: there is no fallback to direct git.

WHAT IT DOES NOT DO
    It does not PUSH. A trunk holds personal notes; sending them to a remote is
    its owner's decision, not the side effect of a session ending. (The author
    pushes their own from `tools/sync_depots.py`, which is not part of the package.)

Usage:
  commit_par_zone.py             commits
  commit_par_zone.py --dry-run   says what it would do, writes nothing
"""
import os, sys, subprocess

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))

# ── THE PRIMITIVE IS MANDATORY — ADR-0017 phase 3 ───────────────────────────
# If `git_guard` cannot be found, this producer DOES NOT COMMIT. There is no fallback
# to a direct git call: a fallback would turn the safeguard's failure into a silent
# return to the behaviour that corrupted the index on 2026-08-25. A missing commit
# is visible and recoverable; an ungoverned commit is not.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import git_guard
    _GUARD_INDISPO = None
except Exception as _e:                                        # pragma: no cover
    git_guard = None
    _GUARD_INDISPO = "%s: %s" % (type(_e).__name__, _e)

# How long to wait before giving up on a zone. 60 s: above a local transaction
# (2.0–2.7 s measured) so as not to skip a zone at the first contention, below
# the 300 s TTL so as never to confuse "someone is working" with "dead lock".
ATTENTE = 60.0

# ⚠️ THIS TABLE IS A COPY of the pre-commit hook's, despite what the original comment
# claimed here ("we use ITS table, not a copy"). It always was one: the hook is shell,
# this module is Python. A declaration does not make a copy unique.
# As long as both exist, tests/zones_de_commit.py goes red as soon as they drift apart.
ZONES = (("hooks/", "engine"), ("tests/", "engine"), ("companion/", "engine"),
         ("cbrain/", "engine"), ("capsule/", "engine"),
         ("projects/", "knowledge"), ("lessons/", "knowledge"), ("meta/", "knowledge"),
         ("life/", "knowledge"), ("agents/", "knowledge"), ("skills/", "knowledge"),
         ("sessions/", "archives"))
LABEL = {"engine": "engine: hooks, tests and capsule",
         "knowledge": "knowledge: notes, lessons and maps",
         "archives": "archives: sessions and logs",
         "root": "root: entry maps, audits and tooling"}
ORDER = ("archives", "knowledge", "root", "engine")


def _artefacts_du_garde(cwd):
    """Relative paths of the files git_guard writes into the repository.

    WHY THIS EXCLUSION EXISTS. It was found by the bench, not by rereading:
    `state/` is ignored in the author's trunk, but NOTHING guarantees it elsewhere, and
    without this barrier a repository lacking the ignore rule would commit `state/git.lock`
    WHILE IT IS HELD — a live lock frozen into history. The primitive must
    never be capturable by the producer it governs."""
    if git_guard is None:
        return set()
    _, lock, journal = git_guard._chemins(cwd)
    racine = os.path.realpath(cwd)
    return {os.path.relpath(x, racine) for x in (lock, journal)}


def _origine():
    """Where does this call come from? The parent process's name, read from the system.

    ADR-0017 requires an attributable identity, and "unknown" is not one when
    the caller CAN be known. `auto_maintain` launches this script through a shell: the
    parent therefore says at least by which path we got here. No caller is changed for
    this — the producer finds out about itself."""
    try:
        r = subprocess.run(["ps", "-o", "command=", "-p", str(os.getppid())],
                           capture_output=True, text=True, timeout=5)
        return (r.stdout.strip() or None)
    except Exception:
        return None


def zone(f):
    for prefix, z in ZONES:
        if f.startswith(prefix):
            return z
    return "root"


def sh(cmd, cwd, timeout=180):
    """Returns (code, output). Never raises: this script must not break anything."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except Exception as e:
        return 1, str(e)


def changed(cwd):
    # `-uall`: one line per untracked FILE. Without it, an untracked folder comes back as a
    # single `state/` line, `_artefacts_du_garde` (which compares files) cannot recognise
    # it, and the "root" zone commits `state/git.lock` WHILE IT IS HELD. Observed on
    # 2026-09-25 on a throwaway repository with no ignore rule — which is exactly what
    # install.sh creates.
    _, out = sh(["git", "status", "--porcelain", "-uall"], cwd)
    return [l[3:].strip().strip('"') for l in out.splitlines() if l.strip()]


def commit_by_zone(cwd, msg_prefix="auto: ", dry=False, sid=None):
    """One commit per zone, under the git_guard lock. Returns the number of commits made.

    BOTH `git reset` CALLS WERE REMOVED (2026-08-26, ADR-0017 phase 3). They were not
    dropped for comfort: their role was examined, measured, and replaced.

      · the reset at the START of the loop was a precondition for "commit the index": it
        emptied the index so that `git add -- <zone>` then `git commit` took only
        that zone. That role is now held by `git commit -- <zone>`, which bounds the
        commit by the COMMAND and not by a shared state a third party can change between
        the check and the use. Measured: S4 contaminates 10/10 without pathspec, 0/10 with.
      · the FINAL reset was hygiene: leaving the index clean. It is useless — the
        commit consumes our own staging — and it is HARMFUL.

    WHY HARMFUL, AND IT IS NOT THEORETICAL. A global `git reset` destroys
    EVERYONE's staging. Measured on 2026-08-26 in a throwaway repository: a file
    staged by a third party SURVIVES `git commit -- <my plan>` and is DESTROYED by
    `git reset`. And at the time of writing, the trunk happened to carry two
    files staged by an agent — the old code would have wiped them.

    WHAT IS STILL NEEDED: the `git add`. Measured too — `git commit -- <new file>`
    fails with "pathspec did not match any file(s) known to git" as long as the file
    is not known to git. The add bounds nothing, it makes committable; the pathspec
    is what bounds.
    """
    if git_guard is None:
        print(f"    ⛔ git_guard unavailable ({_GUARD_INDISPO}) — NO commit.")
        print("       No fallback to direct git: ADR-0017 explicitly forbids it.")
        return 0

    origine = _origine()
    exclus = _artefacts_du_garde(cwd)
    sid = sid or os.environ.get("CLAUDE_CODE_SESSION_ID")
    made = 0
    for z in ORDER:
        sel = [f for f in changed(cwd) if zone(f) == z and f not in exclus]
        if not sel:
            continue
        if dry:
            # Pure read: no mutation, so no lock. Taking the lock for
            # a simulation would take it away from an actor that does have work to do.
            print(f"    [dry] {z:9} {len(sel):4d} file(s)")
            made += 1
            continue

        with git_guard.transaction("commit_par_zone", f"commit-zone:{z}", sel, depot=cwd,
                                   sid=sid, attente=ATTENTE,
                                   extra={"origin": origine, "zone": z}) as jeton:
            if jeton:
                # THE PLAN IS RECOMPUTED UNDER THE LOCK. The `sel` above only served to
                # decide whether the lock was worth asking for; between that glance
                # and the acquisition, an agent may have written. Committing the list from BEFORE
                # would be exactly the check-then-use this job exists to remove.
                # The token carries the REAL plan, otherwise the log would certify a scope
                # that is not the commit's.
                sel = [f for f in changed(cwd) if zone(f) == z and f not in exclus]
                jeton["scope"] = sel
                if not sel:
                    continue
            if not jeton:
                # Refused: another actor holds git. We SAY so, we do not work around it.
                d = git_guard.diagnostic(cwd)
                p = (d.get("owner") or {}).get("actor", "?")
                print(f"    ⏸  {z:9} lock held by \"{p}\" — zone postponed, nothing forced")
                continue

            code, _ = sh(["git", "add", "--"] + sel, cwd)
            if code:
                continue
            # No "Co-Authored-By" line here: this commit is made in its owner's
            # repository by their own machine. Pasting an e-mail address into it —
            # public or not — both dirties their history and turns leakcheck red,
            # which hunts addresses in EVERYTHING that ships in the package.
            msg = (f"{msg_prefix}{LABEL[z]}\n\n"
                   f"Automatic commit, one zone at a time ({len(sel)} file(s)).\n"
                   f"One zone per commit: work in progress stays identifiable in the "
                   f"history instead of being buried by a `git add -A`.\n")
            # Author "C Brain": a commit made by the machine must not carry the
            # human's signature.
            # `-- ` + sel: THE SCOPE IS CARRIED BY THE COMMAND. Even if the index
            # changed under our feet, this commit can only contain `sel`.
            r = subprocess.run(["git", "-c", "user.name=C Brain",
                                "-c", "user.email=brain@local",
                                "commit", "-q", "-F", "-", "--"] + sel, cwd=cwd,
                               input=msg, text=True, capture_output=True)
            if r.returncode == 0:
                print(f"    ✅ {z:9} {len(sel):4d} file(s)")
                made += 1
            else:
                # the trunk's pre-commit hook may refuse: we SAY so, we do not insist.
                # WE SHOW THE END, NOT THE START — fixed on 2026-09-19. This refusal
                # showed the first 120 characters, that is the "✅ 15 benches
                # green" the hook prints BEFORE returning. The message therefore said
                # exactly the opposite of what was happening, and the real error
                # — "error: Error building trees" — stayed invisible. The commit had to be
                # replayed by hand to see it.
                lignes = [l for l in (r.stdout + r.stderr).strip().splitlines()
                          if l.strip() and not l.startswith("✅")]
                print(f"    ⚠️  {z:9} refused:")
                for l in lignes[-6:]:
                    print(f"         {l.strip()[:150]}")
                # We undo OUR staging, and only ours. A global `git reset` would make
                # one zone's failure destructive for a third party's work.
                sh(["git", "restore", "--staged", "--"] + sel, cwd)
    return made


# GRAPH REGENERATION NO LONGER LIVES HERE (2026-08-20, job B5).
# It lived in this function for half a day, long enough to understand that it
# covered only one path there: a manual `git commit` left
# `planet/graph.json` on the previous HEAD, and the invariant refused the next
# commit. Two producers for the same operation would have regenerated twice per
# commit. The trigger therefore now lives in `tools/git-hooks/post-commit`,
# also installed as `post-merge` — where ALL writers pass, automatic
# as well as manual. `hooks/graph_export.py` remains, as before, the single definition.
def main():
    dry = "--dry-run" in sys.argv
    code, _ = sh(["git", "rev-parse", "--git-dir"], BRAIN)
    if code:
        print("  trunk is not a git repo — nothing to save")   # the normal case: nobody ran `git init`
        return 0
    n = len(changed(BRAIN))
    if not n:
        print("  nothing to commit")
        return 0
    print(f"  {n} file(s) changed")
    commit_by_zone(BRAIN, dry=dry)
    # Nothing to regenerate here: every commit made above triggered the repository's
    # `post-commit` hook, which takes care of it — and which also covers the manual
    # commit this script never sees.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"commit_par_zone: {e}")
        sys.exit(0)                              # NEVER breaks its caller
