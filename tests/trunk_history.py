#!/usr/bin/env python3
"""trunk_history.py — does a change to your knowledge really enter a history?

THE INVARIANT:

    No protection may be silently inactive. Either the per-session save records
    what changed, or the user is told, in words, that nothing is recording it.

THE FAILURE THIS EXISTS TO PREVENT, measured on 2026-08-17 on a fresh install:

    the trunk was not a git repository;
    `hooks/commit_par_zone.py` — the per-session auto-save — began with "is this
      a repo?", printed "trunk is not a git repo — nothing to save" and returned
      0, into a log nobody reads. Its own comment called that "the normal case:
      nobody ran `git init`";
    `brain backup` — the command whose NAME promises safekeeping — answered
      `fatal: not a git repository` and exited 128.

So the shipped protection was inert for every default install, and the only
signal was a doctor line seen by whoever ran doctor and read to the end.

WHY THIS DOES NOT TEST `.git exists`. A directory proves nothing about the
promise. What is asserted is the OBSERVABLE: write a note, run the save, and the
note's CONTENT must come back out of the history with `git show`.

⚠️ HISTORY, NOT BACKUP. Everything here is local, on one disk. The package pushes
nowhere. The wording is part of the contract: a command that says "backup" over a
local-only history invites someone to lose a laptop believing otherwise.

⚠️ TRUNK GIT IS NOT ENGINE GIT. `brain update` reasons about the ENGINE repo and
must never look at this one. Asserted at the end.

Run:
  python3 tests/trunk_history.py
  python3 tests/trunk_history.py --check
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAVE = os.path.join(ROOT, "hooks", "commit_par_zone.py")
BRAIN_CLI = os.path.join(ROOT, "brain")
INSTALL = os.path.join(ROOT, "install.sh")

NOTE = """---
name: {name}
description: "a note written by the user, which must end up in the history"
metadata:
  type: lesson
---

## En clair

