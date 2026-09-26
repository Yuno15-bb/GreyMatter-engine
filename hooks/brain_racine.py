#!/usr/bin/env python3
"""brain_racine — the single definition of "which Brain am I measuring?".

THREE ROOTS, THREE NOTIONS. Confusing them is the defect this module exists to
close:

    CODE_ROOT   where my scripts, fixtures and neighbouring resources live. → __file__
    BRAIN_ROOT  the data tree I act on: corpus, state, maps.               → BRAIN_HOME
    HOME        the user's home: Desktop, vaults, backups.                 → ~

On the author's trunk the three coincide — and that is exactly what kept the defect
invisible for months. They diverge as soon as you clone, open a worktree, or install
the package somewhere else.

WHY A PRIMITIVE, AND ONLY NOW. The right pattern had existed since 2026-08-03 in
`tests/invariants_brain.py:19-23`, with the right reason written next to it, and had
never been propagated. On 2026-08-21 there were five inline copies of it. Five copies of
one definition are five chances to diverge: `grep -l "def racine"` returned nothing.

RULE (spec frozen on 2026-08-20, clauses 1 to 5):
    1. `realpath` is mandatory — the ~/.claude/projects/…/memory symlink gives two paths
       for a single tree, and two paths make two roots.
    2. never a literal `~/.c-brain/trunk` OUTSIDE this file — measured: 7 sites no
       variable could redirect. Here it is the one default, and BRAIN_HOME overrides it.
    3. never the `cwd` — it has no effect today; creating the dependency would be a step back.
    4. `BRAIN_HOME` set but EMPTY ≡ unset — measured on 2026-08-20.
    5. a single implementation — this file.
"""
import os


def brain_root(depuis=None):
    """Canonical root of the Brain being MEASURED: `BRAIN_HOME`, else `~/.c-brain/trunk`.

    `depuis` (the caller's `__file__`) is accepted and NOT used for the identity. The
    folder above the code is never the trunk in an installed engine: the hooks run as
    `~/.c-brain/trunk/hooks/X.py`, `hooks` is a symlink into the engine, and `realpath`
    resolves it BEFORE applying `..` — measured on 2026-09-25, the "parent of the code"
    landed in `~/.c-brain/versions/<version>`, the frozen engine doctor checks against
    its manifest. Every state file would have been written there. Under the plugin,
    the code sits in the plugin cache: no trunk at all."""
    demande = os.environ.get("BRAIN_HOME")
    if demande:                                   # "" is falsy: clause 4
        return os.path.realpath(demande)
    return os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))


def code_root(depuis):
    """Root of the calling CODE. Legitimate, and distinct from the Brain: that is where the
    fixtures, neighbouring scripts and program resources live. Never use it as the Brain's
    identity just because the two coincide on the author's trunk."""
    return os.path.dirname(os.path.abspath(depuis))
