#!/usr/bin/env python3
"""
identite_fiche — the ONLY definition of "what is this file's logical identifier".

WHY THIS FILE EXISTS. The trunk derives a note's identity from its file name everywhere:
`basename[:-3]`. That holds for `projects/`, `lessons/`, `life/`, `meta/`. It does
NOT hold for `skills/`, and on 2026-08-25 that difference broke all 24 of the
author's skills.

WHAT HAPPENED, AND WHY IT WAS BOUND TO. An agent wanted to bring the
skills into the Brain's graph. It added `skills` to `brain_doctor`'s `LINKED_DIRS`.
The doctor then applied its general rule to `skills/design/SKILL.md`:
`base = "SKILL"`, compared with the frontmatter's `name: design` → violation; and
`re.fullmatch(r"[a-z0-9-]+", "SKILL")` → violation too. **Renaming the file to
`design.md` was the ONLY way to satisfy the doctor.** The agent did it, twice, and
the 24 skills became unfindable for Claude Code, which requires `SKILL.md`.

So it was not clumsiness: it was a contradictory constraint nobody had settled.

THE DECISION (the author, 2026-08-27): **the external constraint has authority over the
physical form.** Claude Code requires `skills/<slug>/SKILL.md`; the Brain does not break that
convention to satisfy its own indexer. The indexer is the one that learns.

    physical   skills/design/SKILL.md
    identity   design                    ← the FOLDER's name, not the file's

ONE SINGLE INDEXABLE REPRESENTATION. If `SKILL.md` and `design.md` coexist, it is not
"two notes" nor "one note indexed twice": it is a CONFLICT, and it is reported.
Indexing both silently would give 48 identities for 24 skills, and a resolution of
`[[design]]` that depends on the order the disk is walked in.

WHY HERE AND NOT IN EACH CONSUMER. A dozen places compute
`basename[:-3]`. Copying the rule into each would guarantee they diverge at the first
new folder — that is already `commit_par_zone`'s argument for its zone table. One
definition, several importers.
"""
import os

# Families whose identity comes from the FOLDER and not from the file, with the canonical
# name imposed by the external tool.
FAMILLES_A_DOSSIER = {"skills": "SKILL.md"}

# Subfolders that are not notes: a family's internal resources.
DOSSIERS_RESSOURCE = {"_refs", "references", "assets", "scripts"}

# Tooling: never knowledge. Found by measuring, not planned — a `.venv` in
# `skills/video-merge/` brought in `numpy/random/LICENSE.md` as a "competing
# representation of the video-merge skill". A scanner that goes down into a virtualenv
# indexes somebody else's dependencies.
DOSSIERS_OUTILLAGE = {".venv", "venv", "node_modules", "__pycache__", ".git",
                      "site-packages", ".tox", "dist", "build", ".pytest_cache"}


def identite(rel):
    """Path relative to the trunk → (slug, canonical, reason).

    slug       logical identity, or None if this file is not a note at all;
    canonical  True if it is THE representation to index;
    reason     why it is not, when it is not.
    """
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    if not rel.endswith(".md"):
        return None, False, "not a .md"
    zone = parts[0]
    fichier = parts[-1]

    if zone in FAMILLES_A_DOSSIER:
        if len(parts) < 3:
            # `skills/something.md` — outside the folder/SKILL.md scheme
            return None, False, "outside the scheme %s/<slug>/%s" % (zone, FAMILLES_A_DOSSIER[zone])
        dossier = parts[1]
        intermediaires = set(parts[1:-1])
        if intermediaires & DOSSIERS_OUTILLAGE:
            return None, False, "outillage (%s)" % ", ".join(sorted(intermediaires & DOSSIERS_OUTILLAGE))
        if dossier in DOSSIERS_RESSOURCE or (intermediaires & DOSSIERS_RESSOURCE):
            return None, False, "internal resource, not a note"
        # DEPTH. The scheme imposed by the external tool is EXACTLY
        # `zone/<slug>/SKILL.md` — two segments, not three. A folder that CONTAINS
        # others is not a skill, it is a container, and its name is nobody's
        # identity. Measured on 2026-09-20: `skills/synced/<uuid>/<slug>/SKILL.md`, the
        # mirror of synced skills, folded ITS 57 SKILL.md onto the single identity
        # "synced". Chain reaction — 57 orphans and 57 off-map notes all carrying
        # the same name, 86 "competing representations", 58 frontmatter complaints;
        # and since the doctor prints only 12 entries per section, the sabotage of
        # `tests/identite_skills.py` (a skill with a wrong `name:`) fell OFF THE SCREEN.
        # The bench was red on "INVISIBLE SABOTAGE": noise hiding a defect.
        # The rule is stated as structure, not as a list of names — a list would have missed the
        # next container, which is what this file already holds against the `basename` copies.
        if len(parts) > 3:
            return None, False, ("outside the scheme %s/<slug>/%s — %d folder levels, "
                                 "so a container and not a skill"
                                 % (zone, FAMILLES_A_DOSSIER[zone], len(parts) - 1))
        if fichier == FAMILLES_A_DOSSIER[zone]:
            return dossier, True, None
        # same logical identity, another file: a COMPETING representation.
        return dossier, False, ("competing representation of %s/%s/%s"
                                % (zone, dossier, FAMILLES_A_DOSSIER[zone]))

    return os.path.splitext(fichier)[0], True, None


def chemin_canonique(zone, slug):
    """The reverse: where the note `slug` of zone `zone` MUST live."""
    if zone in FAMILLES_A_DOSSIER:
        return "%s/%s/%s" % (zone, slug, FAMILLES_A_DOSSIER[zone])
    return "%s/%s.md" % (zone, slug)


def scanner(racine, zones):
    """Walks `zones` under `racine`. Returns (index, conflits, ignores).

    index     {slug: relative path}  — one entry per identity, never two;
    conflits  [(slug, canonical, competitor, reason)] — to REPORT, not to settle alone;
    ignores   [(rel, reason)] — internal resources and files outside the scheme.

    The scanner neither deletes nor renames anything: detecting is not deciding.
    """
    index, conflits, ignores, vus = {}, [], [], {}
    for z in zones:
        d = os.path.join(racine, z)
        if not os.path.isdir(d):
            continue
        for r, sousdirs, fs in os.walk(d):
            # prune AT THE SOURCE: going down into a .venv and then filtering costs
            # thousands of files for nothing.
            sousdirs[:] = [x for x in sousdirs if x not in DOSSIERS_OUTILLAGE]
            for f in sorted(fs):
                if not f.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(r, f), racine).replace("\\", "/")
                slug, canonique, motif = identite(rel)
                if slug is None:
                    ignores.append((rel, motif))
                    continue
                vus.setdefault(slug, []).append((rel, canonique, motif))
    for slug, entrees in vus.items():
        canons = [e for e in entrees if e[1]]
        autres = [e for e in entrees if not e[1]]
        if canons:
            index[slug] = canons[0][0]
            for rel, _, motif in autres:
                conflits.append((slug, canons[0][0], rel, motif))
            for rel, _, _ in canons[1:]:
                conflits.append((slug, canons[0][0], rel, "deux fichiers canoniques"))
        elif autres:
            # no canonical: the note is NOT indexed, and we say why.
            for rel, _, motif in autres:
                conflits.append((slug, None, rel, motif + " — no canonical present"))
    return index, conflits, ignores
