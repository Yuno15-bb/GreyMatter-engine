#!/usr/bin/env python3
"""A generated project dashboard is excluded regardless of path casing.

The ordinary note is a negative control. A temporary copy of the hook restores
literal comparison to prove that the test catches the original fault.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
FAILURES = []
NOTE = "---\nname: %s\n---\n\n# RESUME POINT: something to finish\n"


def check(label, passed, detail=""):
    print(("  PASS " if passed else "  FAIL ") + label + ("  -- " + detail if detail else ""))
    if not passed:
        FAILURES.append(label)


def trunk(dashboard):
    root = os.path.realpath(tempfile.mkdtemp(prefix="dashboard-case."))
    os.makedirs(os.path.join(root, "projects"))
    for name in (dashboard, "ordinary-note.md"):
        open(os.path.join(root, "projects", name), "w").write(NOTE % name[:-3])
    open(os.path.join(root, "MEMORY.md"), "w").write(NOTE % "memory")
    for args in (("init", "-q"), ("add", "-A")):
        subprocess.run(["git", "-C", root, *args], capture_output=True)
    subprocess.run(["git", "-C", root, "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "trunk"], capture_output=True)
    return root


def collect(root, hooks=HOOKS):
    code = textwrap.dedent("""
        import json, sys
        sys.path.insert(0, %r)
        import brain_anticipate as ba
        print(json.dumps([item["path"] for item in ba.collect()]))
    """) % hooks
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env=dict(os.environ, BRAIN_HOME=root))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def case(dashboard, hooks=HOOKS):
    root = trunk(dashboard)
    try:
        return collect(root, hooks)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    print("== case-insensitive dashboard exclusion ==")
    for name in ("PROJECT-STATUS.md", "project-status.md", "Project-Status.md"):
        found = case(name)
        check(f"{name} excluded", not any("project-status" in p.lower() for p in found),
              str(found))
    found = case("PROJECT-STATUS.md")
    check("ordinary note remains a candidate", "projects/ordinary-note.md" in found,
          str(found))
    check("MEMORY.md is excluded", not any(p.lower() == "memory.md" for p in found))

    temporary = tempfile.mkdtemp(prefix="dashboard-sabotage.")
    try:
        hooks = os.path.join(temporary, "hooks")
        shutil.copytree(HOOKS, hooks)
        path = os.path.join(hooks, "brain_anticipate.py")
        source = open(path, encoding="utf-8").read()
        before = 'if rel.lower() in EXCLUS_TOUJOURS \\'
        assert before in source, "sabotage target has changed"
        source = source.replace(before,
                                'if rel in ("MEMORY.md", "projects/PROJECT-STATUS.md") \\')
        open(path, "w", encoding="utf-8").write(source)
        found = case("project-status.md", hooks)
        check("literal-comparison sabotage exposes lowercase dashboard",
              any("project-status" in p.lower() for p in found), str(found))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print("PASS" if not FAILURES else f"FAIL: {len(FAILURES)} case(s)")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
