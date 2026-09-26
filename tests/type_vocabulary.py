#!/usr/bin/env python3
"""type_vocabulary.py — the guard and the briefs must name the SAME note types.

THE INVARIANT:

    The `metadata.type` vocabulary enforced by hooks/on_fiche_write.py is exactly the one
    the writing agents are told to use in agents/*.md.

WHY IT NEEDS A TEST. The vocabulary is written down in two places that never read each
other: a Python set in the hook, and a prose line in each agent brief
("type: user | feedback | project | reference"). Add a fifth type to one side and the
other keeps its four — the hook then records a legitimate note as mistyped, for ever, in
a file nobody reads. A check that fires on a correct value is a check people learn to
ignore, and then it protects nothing at all.

This is the same failure the repository has already met twice on the same day: two recall
engines that had silently disagreed on which documents to index, and a viewer reading a
field the exporter never wrote. Every time, a contract stated in two places rather than
shared from one.

WHAT IT DOES NOT DO. It does not decide the vocabulary. If the two sides disagree, that is
a decision — change the briefs and the hook together, in one commit, and say why.

Run:
  python3 tests/type_vocabulary.py
  python3 tests/type_vocabulary.py --check
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOOK = os.path.join(ROOT, "hooks", "on_fiche_write.py")
AGENTS = os.path.join(ROOT, "agents")

# The line the briefs use to tell an agent which types exist.
BRIEF_LINE = re.compile(r"^\s*type:\s*([a-z]+(?:\s*\|\s*[a-z]+)+)\s*$", re.M)


def vocabulary_of_the_hook():
    sys.path.insert(0, os.path.join(ROOT, "hooks"))
    import on_fiche_write
    return set(on_fiche_write.VALID_TYPES)


def vocabularies_of_the_briefs():
    """{brief name: set of types} for every brief that states one."""
    out = {}
    for name in sorted(os.listdir(AGENTS)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(AGENTS, name), encoding="utf-8") as f:
            m = BRIEF_LINE.search(f.read())
        if m:
            out[name] = {t.strip() for t in m.group(1).split("|")}
    return out


def main():
    check = "--check" in sys.argv
    hook = vocabulary_of_the_hook()
    briefs = vocabularies_of_the_briefs()

    print(f"Type vocabulary — the guard knows {len(hook)}: {', '.join(sorted(hook))}\n")

    trouble = []
    if not briefs:
        trouble.append("no agent brief states a type vocabulary any more: the guard's list "
                       "has nothing left to agree with, and this test would pass on an "
                       "empty comparison")

    for name, types in briefs.items():
        if types == hook:
            print(f"  agents/{name:20} ✅ same {len(types)}")
        else:
            print(f"  agents/{name:20} ❌ {', '.join(sorted(types))}")
            missing = sorted(types - hook)
            extra = sorted(hook - types)
            detail = []
            if missing:
                detail.append("the brief allows " + ", ".join(missing) +
                              " and the guard would record " +
                              ("it" if len(missing) == 1 else "them") + " as unknown")
            if extra:
                detail.append("the guard accepts " + ", ".join(extra) +
                              " and no brief ever tells an agent to write " +
                              ("it" if len(extra) == 1 else "them"))
            trouble.append(f"agents/{name}: " + " ; ".join(detail))

    if trouble:
        print("\n❌ the guard and the briefs no longer name the same types:")
        for t in trouble:
            print(f"     {t}")
        print("\n   Change them TOGETHER, in one commit, and say why. A guard that fires")
        print("   on a legitimate value is a guard people learn to ignore.")
        return 1

    print(f"\n✅ {len(briefs)} brief(s) and the guard name exactly the same types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
