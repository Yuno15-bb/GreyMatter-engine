#!/usr/bin/env python3
"""planet_semantic_honesty.py — the map may not claim a meaning it does not have.

WHY IT EXISTS. The Planet OPENS on the semantic view: that is the author's choice, and a good
one — the globe says which folder a note sits in, the semantic cloud says what resembles what.
But the embeddings that place that cloud are OPTIONAL BY DESIGN (docs/design-doc.md: "Neither
the cold corpus nor the embeddings venv: optional, BM25 is enough by default"), and the
installer lays down neither venv nor pip. So the ordinary state of a fresh installation is: no
vectors at all.

Measured 2026-08-19 and re-measured ON THE RENDERED SCREEN 2026-09-19, with Chrome headless
over the shipped package: 0 notes of 10 carried a vector, 0 of 36 in an installed trunk — and
the landing screen read "✦ MEANING IN VOLUME — proximity = meaning, every note". Every point
sat at its STRUCTURAL position, through a fallback written for "a note that has no vector yet"
and applied to 100% of them. No error, no log line: the recompute was invoked with `|| true`.

WHAT IS MEASURED. Not an exit code. Two things a reader can see:
  1. the exporter RECORDS what it measured — `graph.json` carries `semantic.state` / `covered`
     / `total`, counted on the NOTES and not on the size of the cache (a cache of stale keys
     places nobody and must not read as full health);
  2. the sentence the viewer will display, produced by `planet/semantic-label.js` and compared
     here as a STRING, under node — so the four states are checkable everywhere, including in
     CI where no browser is installed.

THE ONE INVARIANT, above all the others: the words "MEANING IN VOLUME" and "every note" may
appear only when every note really is placed by meaning.

Run:  python3 tests/planet_semantic_honesty.py
      python3 tests/planet_semantic_honesty.py --sabotage label-frozen-on-meaning
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SABOTAGES = ("label-frozen-on-meaning", "coverage-counted-on-the-cache", "old-graph-assumed-ready")

NOTE = """---
name: {name}
description: a note for the semantic honesty bench
metadata:
  type: lesson
---

