#!/usr/bin/env python3
"""Resume ranking follows Git commit dates and a stable path tie-break.

All notes and repositories are synthetic. File mtimes are deliberately changed
without changing content; a later real commit must move its note to first place.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
TOP = 4
FAILURES = []


def command(*args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


def check(label, condition, detail=""):
    print(("  PASS " if condition else "  FAIL ") + label + ("  -- " + detail if detail else ""))
    if not condition:
        FAILURES.append(label)


def seed(parent):
    root = os.path.join(parent, "seed")
    os.makedirs(os.path.join(root, "projects"))
    os.makedirs(os.path.join(root, "planet"))
    with open(os.path.join(root, ".gitignore"), "w") as ignored:
        ignored.write("planet/graph.json\n")
    for index in range(4):
        name = f"project-{index}.md"
        with open(os.path.join(root, "projects", name), "w") as note:
            note.write(f"---\nname: project-{index}\ndescription: synthetic project\n---\n\n"
                       f"# RESUME POINT: complete task {index}\n")
    result = command("git", "init", "-q", root)
    assert result.returncode == 0, result.stderr
    command("git", "-C", root, "add", "-A")
    commit(root, "initial candidates", "2026-01-01T00:00:00+00:00")
    return root


def clone(root, destination):
    result = command("git", "clone", "-q", "--no-hardlinks", root, destination)
    assert result.returncode == 0, result.stderr
    os.makedirs(os.path.join(destination, "planet"), exist_ok=True)
    return destination


def commit(root, message, date):
    command("git", "-C", root, "add", "-A")
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    result = command("git", "-C", root, "-c", "user.email=bench@local",
                     "-c", "user.name=Bench", "commit", "-qm", message, env=env)
    assert result.returncode == 0, result.stderr
    return command("git", "-C", root, "rev-parse", "HEAD").stdout.strip()


def top(root, by_mtime=False):
    code = textwrap.dedent("""
        import json, sys
        sys.path.insert(0, %r)
        import brain_anticipate as hook
        items = hook.collect()
        if %r:
            items.sort(key=lambda item: item["mtime"], reverse=True)
        print(json.dumps([item["path"] for item in items[:%d]]))
    """) % (HOOKS, by_mtime, TOP)
    result = command(sys.executable, "-c", code,
                     env=dict(os.environ, BRAIN_HOME=root))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def export(root):
    result = command(sys.executable, os.path.join(HOOKS, "graph_export.py"),
                     env=dict(os.environ, BRAIN_HOME=root))
    assert result.returncode == 0, result.stderr
    with open(os.path.join(root, "planet", "graph.json")) as source:
        return json.load(source)


def badge(graph):
    return sorted(node["file"] for node in graph["nodes"] if node.get("resume"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sabotage", action="store_true", help="Rank by mtime again")
    args = parser.parse_args()
    temporary = tempfile.mkdtemp(prefix="resume-rank-")
    try:
        origin = seed(temporary)
        a = clone(origin, os.path.join(temporary, "A"))
        b = clone(origin, os.path.join(temporary, "B"))
        graph = export(a)

        now = time.time()
        for index, filename in enumerate(sorted(os.listdir(os.path.join(b, "projects")))):
            path = os.path.join(b, "projects", filename)
            os.utime(path, (now - index, now - index))
        check("mtime edits preserve Git content",
              not command("git", "-C", b, "status", "--porcelain").stdout.strip())
        rank = (lambda root: top(root, True)) if args.sabotage else top
        check("same HEAD gives same ranked candidates", rank(a) == rank(b),
              f"A={rank(a)}, B={rank(b)}")
        check("old mtime ranking diverges under this perturbation", top(a, True) != top(b, True))

        before = top(a)
        for filename in os.listdir(os.path.join(a, "projects")):
            path = os.path.join(a, "projects", filename)
            data = open(path, "rb").read()
            with open(path, "wb") as note:
                note.write(data)
            os.utime(path, None)
        check("same-content maintenance keeps Git clean",
              not command("git", "-C", a, "status", "--porcelain").stdout.strip())
        check("same-content maintenance keeps ranking", rank(a) == before)
        graph = export(a)
        check("graph badges agree with candidates at same HEAD", badge(graph) == sorted(top(a)))

        target = top(a)[-1]
        with open(os.path.join(a, target), "a") as note:
            note.write("\n<!-- substantive update -->\n")
        old_head = command("git", "-C", a, "rev-parse", "HEAD").stdout.strip()
        new_head = commit(a, "update candidate", "2026-01-02T00:00:00+00:00")
        check("the update created a new HEAD", old_head != new_head)
        check("committed candidate moves to rank zero", rank(a)[0] == target)
        graph = export(a)
        check("regenerated graph badges match candidates", badge(graph) == sorted(top(a)))
        c = clone(origin, os.path.join(temporary, "C"))
        d = clone(origin, os.path.join(temporary, "D"))
        check("two fresh clones have the same ranking", top(c) == top(d))
        print("PASS" if not FAILURES else "FAIL: " + ", ".join(FAILURES))
        return 0 if not FAILURES else 1
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
