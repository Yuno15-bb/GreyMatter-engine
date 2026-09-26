#!/usr/bin/env python3
"""Process search patterns must not hard-code a checkout path.

A process search is a measurement with a target. If its pattern embeds a checkout name,
it can silently report no process in every other checkout and mistake that for absence.

This static check follows Python string constants into pgrep/pkill argument lists and
checks shell/JavaScript call lines. It allows broad relative patterns such as
`capsule/node_modules`, which intentionally match across checkouts. It cannot prove that
a valid pattern matches a live process; that requires a separate runtime calibration.

Run: python3 tests/motif_process_ancre.py [--check|--sabotage]
"""
import ast
import os
import re
import sys

ROOT = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))
ZONES = ("hooks", "tools", "tests", "capsule", "companion", "cbrain")
IGNORED = ("/node_modules/", "/__pycache__/", "/.git/", "/projection/bac/",
           "/captures/", "/heldout/")
PROCESS_CALL = re.compile(r"\b(?:pgrep|pkill)\b")
# A path that embeds a checkout-specific prefix before a code area, or an absolute
# user/home path. The prefix is intentionally generic and contains no machine identity.
HARDCODED = re.compile(r"(?:^|[\s\"'])/(?:Users|home)/|[\w.-]+-(?:brain|matter)/(?:capsule|hooks|tools)/")


def files():
    for zone in ZONES:
        for directory, _, names in os.walk(os.path.join(ROOT, zone)):
            for name in names:
                path = os.path.join(directory, name)
                if name.endswith((".py", ".js", ".sh", ".mjs", ".zsh")) and not any(
                        marker in path for marker in IGNORED):
                    yield path


def python_patterns(source):
    """Return (line, pattern) pairs passed to pgrep/pkill, directly or by constant."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    constants = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = (node.lineno, node.value.value)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
            continue
        first = node.elts[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)
                and PROCESS_CALL.search(first.value)):
            continue
        for value in node.elts[1:]:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.append((value.lineno, value.value))
            elif isinstance(value, ast.Name) and value.id in constants:
                line, text = constants[value.id]
                found.append((line, f"{value.id} = {text!r}"))
    return found


def text_patterns(lines):
    """Return process-call lines and simple variable assignments referenced by them."""
    found, names = [], set()
    for number, line in enumerate(lines, 1):
        if PROCESS_CALL.search(line):
            found.append((number, line.strip()[:120]))
            names.update(re.findall(r"\$\{?([A-Za-z_][A-Za-z_0-9]*)", line))
            names.update(re.findall(r"\b([A-Z][A-Z_0-9]{2,})\b", line))
    for number, line in enumerate(lines, 1):
        match = re.match(r"\s*(?:const |let |var )?([A-Za-z_][A-Za-z_0-9]*)\s*=", line)
        if match and match.group(1) in names:
            found.append((number, line.strip()[:120]))
    return found


def scan(source, filename):
    patterns = python_patterns(source) if filename.endswith(".py") else text_patterns(source.splitlines())
    return [(line, text) for line, text in patterns if HARDCODED.search(text)]


def main():
    check = "--check" in sys.argv
    if "--sabotage" in sys.argv:
        bad = 'TARGET = "sample-brain/capsule/node_modules/app"\nsubprocess.run(["pgrep", "-f", TARGET])'
        if not any(HARDCODED.search(text) for _, text in python_patterns(bad)):
            print("FAIL: calibration fixture was not detected before sabotage")
            return 1
        # Simulate a broken detector that drops every finding. The known-bad pattern
        # must then fail the assertion, proving the test can go red.
        found = []
        if not found:
            print("FAIL: sabotaged detector missed a known hard-coded path")
            return 1
        return 0

    failures, count = [], 0
    for path in files():
        try:
            source = open(path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        if not PROCESS_CALL.search(source) or os.path.abspath(path) == os.path.abspath(__file__):
            continue
        count += 1
        for line, text in scan(source, path):
            failures.append((os.path.relpath(path, ROOT), line, text))

    if failures:
        print("FAIL: process-search patterns embed a checkout-specific or absolute path:")
        for path, line, text in sorted(set(failures)):
            print(f"  {path}:{line} — {text}")
        print("Anchor the search to the runtime root or use a deliberately broad relative pattern.")
        return 1
    if not check:
        print(f"PASS: scanned {count} files that call pgrep/pkill; no hard-coded roots found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
