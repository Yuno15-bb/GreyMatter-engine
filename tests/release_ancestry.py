#!/usr/bin/env python3
"""
release_ancestry.py — the latest release must be inside the development branch.

v2.1.1 was cut from a side branch and never merged back. Its three commits —
among them "ask before updating" — were missing from main for a day while main
kept shipping commits, the README already promised the new behaviour, and every
job stayed green. A v2.2 tagged from that main would have gone back to
installing updates without asking, and nothing would have said so. An external
audit found it, not a test.

The rule this holds: a published release is always an ancestor of the next
development. The newest English release tag (`vX.Y.Z`, compared in version
order, the same family `update.sh` installs from) must be reachable from HEAD.
A patch release cut elsewhere turns this red on main until it is merged back.

A check that cannot see the tags must not pass: no tag visible is a failure,
because a shallow checkout would otherwise make this green for ever.

Run:      python3 tests/release_ancestry.py
Sabotage: python3 tests/release_ancestry.py --sabotage   (must exit 1)
          — pretends the latest release is a commit outside HEAD's history.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True)


def latest_release():
    tags = [t for t in git("tag", "-l", "v*").stdout.split() if RELEASE.match(t)]
    if not tags:
        return None
    return max(tags, key=lambda t: tuple(int(n) for n in RELEASE.match(t).groups()))


def main():
    # Version order, not alphabetical: v2.10.0 is newer than v2.9.0.
    assert max(["v2.9.0", "v2.10.0"],
               key=lambda t: tuple(int(n) for n in RELEASE.match(t).groups())) == "v2.10.0"

    tag = latest_release()
    if tag is None:
        print("❌ no release tag visible — a shallow checkout? (fetch-depth: 0)")
        return 1
    commit = git("rev-list", "-n1", tag).stdout.strip()

    if "--sabotage" in sys.argv:
        # A commit with HEAD's tree and no parent: in no branch's history.
        tree = git("rev-parse", "HEAD^{tree}").stdout.strip()
        commit = subprocess.run(["git", "-C", str(ROOT), "commit-tree", tree, "-m", "sabotage"],
                                capture_output=True, text=True,
                                env={"GIT_AUTHOR_NAME": "s", "GIT_AUTHOR_EMAIL": "s@s",
                                     "GIT_COMMITTER_NAME": "s", "GIT_COMMITTER_EMAIL": "s@s",
                                     "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
                                ).stdout.strip()
        tag = f"{tag} (sabotaged)"

    if git("merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
        missing = git("rev-list", "--count", f"HEAD..{commit}").stdout.strip()
        print(f"❌ the latest release {tag} is not in this branch's history "
              f"({missing} of its commits are missing) — merge it back: "
              f"git merge {tag.split()[0]}")
        return 1
    print(f"✅ the latest release {tag} is an ancestor of HEAD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
