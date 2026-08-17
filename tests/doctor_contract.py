#!/usr/bin/env python3
"""doctor_contract.py — does the doctor actually see each thing it claims to see?

`hooks/brain_doctor.py` reports on a trunk it does not own. Every one of its checks is a
comparison between two things that were written separately, and the report is a list that
is *empty when all is well* — which is exactly the shape that can go quiet without anyone
noticing. "Nothing to report" and "I did not look" print almost the same thing.

So this test builds a HEALTHY trunk, proves the doctor is silent on it, then introduces
ONE anomaly at a time and proves that the doctor names that one and only that one.

TWO PROPERTIES BEYOND "it reports something":

  · ONE anomaly must raise ONE category. A check that fires on everything is not a
    diagnosis, it is noise, and noise gets filtered out by whoever reads it.

  · A vocabulary it cannot reach must be SAID, not skipped. Checks 8 and 9 import their
    vocabulary from the hook that owns it (on_fiche_write, graph_export) precisely so the
    doctor is not a third source of truth. The price of that choice is that an import can
    fail — and a guard that goes quiet when its reference disappears reports a clean trunk
    for ever. It must announce the skip instead.

No dependency on the real ~/.c-brain/trunk: everything runs against a temporary trunk
through BRAIN_HOME.

Run:
  python3 tests/doctor_contract.py
  python3 tests/doctor_contract.py --check
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCTOR = os.path.join(ROOT, "hooks", "brain_doctor.py")

NOTE = """---
name: %(slug)s
description: a note for the doctor contract
metadata:
  type: %(type)s
%(relations)s---

Body pointing at [[%(link)s]].
"""


def note(slug, type_="reference", relations="", link="healthy-two"):
    return NOTE % {"slug": slug, "type": type_, "relations": relations, "link": link}


def build(trunk, notes, memory_extra=""):
    """A trunk that is healthy unless the caller asks for something else."""
    os.makedirs(os.path.join(trunk, "lessons"), exist_ok=True)
    os.makedirs(os.path.join(trunk, "state"), exist_ok=True)
    lines = "".join(f"- [[{slug}]]\n" for slug in notes)
    with open(os.path.join(trunk, "MEMORY.md"), "w", encoding="utf-8") as f:
        f.write("# Map\n\n" + lines + memory_extra)
    with open(os.path.join(trunk, "lessons", "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("# Index\n")
    for slug, body in notes.items():
        with open(os.path.join(trunk, "lessons", f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(body)


def run(trunk, doctor=DOCTOR):
    subprocess.run([sys.executable, doctor, "--json", "--quiet"],
                   capture_output=True, text=True,
                   env=dict(os.environ, BRAIN_HOME=trunk), timeout=180)
    with open(os.path.join(trunk, "state", "doctor.json"), encoding="utf-8") as f:
        return json.load(f)


def doctor_without(hooks_dir, missing):
    """A copy of hooks/ with one file removed — the real 'vocabulary unreachable' path.

    Tested by copy rather than by a flag in the production code: a test-only switch is a
    branch that exists in the shipped file and is never taken by a user, which is one more
    thing that can be wrong without ever being run.
    """
    src = os.path.join(ROOT, "hooks")
    for name in os.listdir(src):
        if name.endswith(".py") and name != missing:
            with open(os.path.join(src, name), encoding="utf-8") as f:
                body = f.read()
            with open(os.path.join(hooks_dir, name), "w", encoding="utf-8") as f:
                f.write(body)
    return os.path.join(hooks_dir, "brain_doctor.py")


# Categories that are lists of findings. `engine_dirty` is excluded: it is about a second
# repository that does not exist in a fixture.
CATEGORIES = ("dead_links", "orphans", "frontmatter", "naming", "off_index",
              "memory_too_heavy", "unknown_type", "unknown_relation",
              "vocabulary_unreachable")


def healthy():
    return {
        "healthy-one": note("healthy-one", link="healthy-two"),
        "healthy-two": note("healthy-two", relations="relations:\n  based_on: [healthy-one]\n",
                            link="healthy-one"),
    }


def raised(report):
    return {k for k in CATEGORIES if report.get(k)}


def main():
    trouble = []
    results = []

    def case(label, mutate, expect, missing_hook=None):
        with tempfile.TemporaryDirectory() as trunk:
            notes = healthy()
            extra = mutate(notes) or ""
            build(trunk, notes, extra)
            if missing_hook:
                with tempfile.TemporaryDirectory() as hooks_dir:
                    report = run(trunk, doctor_without(hooks_dir, missing_hook))
            else:
                report = run(trunk)
        got = raised(report)
        ok = got == expect
        results.append((label, sorted(expect), sorted(got), ok))
        if not ok:
            trouble.append(f"{label}: expected {sorted(expect) or 'silence'}, got {sorted(got) or 'silence'}")

    case("a healthy trunk is silent", lambda n: None, set())

    def unknown_type(n):
        n["healthy-one"] = note("healthy-one", type_="not-a-type")
    case("an unknown metadata.type", unknown_type, {"unknown_type"})

    def unknown_relation(n):
        n["healthy-two"] = note("healthy-two", relations="relations:\n  illustrates: [healthy-one]\n",
                                link="healthy-one")
    case("a relation the exporter would drop", unknown_relation, {"unknown_relation"})

    def dead_link(n):
        n["healthy-one"] = note("healthy-one", link="a-note-that-does-not-exist")
    case("a dead link", dead_link, {"dead_links"})

    def bad_name(n):
        n["healthy-one"] = note("healthy-one", type_="reference")
        n["Not_Kebab"] = note("Not_Kebab", link="healthy-one")
    case("a name that is not kebab-case", bad_name, {"naming"})

    def no_frontmatter(n):
        n["healthy-one"] = "Just a body, no front matter, pointing at [[healthy-two]].\n"
    case("a note with no front matter", no_frontmatter, {"frontmatter"})

    # The point of importing the vocabularies: the import can fail, and the doctor must
    # SAY the check did not run rather than report a clean trunk.
    case("an unreachable vocabulary is announced", lambda n: None,
         {"vocabulary_unreachable"}, missing_hook="graph_export.py")

    print("Doctor contract — one anomaly at a time\n")
    for label, expect, got, ok in results:
        print(f"  {'✅' if ok else '❌'} {label}")
        if not ok:
            print(f"        expected {expect or 'silence'}")
            print(f"        got      {got or 'silence'}")

    if trouble:
        print("\n❌ the doctor does not see what it claims to see:")
        for t in trouble:
            print(f"     {t}")
        print("\n   An empty report and an absent check print the same thing.")
        return 1

    print("\n✅ silent when healthy, and each anomaly raises its own category")
    return 0


if __name__ == "__main__":
    sys.exit(main())
