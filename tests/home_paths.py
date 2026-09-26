#!/usr/bin/env python3
"""Reject machine-specific home paths in distributed code and examples."""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]

# Each allowed root has a product or migration reason. Narrower checks for
# Desktop and the Finder shortcut follow below.
ALLOWED = {
    ".c-brain": "product engine, trunk, state, and runtime",
    ".c-brain-a1": "isolated work directory for the A1 test",
    ".claude": "Claude Code integration and test surfaces",
    ".claude.json": "Claude Code's own installation metadata",
    ".local": "user-level command installation",
    ".zshrc": "shell PATH setup example",
    "Library": "macOS LaunchAgents and application cache",
    "claude-brain": "legacy trunk migration and maintainer source",
    "other-trunk": "temporary occupied-surface test fixture",
    "Desktop": "product launcher and generic import examples",
    "C": "Finder shortcut named C Brain",
}
PATH = re.compile(r'(?:~|\$HOME|\$\{HOME\})/([A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*)'
                  r'|os\.path\.join\(HOME,\s*["\']([^"\']+)')
EXTENSIONS = {".py", ".sh", ".js", ".cjs", ".html", ".json", ".yml", ".yaml", ".template"}


def allowed(value, line):
    root = value.split("/", 1)[0]
    if root not in ALLOWED:
        return False
    if root == "Desktop":
        return (value == "Desktop" or value.startswith("Desktop/Planete-C-Brain.command")
                or value.startswith("Desktop/chatgpt-export.zip")
                or (value == "Desktop/C" and "Desktop/C Brain Planet.app" in line))
    if root == "C":
        return "C Brain" in line
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--override", nargs=2, metavar=("TRACKED_PATH", "COPY"),
                        help="check a disposable changed copy in place of a tracked file")
    args = parser.parse_args()
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    problems = []
    checked = 0
    for name in tracked:
        path = Path(name)
        if name == "README.md" or name.startswith("docs/") or path.suffix not in EXTENSIONS:
            continue
        source = Path(args.override[1]) if args.override and name == args.override[0] else ROOT / name
        try:
            content = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        checked += 1
        for number, line in enumerate(content.splitlines(), 1):
            for match in PATH.finditer(line):
                value = match.group(1) or match.group(2)
                if not allowed(value, line):
                    problems.append(f"{name}:{number}: ~/{value}")
    if problems:
        print("Unapproved personal home paths:")
        print("\n".join(problems))
        return 1
    print(f"{checked} tracked code files: home paths allowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
