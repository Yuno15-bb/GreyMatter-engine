#!/usr/bin/env python3
"""Regenerates lessons/INDEX.md from the notes' `tags:` — the INDEX becomes an ARTIFACT.

The user's decision, 2026-08-14 (question Q3 of the "thematic skeleton" job): the truth
lives in the notes, the INDEX is derived. Reason: an index kept by hand over 223 lessons had
already drifted once — that is where its 16 "Misc" entries and its 21 labels sorting by
technology came from. Cf. [[reparer-l-artefact-derive-ne-tient-qu-un-cycle]]: the repair goes into
the source, never into the regenerated file.

What was SAVED before making this file disposable (otherwise the author's judgement was lost):
  · the 103 ⭐ → a `star: true` field in the note;
  · the 22 glosses the description did not carry → folded into the description.

    python3 hooks/index_lecons.py            # writes
    python3 hooks/index_lecons.py --check    # touches nothing, exits 1 if the INDEX has drifted
"""
import glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # CODE_ROOT, legitimate
from brain_racine import brain_root

# I-1 (2026-08-21). Before: the script's REPOSITORY root served as the Brain's identity —
# a CODE root taken for a BRAIN root. This module WRITES `lessons/INDEX.md`: on the
# wrong root, it rewrites another tree's index. Migrated WITHOUT being run on the
# trunk: the proof was made on throwaway clones, the held-out collection is in progress.
BRAIN = brain_root(__file__)
INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")


def frontmatter(p):
    raw = open(p, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---", raw, re.S)
    return m.group(1) if m else ""


def champ(fm, nom):
    m = re.search(rf'^{nom}:\s*"?(.*?)"?\s*$', fm, re.M)
    return m.group(1) if m else ""


def lire_lecons():
    out = []
    # Looks for tags across the whole tree (except sessions/, audits/, .git/, vision/, etc.)
    # because a lesson can physically be a project and still be a lesson through its tags.
    # vision/ is excluded: those are continuity source documents, not lessons
    excludes = {".git", "audits", "sessions", "capsule", "companion", "tools", "archive", ".claude", "planet", "vision"}
    for p in sorted(glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True)):
        # Excludes the specialised folders and the INDEX itself
        rel = os.path.relpath(p, BRAIN)
        if any(rel.startswith(ex) for ex in excludes) or os.path.basename(p) == "INDEX.md":
            continue
        fm = frontmatter(p)
        t = re.search(r"^tags:\s*\[(.*?)\]", fm, re.M)
        if not t:  # Only notes with tags are lessons
            continue
        nom = os.path.basename(p)[:-3]
        out.append({
            "nom": nom,
            "desc": champ(fm, "description"),
            "tags": [x.strip() for x in t.group(1).split(",") if x.strip()],
            "star": champ(fm, "star").lower() == "true",
        })
    return out


def rendre():
    # The registry is the KEYSTONE: without it there is no index to write.
    # We exit by naming the next step rather than unrolling a Python traceback —
    # a bare `FileNotFoundError` says what is missing, never what to do.
    # The file name and its keys (familles, titre, quand, lexique) are the registry's data
    # format, shared with brain_recall._load_families — not translated here.
    reg = os.path.join(BRAIN, "meta", "familles.json")
    try:
        familles = json.load(open(reg, encoding="utf-8"))["familles"]
    except FileNotFoundError:
        sys.exit(f"❌ family registry missing: {reg}\n"
                 "   → `git checkout meta/familles.json` in the trunk, or rerun "
                 "./install.sh (the package ships it in skeleton/meta/).")
    except (ValueError, KeyError) as e:
        sys.exit(f"❌ family registry unreadable: {reg} ({e})\n"
                 "   → repair the JSON; the INDEX is not rewritten until it loads.")
    lecons = lire_lecons()
    sans = [l["nom"] for l in lecons if not l["tags"]]

    par_fam = {k: {"principal": [], "aussi": []} for k in familles}
    for l in lecons:
        for i, t in enumerate(l["tags"]):
            if t in par_fam:
                par_fam[t]["principal" if i == 0 else "aussi"].append(l)

    ordre = sorted(familles, key=lambda k: -len(par_fam[k]["principal"]))
    lignes = [
        "<!-- ⚠️ GENERATED FILE — do not edit by hand: `python3 hooks/index_lecons.py` overwrites it.",
        "     The truth lives in each note's `tags:` field. To move a lesson,",
        "     change ITS tag, never this map. -->",
        "",
        "# Map of cross-cutting lessons",
        "",
        "This secondary index keeps exhaustive navigation without loading the whole catalogue on "
        "every start. It is structural: the recall engines and the knowledge metrics exclude it.",
        "",
        f"**{len(lecons)} lessons · {len(familles)} families.** The folder layout says the SCOPE "
        "(from where must the note be readable); these families say the TOPIC. The two axes are "
        "independent — a family is not a folder.",
        "",
    ]
    for k in ordre:
        f, grp = familles[k], par_fam[k]
        if not grp["principal"] and not grp["aussi"]:
            continue
        lignes.append(f"### {f['titre']}  ·  {len(grp['principal'])}")
        lignes.append(f"*{f['quand']}* — found by searching for: {' · '.join(f['lexique'])}")
        lignes.append("")
        # ⚠️ ONE NOTE PER LINE, SHORT GLOSS. First version: everything on a single line with
        # the whole description — 400 characters per note, 50 notes in a row, unreadable.
        # A catalogue is BROWSED: the name already carries the meaning, the gloss only confirms it.
        def glose(d, n=115):
            # ⚠️ A GENERATED MAP MUST BE INERT. The descriptions contain
            # backticks (`git checkout`, `tags:`): copied as they are, they
            # open unclosed code spans, and the doctor's link extractor swallowed
            # everything after them. Measured: 289 `[[` in the file, 136 links seen — 153 links
            # lost, hence "orphans" wrongly reported on perfectly linked notes.
            # Brackets are neutralised too, since they would make fake links.
            d = re.sub(r"\s+", " ", d).replace("`", "").replace("[[", "").replace("]]", "").strip()
            if len(d) <= n:
                return d
            coupe = d[:n].rsplit(" ", 1)[0]
            return coupe + "…"
        for l in sorted(grp["principal"], key=lambda x: (not x["star"], x["nom"])):
            etoile = "⭐ " if l["star"] else ""
            lignes.append(f"- {etoile}[[{l['nom']}]] — {glose(l['desc'])}" if l["desc"]
                          else f"- {etoile}[[{l['nom']}]]")
        if grp["aussi"]:
            lignes.append("")
            lignes.append("*Also touches this family:* " +
                          " · ".join(f"[[{l['nom']}]]" for l in sorted(grp["aussi"], key=lambda x: x["nom"])))
        lignes.append("")
    if sans:
        lignes += ["### ⚠️ No family — to tag", "", " · ".join(f"[[{n}]]" for n in sans), ""]
    return "\n".join(lignes) + "\n"


if __name__ == "__main__":
    neuf = rendre()
    if "--check" in sys.argv:
        actuel = open(INDEX, encoding="utf-8").read() if os.path.exists(INDEX) else ""
        if actuel == neuf:
            print("INDEX up to date."); sys.exit(0)
        print("INDEX DRIFTED — rerun `python3 hooks/index_lecons.py`.", file=sys.stderr); sys.exit(1)
    open(INDEX, "w", encoding="utf-8").write(neuf)
    n = len(lire_lecons())
    print(f"lessons/INDEX.md regenerated: {n} lessons")
