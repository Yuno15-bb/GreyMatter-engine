#!/usr/bin/env python3
"""Check that GMTR style sheets retain balanced comments and rule blocks."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent / "gmtr"


def analyse(text):
    extra_closers, opener, depth, i, line = [], None, 0, 0, 1
    state, quote = "plain", ""
    while i < len(text):
        char = text[i]
        if char == "\n":
            line += 1
            if state == "string":
                state = "plain"
            i += 1
            continue
        if state == "comment":
            if text[i:i + 2] == "*/":
                state, opener, i = "plain", None, i + 2
                continue
        elif state == "string":
            if char == "\\":
                i += 2
                continue
            if char == quote:
                state = "plain"
        elif text[i:i + 2] == "/*":
            state, opener, i = "comment", line, i + 2
            continue
        elif text[i:i + 2] == "*/":
            extra_closers.append(line)
            i += 2
            continue
        elif char in "\"'":
            state, quote = "string", char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        i += 1
    return extra_closers, opener if state == "comment" else None, depth


def main():
    failures = []
    sheets = sorted(ROOT.rglob("*.css"))
    for path in sheets:
        closers, opener, depth = analyse(path.read_text(encoding="utf-8"))
        failures.extend(f"{path.relative_to(ROOT)}:{n}: unmatched comment closer" for n in closers)
        if opener:
            failures.append(f"{path.relative_to(ROOT)}:{opener}: unclosed comment")
        if depth:
            failures.append(f"{path.relative_to(ROOT)}: unmatched rule braces ({depth})")
    if not sheets:
        failures.append("No GMTR style sheets found")
    if failures:
        print("RED — " + "\nRED — ".join(failures))
        return 1
    print(f"PASS — {len(sheets)} GMTR style sheets have balanced comments and braces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
