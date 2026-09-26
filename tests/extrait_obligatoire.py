#!/usr/bin/env python3
"""E1: a newly added sourced note must quote an exact excerpt.

The pre-commit gate reads Git's index, so each case runs in its own temporary
repository. An unknown origin and an already committed note are exempt.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "provenance_fiches.py")
EXCERPT = "The PDF reader kept the previous rendering."
WITH_EXCERPT = """---
title: The PDF reader cache retained the previous version
description: "Rewriting a PDF at the same path can show stale content."
topic: machine-and-process
provenance:
  kind: internal_experience
  ref: "sessions/archive/2026-09-18-trial.md"
  captured_at: 2026-09-18
  extrait: "The PDF reader kept the previous rendering."
authority:
  validated: false
  scope: repository
  confidence: medium
---

A reader may display the previous PDF after a rewrite at the same path.

## Remedy

Change the filename on each render or clear the reader cache.
"""
UNKNOWN = """---
title: An observation with an unknown origin
description: "An older observation without a retained source."
topic: machine-and-process
provenance:
  kind: unknown
---

The note body is irrelevant to this bench.
"""


def clean_env(**extra):
    """Drop Git hook variables that could redirect commands to the caller's index."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(extra)
    return env


def write(root, rel, content):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as note:
        note.write(content)


def repository():
    root = tempfile.mkdtemp(prefix="excerpt-bench-")
    for subdir in ("projects/base", "lessons", "meta", "state"):
        os.makedirs(os.path.join(root, subdir), exist_ok=True)
    write(root, "lessons/old-note.md", WITH_EXCERPT.replace(
        f'  extrait: "{EXCERPT}"\n', ""))
    for command in (("git", "init", "-q"),
                    ("git", "config", "user.email", "bench@local"),
                    ("git", "config", "user.name", "Bench"),
                    ("git", "add", "-A"),
                    ("git", "commit", "-q", "-m", "existing note")):
        result = subprocess.run(command, cwd=root, env=clean_env(), capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    return root


def stage(root, content):
    rel = "lessons/new-note.md"
    write(root, rel, content)
    result = subprocess.run(["git", "add", rel], cwd=root, env=clean_env(),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def verdict(root, gate=GATE):
    result = subprocess.run([sys.executable, gate, "--check", "--nouvelles"],
                            cwd=root, env=clean_env(BRAIN_HOME=root),
                            capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


CASES = (
    ("new note with excerpt", WITH_EXCERPT, False),
    ("new note without excerpt", WITH_EXCERPT.replace(f'  extrait: "{EXCERPT}"\n', ""), True),
    ("empty excerpt", WITH_EXCERPT.replace(f'"{EXCERPT}"', '""'), True),
    ("whitespace excerpt", WITH_EXCERPT.replace(f'"{EXCERPT}"', '"   "'), True),
    ("unknown origin", UNKNOWN, False),
    ("existing note without excerpt", None, False),
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--sabotage", action="store_true",
                        help="Invert the expected outcome of the missing-excerpt case")
    args = parser.parse_args()
    failures = []
    print(f"E1 excerpt gate — {len(CASES)} cases")
    for label, content, expect_red in CASES:
        root = repository()
        try:
            gate = GATE
            if args.sabotage:
                gate_dir = os.path.join(root, "test-gate")
                os.makedirs(gate_dir)
                shutil.copy(os.path.join(HERE, "provenance_invariants.py"), gate_dir)
                source = open(GATE, encoding="utf-8").read()
                before = 'and not str(prov.get("extrait") or "").strip()):'
                assert before in source, "sabotage target has changed"
                gate = os.path.join(gate_dir, "provenance_fiches.py")
                with open(gate, "w", encoding="utf-8") as script:
                    script.write(source.replace(before, 'and False):'))
            initial, output = verdict(root, gate)
            if initial:
                failures.append(f"{label}: baseline failed: {output[-200:]}")
                continue
            if content is not None:
                stage(root, content)
            code, output = verdict(root, gate)
            passed = (bool(code) == expect_red and (not expect_red or "E1" in output))
            print(("  PASS " if passed else "  FAIL ") + label)
            if not passed:
                failures.append(f"{label}: exit={code}, E1={'E1' in output}")
        finally:
            shutil.rmtree(root, ignore_errors=True)
    print(f"{len(CASES) - len(failures)}/{len(CASES)} cases conform")
    for failure in failures:
        print("  " + failure)
    return 1 if args.check and failures else 0


if __name__ == "__main__":
    sys.exit(main())
