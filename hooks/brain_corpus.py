#!/usr/bin/env python3
"""brain_corpus — THE definition of the trunk's indexable corpus. Single source.

WHY THIS FILE EXISTS (2026-08-16). This definition lived in TWO copies: one in
`brain_recall.py` (BM25), one in `brain_embed.py` (embeddings), the second one
carrying the comment "IMPORTANT: the SAME corpus as brain_recall". Measured on a
real trunk the day this file was written:

    brain_recall  471 documents      (tools/ excluded)
    brain_embed   476 documents      (tools/ indexed)
    gap: 5 documents, all under tools/ — two READMEs and three result LISEZ-MOI

Nobody saw it, because nothing compared the two. The comment ASSERTED parity
instead of guaranteeing it — and a comment never turns red.

WHAT IT BROKE. Every BM25 / embeddings comparison measured two CORPORA while
believing it compared two retrieval methods. The blind duel behind
docs/decisions (BM25 stays the recall engine) was settled BEFORE the divergence
appeared; replaying it against these two definitions would return a false verdict.

THE RULE. No engine redefines this list. It imports it.
`tests/shared_corpus.py` rejects any module that writes itself a local copy.
"""
import glob
import os

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))

# Excluded from the corpus: the RAW and infrastructure layers. Recall must surface
# DISTILLED knowledge (projects/lessons/meta/life), not agent catalogues, state, or
# the cold corpus.
#   • sessions/ : TIMELINE.md indexes 80+ sessions and is long enough to match almost
#     anything → pure noise.
#   • corpus/   : the cold layer (thousands of imported conversations) would drown the top-k.
# Matched on path SEGMENTS, never as a substring: otherwise a note named "capsule-…"
# or "…-sessions" would be wrongly excluded, which is the bug this replaced.
#   • tools/    : tooling. The value bench keeps COPIES of the trunk for its conditions;
#     without this exclusion every note was indexed 5 times (1573 docs instead of 312),
#     which skews the IDF of the whole corpus and therefore every score. This is the
#     line brain_embed.py was missing — the 5-document divergence above.
SKIP_DIRS = {
    ".git", "node_modules", "capsule", "capsule-v2", "corpus", "audits",
    "agents", "state", "tools",
    #   • skills/ : skill definitions are USER MANUALS and their references — tooling,
    #     like agents/ just above, not distilled knowledge. Measured on a trunk that
    #     hosts them: 65 of 438 indexed documents came from skills/ (15% of the
    #     corpus), and recall answered "push the changes" with
    #     skills/blender-motion/references/fcurve-modifiers.md. Moving a tooling layer
    #     into the trunk and excluding it from recall must happen TOGETHER; filing it
    #     under the trunk without this line makes it compete with real notes.
    "skills",
    #   • archive/ : the COLD layer (journals detached from their note). Measured
    #     2026-08-14: without this line an archived journal came back in FIRST
    #     position, ahead of the current note. Filing history away as cold makes no
    #     sense if it keeps competing with the present in search. Kept on disk and in
    #     git, kept out of recall.
    "archive",
    # `vision/` = SOURCE documents about vision and continuity (the C Brain/GMatter
    # MASTER, 2026-08-19). They are not knowledge notes: they are long narratives
    # that explain WHY the system exists. A single one of them weighs more than 20
    # notes and touches the project's whole vocabulary — indexed, it would surface on
    # almost every query and crush the precise note being looked for (the same
    # mechanism as `archive/`, measured on 2026-08-14).
    # They stay reachable through their POINTER in MEMORY.md and through the short
    # note that serves as their entry point, which is indexed.
    # Locked by tests/vision_hors_corpus.py.
    "vision",
}
SKIP_PREFIX = ("sessions",)
SKIP_FILES = {"MEMORY.md", os.path.join("lessons", "INDEX.md")}


def skip(rel):
    """Is this relative path outside the corpus?"""
    if rel in SKIP_FILES or any(rel.startswith(p) for p in SKIP_PREFIX):
        return True
    dirs = rel.split(os.sep)[:-1]               # FOLDER segments (excluding the file name)
    return any(d in SKIP_DIRS for d in dirs)


def indexable(brain=None):
    """The corpus .md files, sorted — (relative path, absolute path).

    The sort is not cosmetic: it feeds the fingerprint of brain_recall's index
    cache. An unstable order would discard the cache on every call.
    """
    root = brain or BRAIN
    out = []
    for p in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, root)
        if not skip(rel):
            out.append((rel, p))
    out.sort()
    return out


if __name__ == "__main__":
    docs = indexable()
    print(f"{len(docs)} documents in the indexable corpus of {BRAIN}")