{body}
"""


def git(repo, *a, check=False):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr}")
    return r


def make_trunk(path, versioned):
    for d in ("lessons", "state", "hooks"):
        os.makedirs(os.path.join(path, d), exist_ok=True)
    if versioned:
        git(path, "init", "-q", check=True)
        git(path, "config", "user.email", "t@t")
        git(path, "config", "user.name", "t")
        with open(os.path.join(path, "README.md"), "w") as f:
            f.write("trunk\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "start")
    return path


def write_note(trunk, name, body="what I learned."):
    p = os.path.join(trunk, "lessons", f"{name}.md")
    with open(p, "w") as f:
        f.write(NOTE.format(name=name, body=body))
    return p


def run_save(trunk, env_extra=None):
    env = dict(os.environ, BRAIN_HOME=trunk, HOME=os.path.dirname(trunk))
    env.update(env_extra or {})
    return subprocess.run([sys.executable, SAVE], capture_output=True, text=True,
                          timeout=120, env=env, cwd=trunk)


def main():
    check = "--check" in sys.argv
    trouble = []
    print("Trunk history — a note written, a note recoverable\n")

    # ---------- 1. a versioned trunk: the note must come back OUT ----------
    with tempfile.TemporaryDirectory() as home:
        trunk = make_trunk(os.path.join(home, "trunk"), versioned=True)
        write_note(trunk, "ma-connaissance", "the sentence that must survive.")
        before = int(git(trunk, "rev-list", "--count", "HEAD").stdout or 0)
        run_save(trunk)
        after = int(git(trunk, "rev-list", "--count", "HEAD").stdout or 0)

        shown = git(trunk, "show", "HEAD:lessons/ma-connaissance.md")
        if shown.returncode:
            shown = git(trunk, "log", "--oneline", "--", "lessons/ma-connaissance.md")
            recovered = "the sentence that must survive." in git(
                trunk, "show", f"{shown.stdout.split()[0]}:lessons/ma-connaissance.md"
            ).stdout if shown.stdout.strip() else False
        else:
            recovered = "the sentence that must survive." in shown.stdout

        print(f"  versioned trunk: commits        {before} → {after}")
        print(f"  the note's CONTENT comes back   {'yes' if recovered else 'NO'}")
        if after <= before:
            trouble.append("writing a note produced no commit: the per-session save is "
                           "inert on a trunk that IS versioned")
        if not recovered:
            trouble.append("the note cannot be read back out of the history: a commit "
                           "count is not the promise — recovering the text is")

    # ---------- 2. an unversioned trunk: inert, but SAID ----------
    with tempfile.TemporaryDirectory() as home:
        trunk = make_trunk(os.path.join(home, "trunk"), versioned=False)
        write_note(trunk, "sans-historique")
        r = run_save(trunk)
        said = "not a git repo" in (r.stdout + r.stderr).lower()
        print(f"  unversioned trunk: says so      {'yes' if said else 'NO'}  (exit {r.returncode})")
        if not said:
            trouble.append("on an unversioned trunk the save records nothing and says "
                           "nothing: the user cannot tell a working history from none")
        if r.returncode != 0:
            trouble.append("the save fails hard on an unversioned trunk; it must stay "
                           "harmless — the notes are files, and nothing is lost")

    # ---------- 3. `brain backup` must explain, not print `fatal:` ----------
    with tempfile.TemporaryDirectory() as home:
        # `brain` resolves its trunk as $HOME/.c-brain/trunk and ignores BRAIN_HOME
        # (the hooks honour it; the CLI does not). The sandbox has to match that,
        # or the test would exercise a path the command never takes.
        trunk = make_trunk(os.path.join(home, ".c-brain", "trunk"), versioned=False)
        r = subprocess.run(["bash", BRAIN_CLI, "backup"], capture_output=True, text=True,
                           timeout=60, cwd=trunk, env=dict(os.environ, HOME=home))
        out = r.stdout + r.stderr
        explains = "not a git repository" in out and "git" in out and "init" in out
        raw_fatal = out.strip().startswith("fatal:")
        print(f"  `brain backup`, no history      {'explains' if explains else 'DOES NOT'}"
              f"{' (raw git fatal)' if raw_fatal else ''}")
        if raw_fatal or not explains:
            trouble.append("`brain backup` answers with a raw git error instead of saying "
                           "what is not recording and how to turn it on — from the command "
                           "whose name promises safekeeping")

    # ---------- 4. the word: history, never backup ----------
    cli = open(BRAIN_CLI, encoding="utf-8").read()
    inst = open(INSTALL, encoding="utf-8").read()
    claims_backup = "manual backup via brain" in cli
    # ⚠ NOT a search for the phrase. The first version of this check looked for
    # "local version history" anywhere in install.sh — and stayed green when the
    # init was removed, because the words survived in the FAILURE message. What is
    # asserted is the mechanism: the installer starts a repository in the TRUNK.
    says_history = 'git -C "$TRUNK" init' in inst
    print(f"  installer starts the history     {'yes' if says_history else 'NO'}")
    print(f"  commit text still says 'backup'  {'YES' if claims_backup else 'no'}")
    if claims_backup:
        trouble.append("the recorded message still calls a local history a 'backup': the "
                       "word promises off-machine safety this has never provided")
    if not says_history:
        trouble.append("the installer never states whether the history is on: silence is "
                       "exactly how a protection becomes invisibly inactive")

    # ---------- 5. trunk git is NOT engine git ----------
    upd = open(os.path.join(ROOT, "cbrain", "update.sh"), encoding="utf-8").read()
    looks_at_trunk = 'git -C "$TRUNK"' in upd or 'git -C "$CB/trunk"' in upd
    print(f"  update.sh looks at the trunk    {'YES' if looks_at_trunk else 'no'}")
    if looks_at_trunk:
        trouble.append("update.sh runs git against the TRUNK: the engine's ownership gate "
                       "must never reason about the user's notes")

    if trouble:
        print("\n❌ a protection is inactive without saying so:")
        for t in trouble:
            print(f"     {t}")
        return 1

    print("\n✅ a written note is recoverable from the history, and its absence is stated")
    if not check:
        print("   (local history on this disk — not a backup, and never called one)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