Body of {name}.
"""

ok = True


def verdict(cond, label, seen=""):
    global ok
    print(f"  {'✅' if cond else '❌'} {label}" + (f"   → {seen}" if not cond and seen else ""))
    if not cond:
        ok = False


def build_trunk(trunk, n_notes, cache):
    """cache: None = no file · "corrupt" = present and unreadable · dict = rel_path -> [x,y,z]"""
    for d in ("lessons", "planet", "state", "meta"):
        os.makedirs(os.path.join(trunk, d), exist_ok=True)
    for i in range(n_notes):
        with open(os.path.join(trunk, "lessons", f"note-{i}.md"), "w", encoding="utf-8") as f:
            f.write(NOTE.format(name=f"note-{i}"))
    path = os.path.join(trunk, "state", "embed2.json")
    if cache is None:
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json at all" if cache == "corrupt" else json.dumps({"pos": cache}))


def export(src, trunk):
    out = subprocess.run([sys.executable, os.path.join(src, "hooks", "graph_export.py")],
                         capture_output=True, text=True,
                         env=dict(os.environ, BRAIN_HOME=trunk), timeout=180)
    if out.returncode != 0:
        raise SystemExit(f"the exporter failed:\n{out.stderr}")
    with open(os.path.join(trunk, "planet", "graph.json"), encoding="utf-8") as f:
        return json.load(f)


def label(src, payload):
    """The sentence the viewer will show, read from the real module under node."""
    js = ("import { capaciteSemantique, etiquetteSens, etiquette3d } from %s;"
          "const d = %s; const c = capaciteSemantique(d);"
          "console.log(JSON.stringify({cap:c, ...etiquetteSens(c), trois_d: etiquette3d(c, null)}));"
          % (json.dumps(os.path.join(src, "planet", "semantic-label.js")), json.dumps(payload)))
    out = subprocess.run(["node", "--input-type=module", "-e", js],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise SystemExit(f"semantic-label.js could not be read by node:\n{out.stderr}")
    return json.loads(out.stdout)


def sabotage(src, name):
    """Break one mechanism on the COPY, on purpose. A patch that matches nothing is a bench
    that certifies its own reddening, so a missing pattern stops everything right here."""
    def patch(rel, old, new):
        p = os.path.join(src, rel)
        s = open(p, encoding="utf-8").read()
        if s.count(old) != 1:
            raise SystemExit(f"SABOTAGE {name}: pattern found {s.count(old)}× in {rel}, expected 1")
        open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))

    if name == "label-frozen-on-meaning":
        # The defect itself: the nominal wording, whatever the state.
        patch("planet/semantic-label.js",
              "    default:   // 'absent' et tout état inconnu",
              "    default:\n      return { titre: '[ TRUNK MAP — MEANING ]',\n"
              "               bandeau: '✦ MEANING IN VOLUME — proximity = meaning, every note · S structure' };\n"
              "    case '_never':   // SABOTAGE")
    elif name == "coverage-counted-on-the-cache":
        # A stale cache reads as full health: count its keys instead of the placed notes.
        patch("hooks/graph_export.py",
              'sem_covered = sum(1 for n in nodes.values() if n.get("embed2"))',
              'sem_covered = len(embed2)  # SABOTAGE')
    elif name == "old-graph-assumed-ready":
        # A graph.json from before the declaration is taken for healthy.
        patch("planet/semantic-label.js",
              "    state: couverts === 0 ? 'absent' : couverts === noeuds.length ? 'ready' : 'partial',",
              "    state: 'ready',  // SABOTAGE")
    else:
        raise SystemExit(f"unknown sabotage: {name}\nknown: {', '.join(SABOTAGES)}")


def main():
    saboteur = None
    if "--sabotage" in sys.argv:
        saboteur = sys.argv[sys.argv.index("--sabotage") + 1]

    lab = tempfile.mkdtemp(prefix="planet-semantic.")
    src = os.path.join(lab, "src")
    try:
        # The bench always works on a COPY: a sabotage must never be able to touch the repo.
        files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                               capture_output=True, timeout=60).stdout.split(b"\0")
        for rel in (f.decode() for f in files if f):
            s, d = os.path.join(ROOT, rel), os.path.join(src, rel)
            if os.path.exists(s):
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
        if saboteur:
            sabotage(src, saboteur)
            print(f"⚠️  sabotage active: {saboteur}\n")

        print("Planet — the map may not claim a meaning it does not have\n")

        # ── 1. the four states, measured by the REAL exporter ─────────────────────────
        vec = [0.1, 0.2, 0.3]
        cases = [
            # name          notes  cache                                     state      covered
            ("no module",     4,   None,                                     "absent",  0),
            ("unreadable",    4,   "corrupt",                                "broken",  0),
            ("stale cache",   4,   {"lessons/gone.md": vec},                 "broken",  0),
            ("mid-indexing",  4,   {f"lessons/note-{i}.md": vec for i in (0, 1)}, "partial", 2),
            ("every note",    4,   {f"lessons/note-{i}.md": vec for i in range(4)}, "ready", 4),
        ]
        recorded = {}
        for label_, n, cache, want_state, want_cov in cases:
            trunk = tempfile.mkdtemp(prefix="trunk.", dir=lab)
            build_trunk(trunk, n, cache)
            g = export(src, trunk)
            sem = g.get("semantic", {})
            recorded[want_state if want_state != "broken" else label_] = sem
            verdict(sem.get("state") == want_state,
                    f"{label_:14} → state = {want_state}", f"state = {sem.get('state')!r}")
            verdict(sem.get("covered") == want_cov and sem.get("total") == n,
                    f"{label_:14} → {want_cov} of {n} notes placed by meaning",
                    f"covered={sem.get('covered')} total={sem.get('total')}")
            if want_state != "ready":
                verdict(bool(sem.get("detail")), f"{label_:14} → says WHY in one sentence")

        print()
        # ── 2. the sentence the reader will see, for each of those states ─────────────
        CLAIM = ("MEANING IN VOLUME", "every note")
        for state, sem in recorded.items():
            r = label(src, {"semantic": sem, "nodes": []})
            claims = any(c in r["bandeau"] for c in CLAIM)
            shown = f"{r['titre']} / {r['bandeau']}"
            if sem.get("state") == "ready":
                verdict(claims, "ready          → the banner DOES say the meaning is there", shown)
                verdict("S for meaning" in r["trois_d"],
                        "ready          → and the globe invites to it", r["trois_d"])
            elif sem.get("state") == "partial":
                # PARTIAL IS NOT "NO MEANING": some notes really are placed by it. The title may
                # say the word — but never bare, always carrying the count that bounds the claim.
                verdict(not claims, f"{state:14} → the banner does NOT claim ALL notes", shown)
                verdict("— MEANING ]" not in r["titre"] and "/" in r["titre"],
                        f"{state:14} → the title says meaning ONLY with its count", r["titre"])
                verdict("S for meaning" in r["trois_d"],
                        f"{state:14} → the globe may still invite to it", r["trois_d"])
            else:
                verdict(not claims, f"{state:14} → the banner does NOT claim meaning", shown)
                # ⚠️ « le titre ne contient pas MEANING » a rougi sur « NO MEANING YET » —
                # une DÉNÉGATION contient le mot qu'elle nie. On vise l'AFFIRMATION nue.
                verdict("— MEANING ]" not in r["titre"],
                        f"{state:14} → nor does the title", r["titre"])
                verdict("S for meaning" not in r["trois_d"],
                        f"{state:14} → the globe does not promise meaning either", r["trois_d"])
        # the numbers must reach the reader, not only the JSON
        mid = label(src, {"semantic": recorded["partial"], "nodes": []})
        verdict("2 of 4" in mid["bandeau"], "mid-indexing   → the banner gives the count",
                mid["bandeau"])

        print()
        # ── 3. a graph.json from BEFORE this declaration ──────────────────────────────
        old = label(src, {"nodes": [{"id": "a"}, {"id": "b"}]})
        verdict(old["cap"]["state"] == "absent",
                "old graph.json → inferred from the notes, not assumed healthy",
                json.dumps(old["cap"]))
        verdict(not any(c in old["bandeau"] for c in CLAIM),
                "old graph.json → the banner does not claim meaning", old["bandeau"])
        old_ok = label(src, {"nodes": [{"id": "a", "embed2": vec}, {"id": "b", "embed2": vec}]})
        verdict(old_ok["cap"]["state"] == "ready",
                "old graph.json WITH vectors → still reads as meaning", old_ok["bandeau"])

        print("\n" + ("✅ the map says what it shows, in all five states."
                      if ok else "❌ the map claims something it cannot show."))
        return 0 if ok else 1
    finally:
        shutil.rmtree(lab, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
