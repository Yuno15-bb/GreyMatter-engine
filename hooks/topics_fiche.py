#!/usr/bin/env python3
"""topics_fiche — READ and VALIDATE a note's topic. One definition, one piece of code.

WHY THIS MODULE EXISTS
    The trunk already has SIX frontmatter readers, each written on its own
    (`brain_doctor`, `graph_export`, `index_lecons`, `fraicheur_fiches`,
    `provenance_fiches`, `archiver-journal`). None is a real YAML parser: they are
    line-by-line regular expressions. Adding a seventh dialect for topics would
    reproduce exactly the defect measured on 20/08, where two readers of `MEMORY.md`
    manufactured the divergence they claimed to measure. So everything that reads or writes
    a topic goes through here — the writing tool as well as the bench that puts it to the test.

THE SOURCE REMAINS `meta/topics.json`
    The valid identifiers are READ on every call, never copied. A topic removed from
    the source becomes invalid here immediately, with no list to keep up to
    date. That is what makes the counter-test "the 13th topic comes back" possible.

THE FORMAT, AND WHY THIS ONE (measured before being chosen)
        topic: proof-and-verification
        secondary_topics: [the-brain, machine-and-process]

    - One key per line, plain value: the six regular-expression readers read it
      without flinching, and none validates the list of keys — a new key turns nobody
      red (checked in `brain_doctor.frontmatter`, which only controls `name` and
      `description`).
    - The list is INLINE, in brackets, because that is already the trunk's convention
      for `tags:`, read by `re.search(r"^tags:\\s*\\[(.*?)\\]")`. A dashed YAML list
      would be silently ignored by `brain_doctor`, which keeps only what looks like
      `key: value`.
    - `secondary_topics` is ABSENT when there are none: an empty key would read as
      a one-element list holding an empty item in at least one of the readers.
    - The frontmatter does NOT enter the text indexed by recall (`brain_recall` builds
      its document with `strip_md()`, which removes the frontmatter). Writing a topic therefore
      cannot move a `golden_recall` result — this is checked by counter-test, not
      assumed.
"""
import json
import os
import re

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
SOURCE = os.path.join(BRAIN, "meta", "topics.json")

RE_TOPIC = re.compile(r"^topic:[ \t]*(.*?)[ \t]*$", re.M)
RE_SECONDAIRES = re.compile(r"^secondary_topics:[ \t]*\[(.*?)\][ \t]*$", re.M)


class SujetInvalide(ValueError):
    """Raised when a topic cannot be written. Refusing is the intended behaviour."""


def ids_canoniques():
    """The valid topic identifiers, READ from the source on every call."""
    canon = json.load(open(SOURCE, encoding="utf-8"))
    return [t["id"] for t in canon["topics"]]


def bloc_frontmatter(texte):
    """The content between the two leading `---`, or None. Same cut as the six readers."""
    m = re.match(r"^---\n(.*?)\n---", texte, re.S)
    return m.group(1) if m else None


def lire(texte):
    """Returns (topic, [secondaries]) as they are WRITTEN. Validates nothing, guesses nothing.

    `topic` is None if the key is absent. A key present twice returns the list of
    all its values, so that the check can REFUSE instead of picking one.
    """
    fm = bloc_frontmatter(texte)
    if fm is None:
        return None, []
    principaux = [v.strip().strip('"').strip("'") for v in RE_TOPIC.findall(fm)]
    m = RE_SECONDAIRES.search(fm)
    secondaires = []
    if m:
        secondaires = [x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()]
    if len(principaux) > 1:
        return principaux, secondaires        # a LIST signals the fault to the checker
    return (principaux[0] if principaux else None), secondaires


def valider(topic, secondaires, ids=None):
    """Raises SujetInvalide if anything is wrong. No silent correction."""
    ids = ids if ids is not None else ids_canoniques()
    if isinstance(topic, list):
        raise SujetInvalide("two main topics: %s" % topic)
    if not topic:
        raise SujetInvalide("no main topic")
    if topic not in ids:
        raise SujetInvalide("unknown main topic: %r" % topic)
    vus = set()
    for s in secondaires:
        if s not in ids:
            raise SujetInvalide("unknown secondary topic: %r" % s)
        if s == topic:
            raise SujetInvalide("secondary %r repeats the main topic" % s)
        if s in vus:
            raise SujetInvalide("duplicate secondary: %r" % s)
        vus.add(s)
    return True


def rendu(topic, secondaires):
    """The lines to insert into the frontmatter, in stable order."""
    lignes = ["topic: %s" % topic]
    if secondaires:
        lignes.append("secondary_topics: [%s]" % ", ".join(secondaires))
    return lignes


def ecrire(texte, topic, secondaires, ids=None):
    """Returns the text with the topic set. VALIDATES first; touches nothing else.

    The insertion goes right after `tags:` when it exists — the two classification axes
    then read side by side — otherwise after `description:`. A key already present is
    replaced in place, never duplicated.
    """
    valider(topic, secondaires, ids)
    fm = bloc_frontmatter(texte)
    if fm is None:
        raise SujetInvalide("note without frontmatter")
    lignes = fm.split("\n")
    # remove the existing keys (replacement, not stacking)
    lignes = [l for l in lignes
              if not re.match(r"^topic:", l) and not re.match(r"^secondary_topics:", l)]
    nouvelles = rendu(topic, secondaires)
    pos = None
    for i, l in enumerate(lignes):
        if re.match(r"^tags:", l):
            pos = i + 1
    if pos is None:
        for i, l in enumerate(lignes):
            if re.match(r"^description:", l):
                pos = i + 1
        # a multi-line description (a `>-` block): go down to the next key
        while pos is not None and pos < len(lignes) and re.match(r"^\s", lignes[pos]):
            pos += 1
    if pos is None:
        pos = len(lignes)
    lignes[pos:pos] = nouvelles
    return texte.replace(fm, "\n".join(lignes), 1)
