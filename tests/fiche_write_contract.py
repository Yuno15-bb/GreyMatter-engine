#!/usr/bin/env python3
"""fiche_write_contract.py — what the write hook actually DOES to a note, run for real.

`hooks/on_fiche_write.py` fires on every note landing in the trunk. It has four effects and
one golden rule:

    1. a plaintext secret is masked IN THE FILE
    2. a note absent from the map is dropped into the Inbox — exactly once
    3. an unknown `metadata.type` is RECORDED (never refused)
    4. the save is logged to state/manual-saves.jsonl
    0. it never blocks: it always exits 0, whatever happens

WHY A REAL RUN AND NOT UNIT CALLS. Every one of those effects is a side effect on disk, and
three of them are wrapped in `try/except: pass` so the hook can never cost a note its save.
That is the right design and it is also perfectly silent: a broken effect looks exactly like
a working one from the outside. Only reading the trunk afterwards separates them. So the
test builds a trunk, feeds the hook the same JSON Claude Code feeds it, and reads the disk.

WHY IT ALSO RUNS TWICE. The hook fires on EVERY write, including its own follow-ups. An
Inbox that grows a line per save would bury the map under duplicates within a day.
Idempotence is part of the contract, not a nicety.

This is possible at all because the hook honours BRAIN_HOME. Pointed at the author's real
trunk it could not be tested without writing to it.

Run:
  python3 tests/fiche_write_contract.py
  python3 tests/fiche_write_contract.py --check
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOOK = os.path.join(ROOT, "hooks", "on_fiche_write.py")

SECRET = "sk-ant-AAAABBBBCCCCDDDDEEEE"

NOTE = """---
name: %s
description: a note for the contract test
metadata:
  type: %s
---

Body. A key left lying around: %s
"""


def build(trunk):
    for d in ("lessons", "state"):
        os.makedirs(os.path.join(trunk, d), exist_ok=True)
    with open(os.path.join(trunk, "MEMORY.md"), "w", encoding="utf-8") as f:
        f.write("# Map\n\n## 🆕 Inbox — notes to file (auto)\n")
    with open(os.path.join(trunk, "lessons", "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("# Index\n")


def write_note(trunk, slug, type_):
    p = os.path.join(trunk, "lessons", f"{slug}.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(NOTE % (slug, type_, SECRET))
    return p


def fire(trunk, path):
    """Feed the hook exactly what Claude Code feeds it. Returns its exit code."""
    payload = json.dumps({"tool_input": {"file_path": path}, "session_id": "s1"})
    out = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                         text=True, env=dict(os.environ, BRAIN_HOME=trunk), timeout=120)
    return out.returncode


def read(trunk, *parts):
    p = os.path.join(trunk, *parts)
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read()


def main():
    check = "--check" in sys.argv
    trouble = []

    with tempfile.TemporaryDirectory() as trunk:
        build(trunk)

        # --- a new note, unknown type, carrying a secret
        p = write_note(trunk, "fresh-note", "not-a-real-type")
        rc = fire(trunk, p)
        rc2 = fire(trunk, p)                      # fired twice: the hook runs on every write

        body = read(trunk, "lessons", "fresh-note.md")
        memory = read(trunk, "MEMORY.md")
        unknown = read(trunk, "state", "unknown-types.jsonl")
        saves = read(trunk, "state", "manual-saves.jsonl")

        # --- a note with a VALID type must NOT be reported
        q = write_note(trunk, "proper-note", "reference")
        rc3 = fire(trunk, q)
        unknown_after = read(trunk, "state", "unknown-types.jsonl")

        # --- a file OUTSIDE the trunk must be left alone
        with tempfile.TemporaryDirectory() as outside:
            o = os.path.join(outside, "stranger.md")
            with open(o, "w", encoding="utf-8") as f:
                f.write(NOTE % ("stranger", "reference", SECRET))
            rc4 = fire(trunk, o)
            untouched = SECRET in open(o, encoding="utf-8").read()

    print("Write-hook contract\n")

    def report(label, ok, detail=""):
        print(f"  {'✅' if ok else '❌'} {label}{'  — ' + detail if detail and not ok else ''}")
        if not ok:
            trouble.append(f"{label}{': ' + detail if detail else ''}")

    report("the secret is masked in the file", SECRET not in body,
           "the plaintext key is still on disk")
    report("the note is dropped into the Inbox", "fresh-note" in memory,
           "nothing was added to MEMORY.md")
    report("firing twice adds ONE Inbox line", memory.count("(lessons/fresh-note.md)") == 1,
           f"{memory.count('(lessons/fresh-note.md)')} lines: the map would fill with duplicates")
    report("the unknown type is recorded", "not-a-real-type" in unknown,
           "an unknown type passed in silence")
    report("the save is logged", "fresh-note" in saves, "manual-saves.jsonl says nothing")
    report("a VALID type is NOT reported", "proper-note" not in unknown_after,
           "a legitimate type was recorded as unknown — a guard that cries wolf")
    report("a file outside the trunk is untouched", untouched,
           "the hook rewrote a file that is not a note of this trunk")
    report("it never blocks", rc == rc2 == rc3 == rc4 == 0,
           f"exit codes {rc}, {rc2}, {rc3}, {rc4} — the golden rule is always 0")

    if trouble:
        print("\n❌ the write hook no longer does what it says:")
        for t in trouble:
            print(f"     {t}")
        print("\n   Three of these effects are wrapped in `try/except: pass` so the hook")
        print("   can never cost a note its save. A broken one is therefore SILENT.")
        return 1

    print("\n✅ all four effects happen, twice is the same as once, and it never blocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
