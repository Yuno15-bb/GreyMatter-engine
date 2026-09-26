#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""
recall_cache.py — a stale index is worse than a slow one.

The recall corpus is cached, because rebuilding it on every prompt cost 243 ms
on a 241-note trunk and grew linearly. That cache buys speed and introduces the
one failure this project cannot afford: serving notes that no longer say what
they said. Nothing about it would be visible — recall would keep answering,
confidently, out of date.

So every way the trunk can change has to invalidate it, and every way the cache
can go wrong has to degrade into "slower", never into "wrong" and never into
"crashed" — this runs inside a hook, and a hook that throws takes the session's
recall with it.

Run: python3 tests/recall_cache.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = 0


def check(label, condition, detail=""):
    global FAILS
    if condition:
        print(f"  ✅ {label}")
    else:
        print(f"  ❌ {label}{'  — ' + detail if detail else ''}")
        FAILS += 1


def load_recall(trunk):
    spec = importlib.util.spec_from_file_location(
        "brain_recall", ROOT / "hooks" / "brain_recall.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.BRAIN = str(Path(trunk).resolve())
    return mod


def main():
    tmp = Path(tempfile.mkdtemp(prefix="cbrain-cache-"))
    try:
        trunk = tmp / "trunk"
        (trunk / "lessons").mkdir(parents=True)
        m = load_recall(trunk)
        cache = trunk / "state" / "recall-index.json"

        def note(name, body):
            # mtime has nanosecond resolution in the fingerprint, but a test
            # that writes twice within the same tick would still be a lie on a
            # filesystem with coarser stamps. A short sleep keeps it honest.
            time.sleep(0.01)
            (trunk / "lessons" / f"{name}.md").write_text(
                f"---\nname: {name}\ndescription: \"d\"\n---\n{body}\n", encoding="utf-8")

        note("alpha", "cache deployment stale artifact")

        first = m.load_corpus()
        check("the cache file is written", cache.exists())
        second = m.load_corpus()
        check("a cache hit returns the identical corpus", first == second)

        print("▸ every way a trunk changes must invalidate it")
        note("alpha", "offline queue outbox retry resync")
        docs = m.load_corpus()
        check("edited note → new tokens served",
              "outbox" in docs[0]["tokens"],
              "the cache served the note's previous content")

        note("beta", "token refresh expiry")
        check("added note → indexed", len(m.load_corpus()) == 2)

        (trunk / "lessons" / "beta.md").unlink()
        check("deleted note → dropped", len(m.load_corpus()) == 1)

        # A rename keeps mtime and size: only the path changes. If the
        # fingerprint ignored paths, recall would keep pointing at a file that
        # no longer exists, and the note would open on nothing.
        (trunk / "lessons" / "alpha.md").rename(trunk / "lessons" / "renamed.md")
        docs = m.load_corpus()
        check("renamed note → new path served",
              docs and docs[0]["path"].endswith("renamed.md"),
              f"still serving {docs[0]['path'] if docs else 'nothing'}")

        print("▸ a broken cache degrades to slow, never to wrong or dead")
        cache.write_text("{ not json at all", encoding="utf-8")
        check("corrupt cache → rebuilt", len(m.load_corpus()) == 1)

        # The cache is planted with a version the code does not accept AND with
        # content that could only come from it. Asserting on the note COUNT
        # would pass either way — that weaker check let a mutation through
        # while still reporting green.
        import json as _json
        stale = _json.loads(cache.read_text(encoding="utf-8"))
        stale["version"] = 0
        stale["docs"] = [{"path": "lessons/ghost.md", "name": "SHOULD-NOT-BE-SERVED",
                          "desc": "", "tokens": ["ghost"]}]
        cache.write_text(_json.dumps(stale), encoding="utf-8")
        served = {d["name"] for d in m.load_corpus()}
        check("older cache version → discarded, not served",
              "SHOULD-NOT-BE-SERVED" not in served,
              "a cache written under different tokenisation rules was served as-is")

        os.chmod(trunk / "state", 0o500)          # read-only state directory
        try:
            check("unwritable cache → recall still answers",
                  len(m.load_corpus()) == 1)
        finally:
            os.chmod(trunk / "state", 0o700)

        print()
        if FAILS:
            print(f"❌ {FAILS} failure(s) — the recall cache can serve stale notes")
            return 1
        print("✅ the cache is invalidated by every trunk change, and never fails hard")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
