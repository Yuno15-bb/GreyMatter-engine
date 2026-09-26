#!/usr/bin/env python3
"""Every explicit script invoked by release entry points must be tracked."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ROOT_VAR = r'"?\$\{?(?:SRC|SELF|ENGINE|TRUNK|CLAUDE_PLUGIN_ROOT)\}?"?/'
PREFIX = re.compile(rf'^(?:{ROOT_VAR}|\./)?')
SCRIPT = re.compile(rf'(?<![\w./-])(?:{ROOT_VAR}|\./)?'
                    r'(?:[\w.-]+/)*[\w.-]+\.(?:py|sh|js)\b')
COMMAND = re.compile(r'\b(?:python3?|bash|node)\b')


def inputs(selftest):
    paths = [selftest, ROOT / "brain", ROOT / "install.sh", ROOT / "hooks/hooks.json"]
    paths.extend((ROOT / "cbrain").glob("*.sh"))
    paths.extend((ROOT / ".github/workflows").glob("*.yml"))
    return paths


def script_paths(path):
    if path.name == "hooks.json":
        json.loads(path.read_text(encoding="utf-8"))
        # JSON's nested command strings are searched below as plain text.
        text = path.read_text(encoding="utf-8")
    else:
        text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        # A path inside an explanatory trailing comment is not an invocation.
        line = re.split(r'\s+#\s', line, maxsplit=1)[0]
        command = COMMAND.search(line)
        if not command:
            continue
        rest = re.split(r'&&|\|\||;', line[command.end():], maxsplit=1)[0]
        for match in SCRIPT.finditer(rest):
            name = PREFIX.sub("", match.group())
            if name.startswith(("tests/", "hooks/", "cbrain/", "companion/", "capsule/", "planet/")) or "/" not in name:
                yield number, name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", type=Path, default=ROOT / "hooks/selftest.sh",
                        help="override the selftest source for a disposable sabotage")
    args = parser.parse_args()
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines())
    missing = []
    count = 0
    for path in inputs(args.selftest):
        references = list(script_paths(path))
        if path == ROOT / "brain" and not references:
            missing.append("brain: no script references parsed")
        for line, name in references:
            count += 1
            if name not in tracked:
                missing.append(f"{path.name}:{line}: {name}")
    if missing:
        print("Missing invoked files from the tracked tree:")
        print("\n".join(sorted(set(missing))))
        return 1
    print(f"{count} script references resolve to tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
