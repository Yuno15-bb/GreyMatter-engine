#!/usr/bin/env python3
"""Exercise the production topic reader and writer on in-memory notes.

A temporary topic catalog is the sole source of valid identifiers. Removing an
identifier must immediately make it invalid.
"""
import json
import os
import sys
import tempfile
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CATALOG = ["proof-and-verification", "the-brain", "client-projects",
           "interfaces-and-rendering", "machine-and-process"]

NOTE = """---
name: bench-note
description: "A test note."
tags: [the-brain]
metadata:
  type: lesson
---

# Body

Unchanged text.
"""
NO_TAGS = """---
name: note-without-tags
description: "No tags here."
metadata:
  type: lesson
---

Body.
"""


def run(topic_module):
    topics = topic_module
    ids = topics.ids_canoniques()
    failures = []

    def verify(label, passed):
        print(("  PASS " if passed else "  FAIL ") + label)
        if not passed:
            failures.append(label)

    for label, topic, secondary in (
        ("one main topic", "proof-and-verification", []),
        ("one secondary", "the-brain", ["proof-and-verification"]),
        ("two secondaries", "client-projects",
         ["interfaces-and-rendering", "proof-and-verification"]),
    ):
        written = topics.ecrire(NOTE, topic, secondary, ids)
        verify(label + " round-trips", topics.lire(written) == (topic, secondary))

    written = topics.ecrire(NOTE, "the-brain", ["proof-and-verification"], ids)
    added = [line for line in written.splitlines() if line not in NOTE.splitlines()]
    removed = [line for line in NOTE.splitlines() if line not in written.splitlines()]
    verify("only topic lines are added",
           sorted(added) == ["secondary_topics: [proof-and-verification]", "topic: the-brain"]
           and not removed)
    with_tags = topics.ecrire(NOTE, "the-brain", [], ids).splitlines()
    without_tags = topics.ecrire(NO_TAGS, "the-brain", [], ids).splitlines()
    verify("topic follows tags or description",
           with_tags[with_tags.index("tags: [the-brain]") + 1] == "topic: the-brain"
           and without_tags[without_tags.index('description: "No tags here."') + 1]
           == "topic: the-brain")

    twice = topics.ecrire(topics.ecrire(NOTE, "the-brain", [], ids),
                         "proof-and-verification", ["machine-and-process"], ids)
    frontmatter = topics.bloc_frontmatter(twice).splitlines()
    verify("rewriting replaces instead of stacking",
           sum(line.startswith("topic:") for line in frontmatter) == 1
           and sum(line.startswith("secondary_topics:") for line in frontmatter) == 1
           and topics.lire(twice) == ("proof-and-verification", ["machine-and-process"]))

    for label, main, secondary in (
        ("unknown main topic", "invented-topic", []),
        ("retired topic", "making-methods", []),
        ("missing main topic", None, []),
        ("empty main topic", "", []),
        ("unknown secondary", "the-brain", ["invented-topic"]),
        ("secondary repeats main", "the-brain", ["the-brain"]),
        ("duplicate secondary", "the-brain", ["proof-and-verification"] * 2),
        ("two main topics", ["the-brain", "proof-and-verification"], []),
    ):
        try:
            topics.valider(main, secondary, ids)
            refused = False
        except topics.SujetInvalide:
            refused = True
        verify(label + " is refused", refused)

    double = NOTE.replace("tags: [the-brain]",
                          "tags: [the-brain]\ntopic: the-brain\ntopic: client-projects")
    main, _ = topics.lire(double)
    verify("duplicate topic keys remain visible", isinstance(main, list))
    reduced = [item for item in ids if item != "the-brain"]
    try:
        topics.valider("the-brain", [], reduced)
        follows_catalog = False
    except topics.SujetInvalide:
        follows_catalog = True
    verify("removing a catalog ID invalidates it", follows_catalog)
    print("PASS" if not failures else "FAIL: " + ", ".join(failures))
    return 0 if not failures else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sabotage", action="store_true", help="Disable topic validation")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="topics-bench-") as root:
        meta = os.path.join(root, "meta")
        os.makedirs(meta)
        with open(os.path.join(meta, "topics.json"), "w") as source:
            json.dump({"topics": [{"id": name} for name in CATALOG]}, source)
        os.environ["BRAIN_HOME"] = root
        sys.path.insert(0, os.path.join(ROOT, "hooks"))
        import topics_fiche
        if args.sabotage:
            topics_fiche.valider = lambda topic, secondary, ids=None: True
        return run(topics_fiche)


if __name__ == "__main__":
    sys.exit(main())
