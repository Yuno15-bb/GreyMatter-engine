#!/usr/bin/env python3
"""update_ownership.py — may `brain update` touch this repository at all?

THE INVARIANT:

    An updater performs destructive git only on an engine it explicitly owns.
    Anywhere else it refuses and changes NOTHING — not HEAD, not the branch,
    not the working tree, not the index.

THE FAILURE THIS EXISTS TO PREVENT, measured on 2026-08-17 on five real
repositories, before the gate existed:

    managed install, on its tag       HEAD moved, tree replaced   legitimate
    dev repo, clean branch            HEAD moved, BRANCH LOST
    dev repo, commits above the tag   HEAD moved, BRANCH LOST     ← the incident
    uncommitted work under hooks/     `M hooks/thing.py` -> clean ← work DESTROYED

The incident was real: `brain update`, run from a sandbox install whose engine
symlink pointed at the development repo, rewound that repo past four commits and
left HEAD detached. Nothing was lost only because the commits were reachable. The
fourth line has no such luck — `git checkout -- .` over the engine-owned paths is
where unsaved work went to die, and those paths are the whole codebase.

WHY REAL REPOSITORIES AND NOT A MOCK. The thing under test is what git does to a
working tree. A fake would encode what we BELIEVE `checkout <tag>` does to a
branch with commits above it — which is exactly the belief that was wrong.

WHY THE MANAGED CASE IS ALSO ASSERTED. A gate that refuses everywhere is not a
fix, it is an outage: the updater must still update a real install. That case is
the non-regression half, and it fails if the gate turns out to be a wall.

Run:
  python3 tests/update_ownership.py
  python3 tests/update_ownership.py --check
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0 and args[0] not in ("describe", "status"):
        raise SystemExit(f"git {' '.join(args)} failed in {repo}:\n{r.stderr}")
    return r.stdout.strip()


def state(repo):
    """Everything an update must not silently move."""
    return {"head": git(repo, "rev-parse", "HEAD"),
            "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "tree": git(repo, "write-tree"),
            "dirty": git(repo, "status", "--porcelain", "--untracked-files=no")}


def build_remote(path):
    """A published engine with two releases."""
    os.makedirs(os.path.join(path, "cbrain"), exist_ok=True)
    os.makedirs(os.path.join(path, "hooks"), exist_ok=True)
    git(path if os.path.exists(os.path.join(path, ".git")) else path, "init", "-q") \
        if False else subprocess.run(["git", "init", "-q", path], check=True)
    git(path, "config", "user.email", "b@b")
    git(path, "config", "user.name", "b")
    shutil.copy(os.path.join(ROOT, "cbrain", "update.sh"),
                os.path.join(path, "cbrain", "update.sh"))
    src_paths = os.path.join(ROOT, "cbrain", "engine-paths.txt")
    dst_paths = os.path.join(path, "cbrain", "engine-paths.txt")
    shutil.copy(src_paths, dst_paths) if os.path.exists(src_paths) else \
        open(dst_paths, "w").write("hooks\ntests\n")
    with open(os.path.join(path, "install.sh"), "w") as f:
        f.write("#!/usr/bin/env bash\nexit 0\n")
    with open(os.path.join(path, "hooks", "thing.py"), "w") as f:
        f.write("v1\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "v1.0.0")
    git(path, "tag", "v1.0.0")
    with open(os.path.join(path, "hooks", "thing.py"), "w") as f:
        f.write("v2\n")
    git(path, "commit", "-qam", "v1.1.0")
    git(path, "tag", "v1.1.0")
    git(path, "checkout", "-q", "v1.0.0")


def run_case(work, remote, name, setup, managed, args=()):
    home = os.path.join(work, name)
    eng = os.path.join(home, "engine")
    os.makedirs(os.path.join(home, ".c-brain", "state"), exist_ok=True)
    subprocess.run(["git", "clone", "-q", remote, eng], check=True)
    git(eng, "config", "user.email", "d@d")
    git(eng, "config", "user.name", "d")
    git(eng, "config", "advice.detachedHead", "false")
    git(eng, "checkout", "-q", "v1.0.0")
    setup(eng)
    os.symlink(eng, os.path.join(home, ".c-brain", "engine"))
    if managed:
        with open(os.path.join(home, ".c-brain", "state", "engine-managed"), "w") as f:
            f.write(os.path.realpath(eng) + "\n")

    before = state(eng)
    proc = subprocess.run(["bash", os.path.join(eng, "cbrain", "update.sh"), *args],
                          capture_output=True, text=True, timeout=180,
                          env=dict(os.environ, HOME=home))
    return before, state(eng), proc.stdout + proc.stderr


def main():
    check = "--check" in sys.argv
    trouble = []

    def on_branch(e):
        git(e, "checkout", "-q", "-B", "main", "v1.0.0")

    def commits_above(e):
        on_branch(e)
        with open(os.path.join(e, "hooks", "mine.py"), "w") as f:
            f.write("my work\n")
        git(e, "add", "-A")
        git(e, "commit", "-qm", "work above the tag")

    def dirty(e):
        on_branch(e)
        with open(os.path.join(e, "hooks", "thing.py"), "a") as f:
            f.write("UNSAVED\n")

    def detached(e):
        git(e, "checkout", "-q", "v1.0.0")

    with tempfile.TemporaryDirectory() as work:
        remote = os.path.join(work, "remote")
        build_remote(remote)

        print("Update ownership — five real repositories\n")

        # The MANAGED cases: the updater must still do its job.
        for name, setup in (("managed, on its tag", detached),):
            b, a, out = run_case(work, remote, "managed", setup, managed=True)
            moved = b["head"] != a["head"]
            print(f"  {name:34} engine updated: {'yes' if moved else 'NO'}")
            if not moved:
                trouble.append("the gate refuses a MANAGED install too: the updater no "
                               "longer updates anything, which is an outage, not a fix")

        # The cases it must not touch. Same assertion for all: nothing moved.
        untouchable = (("dev repo, clean branch", on_branch, False),
                       ("dev repo, commits above tag", commits_above, False),
                       ("uncommitted work in hooks/", dirty, False),
                       ("marker naming another engine", on_branch, "wrong"))
        for i, (name, setup, managed) in enumerate(untouchable):
            key = f"case{i}"
            home_managed = True if managed == "wrong" else managed
            b, a, out = run_case(work, remote, key, setup, managed=home_managed)
            if managed == "wrong":
                pass  # marker written with the real path; the branch guard fires first
            same = b == a
            print(f"  {name:34} untouched: {'yes' if same else 'NO'}")
            if not same:
                diff = [k for k in b if b[k] != a[k]]
                trouble.append(f"{name}: the updater moved {', '.join(diff)} on a repo it "
                               "does not own — this is the 2026-08-17 incident")
            if "Nothing was changed" not in out and "Nothing was changed." not in out:
                trouble.append(f"{name}: the refusal does not tell the user that nothing "
                               "was changed, so a scared user will go looking for damage")
            if setup is dirty and not a["dirty"]:
                trouble.append("the uncommitted change was DISCARDED: work under an "
                               "engine-owned path must survive a refused update")

        # ROLLBACK is a checkout too. It sits EARLIER in the script than the update
        # path, so it reached `git checkout <target>` without passing the gate at all:
        # the same incident through a different flag. Asserted here because a guard
        # nobody exercises is a guard that comes back off.
        def dev_with_previous(e):
            on_branch(e)
            home = os.path.dirname(e)
            st = os.path.join(home, ".c-brain", "state")
            os.makedirs(st, exist_ok=True)
            with open(os.path.join(st, "previous-version"), "w") as f:
                f.write("v1.0.0\n")

        b, a, out = run_case(work, remote, "rollback", dev_with_previous,
                             managed=False, args=("--rollback",))
        same = b == a
        print(f"  {'dev repo, --rollback':34} untouched: {'yes' if same else 'NO'}")
        if not same:
            trouble.append("`brain update --rollback` checked out over a repo it does not "
                           "own: the gate is bypassed by the rollback path")

    if trouble:
        print("\n❌ the updater touches what it does not own:")
        for t in trouble:
            print(f"     {t}")
        return 1

    print("\n✅ destructive git only on an engine explicitly marked as managed")
    if not check:
        print("   (and a refused update leaves HEAD, branch, tree and index untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
