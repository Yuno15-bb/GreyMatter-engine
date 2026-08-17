#!/usr/bin/env python3
"""anticipate_contract.py — does the resume list say something USEFUL, or just a lot?

`hooks/brain_anticipate.py` runs at SessionStart and INJECTS its result into the model's
context. That makes it the highest-stakes output in the engine: it is not a report someone
may read, it is four lines that arrive in every single session whether they earn their place
or not. So the question is never "does it find things" — a regex always finds things — but
"is a line that reaches the model a line worth the slot".

WHAT IT MEASURES.
  · A real resume point is found.                       (without this it is merely quiet)
  · A struck-through one is not.                        a headstone is not a task
  · A negated one is not.                               "this is no longer left to do"
  · A markdown table cell is not.                       tabular data is never a task
  · An empty trunk injects NOTHING as a hook.           an empty trunk must not add a line
    …and says so as a command.                          a display command that prints
                                                        nothing cannot be told apart from
                                                        a broken one

THE TWO HALVES MUST BE TESTED TOGETHER. A filter that over-matches "passes" by finding
nothing at all, and a mute detector reports a clean trunk for ever — which is the failure,
not the success. Every case below therefore comes in pairs: something that must be found,
and something that must not.

MEASURED, on a 492-note trunk, at the time these filters were added:
    69 detections  ->  65 after the negation filter  ->  64 after the table-cell filter
Only five detections removed in total, but TWO of the four lines actually injected changed,
because the list is ordered by recency and the noise was recent. The count is the wrong
metric; the injected block is the right one.

Run:
  python3 tests/anticipate_contract.py
  python3 tests/anticipate_contract.py --check
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ANTICIPATE = os.path.join(ROOT, "hooks", "brain_anticipate.py")

NOTES = {
    # must be found
    "real-one": "---\nname: real-one\ndescription: d\n---\n\n## LEFT TO DO\n\nwire the export.\n",
    "real-two": "---\nname: real-two\ndescription: d\n---\n\nRESUME POINT: finish the panel.\n",
    # must NOT be found
    "struck": "---\nname: struck\ndescription: d\n---\n\n## ~~PICK UP HERE~~ — ABANDONED\n",
    "negated": "---\nname: negated\ndescription: d\n---\n\nClosed: there is nothing left to do here.\n",
    "table": "---\nname: table\ndescription: d\n---\n\n| step | state |\n|---|---|\n| L | TODO |\n",
    "negated-en": "---\nname: negated-en\ndescription: d\n---\n\nDecided: this is no longer a next step.\n",
}

MUST_FIND = {"real-one", "real-two"}
MUST_NOT = {"struck", "negated", "table", "negated-en"}


def build(trunk, notes):
    os.makedirs(os.path.join(trunk, "projects"), exist_ok=True)
    for slug, body in notes.items():
        with open(os.path.join(trunk, "projects", f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(body)


def run(trunk, *args):
    out = subprocess.run([sys.executable, ANTICIPATE, *args], capture_output=True, text=True,
                         env=dict(os.environ, BRAIN_HOME=trunk), timeout=120)
    return out.returncode, out.stdout


def main():
    trouble = []
    results = []

    def report(label, ok, detail=""):
        results.append((label, ok, detail))
        if not ok:
            trouble.append(f"{label}{': ' + detail if detail else ''}")

    with tempfile.TemporaryDirectory() as trunk:
        build(trunk, NOTES)
        rc, out = run(trunk)

    found = {slug for slug in NOTES if slug in out}
    for slug in sorted(MUST_FIND):
        report(f"found: {slug}", slug in found,
               "a real resume point was lost — an over-eager filter passes by finding nothing")
    for slug in sorted(MUST_NOT):
        why = {"struck": "a struck-through marker is a headstone, not a task",
               "negated": "a negated marker means the work is CLOSED",
               "negated-en": "a negated marker means the work is CLOSED",
               "table": "a markdown table cell is data, never a task"}[slug]
        report(f"ignored: {slug}", slug not in found, why)

    # An empty trunk: silent as a hook, explicit as a command.
    with tempfile.TemporaryDirectory() as trunk:
        build(trunk, {"quiet": "---\nname: quiet\ndescription: d\n---\n\nAll settled.\n"})
        rc_hook, out_hook = run(trunk, "--hook")
        rc_cmd, out_cmd = run(trunk)

    report("an empty trunk injects nothing", out_hook.strip() == "",
           f"it would add {len(out_hook.strip().splitlines())} line(s) to every prompt")
    report("…but the command says so", "No pending resume point" in out_cmd,
           "a display command that prints nothing looks exactly like a broken one")
    report("it never blocks", rc == rc_hook == rc_cmd == 0,
           f"exit codes {rc}, {rc_hook}, {rc_cmd}")

    print("Anticipate contract — what reaches the model\n")
    for label, ok, detail in results:
        print(f"  {'✅' if ok else '❌'} {label}")
        if not ok:
            print(f"        {detail}")

    if trouble:
        print("\n❌ the resume list no longer earns its slots:")
        for t in trouble:
            print(f"     {t}")
        print("\n   These four lines arrive in EVERY session. A wrong one is not noise")
        print("   somebody can skip: it is context the model was handed as fact.")
        return 1

    print("\n✅ real points found, cancelled ones ignored, and silence when there is nothing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
