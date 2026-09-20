#!/usr/bin/env python3
"""review_contract.py — does the global audit say WHICH measurement it is printing?

`hooks/brain_review.py` prints one sentence at the top of the report:

    726 notes woven · 2968 links · 1 component(s) · topology measured on <date>

Two different programs can supply that first number, and they do not count the same
thing. brain_topology counts NOTES WOVEN INTO THE GRAPH — five zones, frontmatter with
a `name:`, README and structural maps excluded. brain_doctor counts MARKDOWN FILES IN
THE REPOSITORY — twelve zones, skills/ and tools/ included. On the author's trunk on
2026-09-20 that was 726 against 946, a gap of 220.

Until that day `build()` read `topo.get("n_notes", doctor.get("notes"))`. It looks like
an ordinary default. It is a silent substitution of one measurement for another under
one word, and the rest of the sentence did not even have a fallback, so hiding
topology.json produced:

    945 notes · None links · None component(s) · topology measured on None

A number that changed meaning, and three `None` offered to a human as measurements.

THE PROPERTY, and it is the one tests/doctor_contract.py states for the doctor:
"nothing to report" and "I did not look" must not print the same way. Here: when the
topology has not been measured, the report must SAY so, must not print a count of notes
at all, and must never print the word None.

No dependency on the real trunk: everything runs against a temporary BRAIN_HOME.

Run:
  python3 tests/review_contract.py
  python3 tests/review_contract.py --check   # verdict only, for CI
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOPOLOGY = {"generated_at": "2026-09-20T01:47:26", "n_notes": 726, "n_links": 2968,
            "n_components": 1, "missing_links": [], "isolated": [], "odd_placement": [],
            "components": [], "faiblement_liees": []}
DOCTOR = {"notes": 946, "dead_links": [], "orphans": [], "off_index": [],
          "memory_bytes": 19974}


def render(with_topology):
    """Runs the REAL build() + to_markdown() on a throwaway trunk. Never writes to it."""
    with tempfile.TemporaryDirectory() as trunk:
        os.makedirs(os.path.join(trunk, "state"))
        if with_topology:
            with open(os.path.join(trunk, "state", "topology.json"), "w") as f:
                json.dump(TOPOLOGY, f)
        with open(os.path.join(trunk, "state", "doctor.json"), "w") as f:
            json.dump(DOCTOR, f)
        code = ("import sys, os; sys.path.insert(0, os.path.join(%r, 'hooks'));"
                "import brain_review as R; print(R.to_markdown(R.build()))" % ROOT)
        env = dict(os.environ, BRAIN_HOME=trunk)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            return "CRASHED: " + r.stderr.strip().splitlines()[-1]
        return r.stdout


def main():
    fails = []
    quiet = "--check" in sys.argv

    def check(label, ok, seen):
        if not quiet or not ok:
            print(("  ✅ " if ok else "  ❌ ") + label)
        if not ok:
            print(f"        seen: {seen}")
            fails.append(label)

    if not quiet:
        print("── A. the topology HAS been measured ──")
    out = render(True)
    head = next((l for l in out.splitlines() if "·" in l), "")
    check("the count of woven notes is printed, and named as woven",
          "726 notes woven" in head, head)
    check("links and components come from the same measurement",
          "2968 links" in head and "1 component(s)" in head, head)
    check("the doctor's different number is NOT the one shown",
          "946" not in head, head)

    if not quiet:
        print("\n── B. the topology has NOT been measured ──")
    out = render(False)
    check("the report says it did not look", "Topology not measured" in out, out[:120])
    check("no count of notes is printed at all",
          "notes woven" not in out and "946 notes" not in out and "945 notes" not in out,
          next((l for l in out.splitlines() if "notes" in l), "(no line with 'notes')"))
    check("the word None is never offered as a measurement", "None" not in out,
          next((l for l in out.splitlines() if "None" in l), ""))
    check("the doctor's count may appear, but only under its own meaning",
          ("946" not in out) or ("markdown files in the" in out),
          next((l for l in out.splitlines() if "946" in l), "(946 absent)"))

    if not quiet:
        print()
    if fails:
        print(f"❌ review_contract — {len(fails)} property(ies) broken")
        return 1
    print("✅ review_contract — the report names the measurement it prints, "
          "and says so when it has none.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
