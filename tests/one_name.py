#!/usr/bin/env python3
"""
one_name.py — the product has ONE name: GreyMatter.

Until 2026-09-27 it had two. The repository, the README and the plugin page said
GreyMatter; the paths, the plugin id, the launchd jobs, the home shortcut and
most of the prose still said C Brain. A user met the first name on GitHub and the
second in their own home folder, with nothing to tell them it was the same thing.

A rename that nobody guards comes back through the newest file: the next hook
generalized from the author's Brain, the next test copied from an old one. So
this fails on ANY spelling of the old name in a tracked file.

SOME OLD NAMES ARE THE FEATURE. An install from before the rename lives at
`~/.c-brain`, runs jobs labelled `com.claudebrain.*`, and an updater from that
generation looks for migrations in `cbrain/migrations/`. The code that finds and
moves those things has to spell them. Each such line says so where it lives —
the word `pre-rename` on the line — so the reason travels with the code.

Run: python3 tests/one_name.py            (exit 1 on any unmarked old name)
     python3 tests/one_name.py --sabotage  (must exit 1: proves it can go red)
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLD = re.compile(r"c-brain|cbrain|c brain|claudebrain|c_brain|planete-c-brain", re.I)
MARK = "pre-rename"

# Whole files whose old names are history, not usage.
SKIP_FILES = {
    "CHANGELOG.md",            # generated from the annotated tags of past releases
    "tests/one_name.py",
    # Their whole job is the old name: the move itself, and its replay.
    "greymatter/migrations/002-rename-root.sh",
    "tests/update_across_rename.sh",
}
# Formats with no comment syntax: the exact deliberate lines, spelled out.
DELIBERATE = {
    # Claude Code's rename map: moves existing plugin users to the new name.
    ".claude-plugin/marketplace.json": ['"c-brain": "greymatter"'],
}
# The forwarding stubs an updater from before the rename looks for, by path.
SKIP_PREFIXES = ("cbrain/",)   # pre-rename


def offenders(files):
    out = []
    for rel in files:
        if rel in SKIP_FILES or rel.startswith(SKIP_PREFIXES):
            continue
        if OLD.search(rel):
            out.append((rel, 0, "(the file name itself)"))
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if OLD.search(line) and MARK not in line \
                    and line.strip().rstrip(",") not in DELIBERATE.get(rel, []):
                out.append((rel, n, line.strip()[:120]))
    return out


def main():
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True,
                           text=True, check=True).stdout.split("\n")
    files = [f for f in files if f]
    found = offenders(files)
    if "--sabotage" in sys.argv:
        # A real file on disk carrying the line an unguarded regression would add,
        # read by the very same scan — not a string handed to the regex.
        bait = ROOT / "tests" / ".one_name_sabotage.sh"
        bait.write_text('GM="$HOME/.c-brain"\n', encoding="utf-8")   # pre-rename
        try:
            found += offenders([str(bait.relative_to(ROOT))])
        finally:
            bait.unlink()
    for rel, n, line in found[:40]:
        print(f"  ✗ {rel}:{n}  {line}")
    if found:
        print(f"❌ {len(found)} line(s) still use the old name (mark a deliberate one `{MARK}`)")
        return 1
    print(f"✅ one name: no unmarked old name in {len(files)} tracked files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
