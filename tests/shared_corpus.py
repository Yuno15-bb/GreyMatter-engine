#!/usr/bin/env python3
"""shared_corpus.py — do both recall engines see the SAME corpus?

THE INVARIANT:

    The indexable corpus is defined ONCE (hooks/brain_corpus.py).
    No engine keeps a local copy of it.

THE INCIDENT THAT PRODUCED IT (measured 2026-08-16, on a real trunk):

    brain_recall (BM25)        471 documents
    brain_embed  (embeddings)  476 documents
    gap: 5 documents, all under tools/

An earlier measurement on the same corpus version found 393 versus 458 documents:
65 skill files had entered the trunk on 2026-08-15. The later measurement reflects
subsequent corpus growth; both incidents show why the engines must share one source.

`brain_embed.py` carried the comment "IMPORTANT: the SAME corpus as brain_recall".
It had been wrong for as long as the two lists had drifted, and nothing could say so:
**parity asserted in prose never turns red**. Comparisons of BM25 and embeddings
measured two corpora while believing they compared two retrieval methods — including
the blind duel that settled BM25 as the recall engine, before the drift was detected.

WHY THE CHECK IS STATIC. Comparing the two lists by importing both would be
TAUTOLOGICAL now that they come from the same module: the test would pass by
comparing an object to itself, and would stay green the day someone rewrites a local
list somewhere else. What we watch is therefore the GESTURE that produced the
incident: **the reappearance of a local definition**.

Run:
  python3 tests/shared_corpus.py
  python3 tests/shared_corpus.py --check      # barrier (static, instant)
  python3 tests/shared_corpus.py --full       # + REAL comparison of both engines (venv)
"""
import argparse
import ast
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
HOOKS = os.path.join(BRAIN, "hooks")
sys.path.insert(0, HOOKS)

import brain_corpus  # noqa: E402

# The engines that must CONSUME the definition, never write it.
ENGINES = ("brain_recall.py", "brain_embed.py")
SOURCE = "brain_corpus"
NAMES = ("SKIP_DIRS", "SKIP_PREFIX", "SKIP_FILES")


def analyse(filename):
    """(local definitions found, does it import the source?)"""
    path = os.path.join(HOOKS, filename)
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)

    local, imports = [], False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == SOURCE:
            imports = True
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == SOURCE:
                    imports = True
        # An ASSIGNMENT to one of these names is a local copy. A `from … import X`
        # produces no Assign node: the two cases separate cleanly.
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id in NAMES:
                    local.append((t.id, node.lineno))
    return local, imports


def real_comparison():
    """The observable: what each engine ACTUALLY indexes, each in its own interpreter.

    brain_embed lives in the venv (numpy + model2vec); brain_recall runs under the
    system python. They cannot be loaded in the same process — which is exactly why
    their corpora could drift without anyone ever putting them side by side.
    """
    import brain_recall as br
    a = {d["path"] for d in br.load_corpus()}

    venv = os.path.join(BRAIN, ".venv", "bin", "python")
    if not os.path.exists(venv):
        return a, None, "venv absent"
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import brain_embed as be\n"
        "print('\\n'.join(sorted(rel for rel, *_ in be.fiches())))\n" % HOOKS
    )
    try:
        out = subprocess.run([venv, "-c", code], capture_output=True, text=True, timeout=180)
    except Exception as e:                       # noqa: BLE001
        return a, None, f"subprocess failed: {e}"
    if out.returncode != 0:
        return a, None, (out.stderr or "").strip().splitlines()[-1:] or "error"
    return a, {l for l in out.stdout.split("\n") if l.strip()}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--full", action="store_true",
                    help="REALLY compare both engines (loads the venv, ~2 s)")
    a = ap.parse_args()

    print(f"Shared corpus — single source: hooks/{SOURCE}.py "
          f"({len(brain_corpus.indexable())} documents)\n")

    trouble = []
    for m in ENGINES:
        local, imports = analyse(m)
        if local:
            trouble.append(f"{m} locally redefines " +
                           ", ".join(f"{n} (line {l})" for n, l in local))
        if not imports:
            trouble.append(f"{m} does not import {SOURCE}")
        state = "❌ local copy" if local else ("✅ imports the source" if imports
                                              else "❌ imports nothing")
        print(f"  hooks/{m:20} {state}")

    if a.full:
        print()
        bm25, vec, issue = real_comparison()
        if issue:
            print(f"  ⚠️  real comparison impossible: {issue}")
        else:
            only_a, only_b = sorted(bm25 - vec), sorted(vec - bm25)
            print(f"  brain_recall (BM25)        {len(bm25)} documents")
            print(f"  brain_embed  (embeddings)  {len(vec)} documents")
            if only_a or only_b:
                trouble.append(f"corpora diverge: {len(only_a)} document(s) seen only by "
                               f"BM25, {len(only_b)} only by the embeddings engine")
                for p in (only_a + only_b)[:8]:
                    print(f"     ≠ {p}")
            else:
                print("  gap                        0 documents ✅")

    if trouble:
        print("\n❌ the corpus definition is no longer unique:")
        for t in trouble:
            print(f"     {t}")
        print("\n   An engine that writes its own list will drift — it happened, 5")
        print("   documents apart, under a comment claiming the corpora were identical.")
        print(f"   Import from hooks/{SOURCE}.py, do not copy it.")
        return 1

    print("\n✅ one corpus, defined once, consumed by both engines")
    if not a.full:
        print("   (--full to also compare both engines at runtime)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
