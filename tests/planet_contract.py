#!/usr/bin/env python3
"""planet_contract.py — does the Planet actually understand what graph_export writes?

THE INVARIANT:

    Every node field the viewer READS is a field the exporter WRITES.

THE FAILURE THIS EXISTS TO PREVENT. `hooks/graph_export.py` and `planet/index.html` are a
producer and a consumer that never call each other: one writes `planet/graph.json`, the
other fetches it. Nothing links them but field names. Read a field nobody writes and
JavaScript hands you `undefined` — no error, no crash, no log. The panel simply renders
one section less, for ever, and the map looks fine.

It is not hypothetical. Measured on 2026-08-16, before this test existed: the viewer read
`n.en_clair` at six sites and the exporter produced it NOWHERE. The whole "En clair"
register — the plain-language half of every note — was invisible in the public map, and
nothing had reported it since the day it was introduced.

WHY A REAL EXPORT AND NOT A HAND-WRITTEN FIXTURE. A fixture of what we BELIEVE the exporter
produces would pass while the exporter produced something else; it would test our belief,
not the code. So the test builds a small trunk, runs the real exporter over it, and reads
the real file back.

WHY IT ALSO CHECKS A VALUE AND NOT ONLY A KEY. A field can be present and always null,
which is the same blindness one level down: the viewer would still render nothing. So at
least one node must carry a real `en_clair`, and the hover contract — the viewer takes
`en_clair.split('\\n\\n')[0]` — must yield the first paragraph and nothing more.

Run:
  python3 tests/planet_contract.py
  python3 tests/planet_contract.py --check
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXPORTER = os.path.join(ROOT, "hooks", "graph_export.py")
VIEWER = os.path.join(ROOT, "planet", "index.html")

# The viewer reads a node through TWO names, `n` and `nd`. Matching only `n.` was this
# test's own blind spot: `nd.embed2` and `nd.regle` were invisible to it, and one of the
# two turned out to be read and never written — the very defect this file exists to catch.
# The accessor list is deliberately CLOSED: `d.` and `f.` are unrelated locals in this
# viewer (`d.push`, `f.ids`), and matching them would turn the guard into noise.
NODE_ACCESSORS = ("n", "nd")
FIELD = re.compile(r"\b(?:%s)\.([a-z_][a-z_0-9]*)\b" % "|".join(NODE_ACCESSORS))

# Read by the viewer but produced elsewhere than per-node, or provided by the layout code
# itself. Listed with a reason rather than silently skipped.
NOT_FROM_THE_EXPORTER = {
    "x", "y", "z",          # positions, computed by the layout at runtime
    "length",               # array access, not a node field
}

NOTE_WITH = """---
name: with-en-clair
description: a note that carries the plain-language register
metadata:
  type: lesson
relations:
  based_on: [without-en-clair]
---

## En clair

The first paragraph, the one the hover must show.

The second paragraph, which must NOT reach the hover.

## Technical detail

Dense body, outside the register. See [[without-en-clair]].
"""

NOTE_WITHOUT = """---
name: without-en-clair
description: a note with no register, for the fallback path
metadata:
  type: lesson
---

# Title

Direct body, no register here. Links to [[with-en-clair]].
"""


NOTE_UNKNOWN_REL = """---
name: unknown-relation
description: a note whose relation type this exporter does not know
metadata:
  type: lesson
relations:
  base_sur: [with-en-clair]
---

Body. The convention keeps the link in the text: [[with-en-clair]].
"""

# The case that keeps a future check honest: one KNOWN and one UNKNOWN type in the SAME
# note. The known one must stay qualified. A guard that answered "this note is invalid"
# would take the good relation down with the bad one.
NOTE_MIXED_REL = """---
name: mixed-relations
description: a note carrying one known and one unknown relation type
metadata:
  type: lesson
relations:
  based_on: [with-en-clair]
  illustre: [without-en-clair]
---

