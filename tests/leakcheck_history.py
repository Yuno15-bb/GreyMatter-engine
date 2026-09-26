#!/usr/bin/env python3
"""Published history is ignored, while every later or unknown leak is blocked."""

import importlib.util
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("leakcheck", ROOT / "leakcheck.py")
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def check():
    assert len(lc.ALREADY_PUBLIC) == 2, "Public tip list changed"
    compiled = [(label, re.compile(pattern)) for label, pattern in lc.MARKERS]
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        git(root, "init", "-q")
        git(root, "config", "user.name", "Fixture Author")
        git(root, "config", "user.email", "fixture" + "@example.invalid")
        path = root / "sample.txt"
        # Assemble the marker at runtime so this file stays safe to scan.
        first = "sk-" + "ant-" + "A" * 20
        second = "sk-" + "ant-" + "B" * 20
        path.write_text(first + "\n")
        git(root, "add", "sample.txt")
        git(root, "commit", "-qm", "published fixture")
        tip_a = git(root, "rev-parse", "HEAD")

        leaks, _, excluded = lc.scan_history(root, compiled, (tip_a,))
        assert not leaks and excluded == 1, "Published commit was scanned"

        leaks, _, excluded = lc.scan_history(root, compiled, ())
        assert excluded == 0 and leaks, "Removing the public tip hid history"

        unknown = "0" * 40
        leaks, _, excluded = lc.scan_history(root, compiled, (unknown,))
        assert excluded == 0 and leaks, "Unknown public tip hid history"

        path.write_text(first + "\n" + second + "\n")
        git(root, "commit", "-qam", "later fixture")
        leaks, _, excluded = lc.scan_history(root, compiled, (tip_a,))
        assert excluded == 1 and any(label == "Anthropic key" for _, label, _ in leaks), \
            "New leak passed after published tip"

    # The release shape: a commit on top of a public tip that takes a leak OUT.
    # Removing a published value discloses nothing and must stay green.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        git(root, "init", "-q")
        git(root, "config", "user.name", "Fixture Author")
        git(root, "config", "user.email", "fixture" + "@example.invalid")
        path = root / "sample.txt"
        leak = "sk-" + "ant-" + "C" * 20
        path.write_text("kept\n" + leak + "\n")
        git(root, "add", "sample.txt")
        git(root, "commit", "-qm", "published fixture")
        tip = git(root, "rev-parse", "HEAD")
        path.write_text("kept\n")
        git(root, "commit", "-qam", "remove the published value")
        leaks, _, excluded = lc.scan_history(root, compiled, (tip,))
        assert excluded == 1 and not leaks, "Removing a public value was reported as a leak"

        # Added then removed after the public tip: the adding commit is unpublished,
        # so it is still caught even though the final tree is clean.
        path.write_text("kept\n" + leak + "\n")
        git(root, "commit", "-qam", "unpublished leak")
        path.write_text("kept\n")
        git(root, "commit", "-qam", "unpublished removal")
        leaks, _, _ = lc.scan_history(root, compiled, (tip,))
        assert any(label == "Anthropic key" for _, label, _ in leaks), \
            "A leak added and removed after the public tip passed"



if __name__ == "__main__":
    check()
    print("History leak check passed.")