Body linking [[with-en-clair]] and [[without-en-clair]].
"""

# `base_sur` in one note, `illustre` in the other. Counted per TYPE LINE, which is what
# `brain_doctor` lists too — the two must not drift apart.
EXPECTED_UNKNOWN = 2


def export_into(trunk):
    """Build a small trunk, run the REAL exporter over it, return the graph it wrote."""
    for d in ("lessons", "planet", "state", "meta"):
        os.makedirs(os.path.join(trunk, d), exist_ok=True)
    for name, body in (("with-en-clair.md", NOTE_WITH), ("without-en-clair.md", NOTE_WITHOUT),
                       ("unknown-relation.md", NOTE_UNKNOWN_REL),
                       ("mixed-relations.md", NOTE_MIXED_REL)):
        with open(os.path.join(trunk, "lessons", name), "w", encoding="utf-8") as f:
            f.write(body)

    out = subprocess.run([sys.executable, EXPORTER], capture_output=True, text=True,
                         env=dict(os.environ, BRAIN_HOME=trunk), timeout=180)
    if out.returncode != 0:
        raise SystemExit(f"the exporter failed:\n{out.stderr}")
    with open(os.path.join(trunk, "planet", "graph.json"), encoding="utf-8") as f:
        return json.load(f)


def fields_read_by_the_viewer():
    with open(VIEWER, encoding="utf-8") as f:
        return sorted(set(FIELD.findall(f.read())) - NOT_FROM_THE_EXPORTER)


def main():
    check = "--check" in sys.argv

    with tempfile.TemporaryDirectory() as trunk:
        graph = export_into(trunk)

    nodes = graph["nodes"]
    written = set().union(*(set(n) for n in nodes)) if nodes else set()
    read = fields_read_by_the_viewer()

    print(f"Planet contract — {len(nodes)} nodes exported, "
          f"{len(read)} fields read by the viewer\n")

    trouble = []
    missing = [f for f in read if f not in written]
    for f in read:
        mark = "✅" if f in written else "❌ read, never written"
        print(f"  n.{f:18} {mark}")
    if missing:
        trouble.append("the viewer reads " + ", ".join(f"n.{f}" for f in missing) +
                       " — the exporter never writes " +
                       ("it" if len(missing) == 1 else "them"))

    # A key that is always null is the same blindness one level down.
    with_register = [n for n in nodes if n.get("en_clair")]
    print(f"\n  notes carrying a register  {len(with_register)} of {len(nodes)}")
    if not with_register:
        trouble.append("en_clair is present on every node but null on all of them: "
                       "the viewer would still render nothing")
    else:
        # The hover contract, evaluated exactly as the viewer evaluates it.
        hover = with_register[0]["en_clair"].split("\n\n")[0]
        print(f"  hover would show           {hover[:60]!r}")
        if "second paragraph" in hover:
            trouble.append("the hover shows more than the first paragraph: "
                           "en_clair is not paragraph-separated as the viewer expects")
        if "first paragraph" not in hover:
            trouble.append(f"the hover does not show the register's first paragraph: {hover[:80]!r}")

    # The fallback the viewer relies on must stay reachable.
    without = [n for n in nodes if n["id"] == "without-en-clair"]
    if without and without[0].get("en_clair") is not None:
        trouble.append("a note with no register must expose en_clair = null, so the "
                       "viewer falls back on desc")

    # A TYPED relation qualifies an existing edge rather than adding one. The fixture
    # declares `relations: based_on:` alongside the [[link]] the convention requires,
    # so exactly one edge must come out carrying that type. This is not a new feature —
    # it is the non-regression half: an exporter change must not drop it on the way.
    typed = [e for e in graph["links"] if e.get("type")]
    print(f"  typed edges surviving      {len(typed)} of {len(graph['links'])}")
    if not any(e.get("type") == "based_on" for e in typed):
        trouble.append("the typed relation declared in the frontmatter did not survive "
                       "the export: the edge came out untyped")

    # ---------- THE LOSS THE EXPORTER USED TO SWALLOW ----------
    # An unrecognized relation type costs the QUALIFICATION, never the edge. Before this,
    # it cost it in total silence: no error, no log, no trace in graph.json. Two halves are
    # checked separately on purpose — the exporter PRODUCING the signal, and the viewer
    # RENDERING it. Either one alone leaves the loss invisible to a human.
    def edge(a, b):
        for e in graph["links"]:
            if {e["source"], e["target"]} == {a, b}:
                return e
        return None

    counted = graph["counts"].get("unknown_relations")
    print(f"\n  unknown relation types     {counted} (expected {EXPECTED_UNKNOWN})")
    if counted is None:
        trouble.append("graph.json carries no `counts.unknown_relations`: a dropped "
                       "relation type leaves no trace at all in the exported file")
    elif counted != EXPECTED_UNKNOWN:
        trouble.append(f"the exporter counted {counted} unknown relation types where the "
                       f"fixture declares {EXPECTED_UNKNOWN} (`base_sur`, `illustre`): "
                       "the loss is being under- or over-reported")

    # The mixed note: the good relation must not go down with the bad one.
    keep, lost = edge("mixed-relations", "with-en-clair"), edge("mixed-relations", "without-en-clair")
    print(f"  mixed note: known edge     {keep and keep.get('type')!r}")
    print(f"  mixed note: unknown edge   {'present, untyped' if lost and not lost.get('type') else lost!r}")
    if not keep or keep.get("type") != "based_on":
        trouble.append("in a note mixing a known and an unknown relation type, the KNOWN "
                       "one lost its qualification: the unknown type must never "
                       "invalidate its neighbours")
    if not lost:
        trouble.append("the edge carrying the unknown relation type disappeared: an "
                       "unrecognized type must cost the qualification, never the link")
    elif lost.get("type"):
        trouble.append(f"an unrecognized relation type came out qualified as "
                       f"{lost['type']!r}: the exporter invented a vocabulary")

    # The viewer half. `counts.*` is not a node field, so the accessor scan above cannot
    # see it: without this, deleting the warning would keep the whole contract green.
    with open(VIEWER, encoding="utf-8") as f:
        viewer_src = f.read()
    shows = "counts.unknown_relations" in viewer_src
    print(f"  viewer renders the warning {'yes' if shows else 'NO'}")
    if not shows:
        trouble.append("the viewer never reads `counts.unknown_relations`: the exporter "
                       "counts the loss and nothing puts it in front of a human")

    if trouble:
        print("\n❌ the Planet and the exporter no longer agree:")
        for t in trouble:
            print(f"     {t}")
        print("\n   A field read and never written is `undefined` in JavaScript: no error,")
        print("   no crash, one section silently missing from every panel.")
        return 1

    print("\n✅ every field the viewer reads is a field the exporter writes")
    if not check:
        print("   (and the register reaches the hover as one paragraph)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
