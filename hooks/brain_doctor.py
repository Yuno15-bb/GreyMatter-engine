#!/usr/bin/env python3
"""brain_doctor — integrity healthcheck of the trunk.

Checks, without modifying anything:
  1. dead [[x]] links (EXCLUDING doc examples and code blocks),
  2. orphan notes (never targeted by a link),
  3. frontmatter complet (name / description / metadata.type) et name == nom de fichier,
  4. convention de nom kebab-case,
  5. presence in the map: MEMORY.md + lessons/INDEX.md,
  6. MEMORY.md size under the safe-loading threshold,
  7. git drift (uncommitted changes),
  8. a `metadata.type` outside the known vocabulary,
  9. a typed `relations:` entry the graph exporter would silently drop.

DOCTOR DIAGNOSES. IT NEVER REPAIRS, AND IT NEVER DEFINES.

Checks 8 and 9 are about vocabularies, and neither of them is written here. They are
IMPORTED from the file that owns them:

    metadata.type      hooks/on_fiche_write.py   VALID_TYPES
    relations:         hooks/graph_export.py     RELATION_TYPES  (+ its own parser)

That is the whole point. A third copy of a vocabulary is a third thing to disagree with,
and this repository has already met that failure three times in three days: two recall
engines that silently indexed different corpora, a viewer reading a field its exporter
never wrote, and a type list living in a hook and in five agent briefs at once. Doctor's
job is to REPORT a disagreement between existing sources, never to arbitrate one.

WHAT IT DELIBERATELY DELEGATES, because a test already owns it:
    tests/type_vocabulary.py    the hook's type list == the agent briefs'
    tests/planet_contract.py    the viewer reads only fields the exporter writes
    tests/shared_corpus.py      one corpus definition, imported by both engines
    tests/fiche_write_contract.py   what the write hook does to a note
Those run in CI, on the repository. Doctor runs on a user's trunk, where the question is
not "is the engine coherent" but "is this trunk consistent with the engine it has".

Usage :
  brain_doctor.py            → rapport lisible + exit 0 (sain) / 1 (anomalies)
  brain_doctor.py --json     → writes state/doctor.json (for the hooks) + exit code
  brain_doctor.py --quiet    → exit code seulement
"""
import os, re, sys, json, subprocess, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The two vocabularies, imported from the files that OWN them — never restated here.
# Guarded: a doctor that cannot run because a hook moved would be worse than a doctor
# that reports one check less. When a vocabulary cannot be reached, the corresponding
# check is skipped and SAYS SO, rather than passing silently on an empty set.
try:
    from on_fiche_write import VALID_TYPES
except Exception:
    VALID_TYPES = None
try:
    from graph_export import RELATION_TYPES, _REL_BLOCK, _REL_LINE
except Exception:
    RELATION_TYPES = _REL_BLOCK = _REL_LINE = None

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
LESSONS_INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")
MEMORY_WARN_BYTES = 20_000
STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}
LINKED_DIRS = ("projects", "lessons", "life", "meta")           # the woven areas
# skip logic consistent with brain_recall/brain_embed: FOLDER segments (set) + prefixes (startswith).
# L'ancien `"sessions/archive" in parts` (token multi-segment vs segment unique) ne matchait JAMAIS
# → the archive notes + TIMELINE were being counted as "notes", polluting the counter and
# la courbe metrics.jsonl. cf. [[scan-skip-par-segment-pas-substring]]
SKIP_DIRS = {".git", "node_modules", "capsule", "corpus", "audits", "state"}
SKIP_PREFIX = ("sessions",)   # the whole archive/timeline layer (not woven knowledge)
# tokens that appear as [[...]] but are doc EXAMPLES, not links
# Bilingual on purpose: these are placeholder link names used in documentation,
# and users write their notes in their own language.
EXAMPLE_WHITELIST = {"slug", "name", "link", "links", "another-note", "examples",
                     "nom-du-fichier", "exemples", "lien", "liens",
                     "...", "class", "defined", "x", "their-name"}
INDEX_EXEMPT = {"MEMORY", "README", "TIMELINE"}


def md_files():
    out = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if any(rel.startswith(pre) for pre in SKIP_PREFIX):
            continue
        parts = rel.split(os.sep)[:-1]          # segments de DOSSIER (hors nom de fichier)
        if any(d in parts for d in SKIP_DIRS):
            continue
        out.append(p)
    return out


def strip_code(text):
    """Strips ``` blocks and `inline` spans so documentation examples are not read as links."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    return text


def extract_links(text):
    return set(re.findall(r"\[\[([^\]|]+)", strip_code(text)))


def read(p):
    try:
        return open(p, encoding="utf-8").read()
    except Exception:
        return ""


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^(\w[\w.]*?):\s*(.*)$", line.strip())
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"')
    return fm


def main():
    files = md_files()
    checked_files = [
        f for f in files if os.path.relpath(f, BRAIN) not in STRUCTURAL_MAPS
    ]
    slugs = {os.path.splitext(os.path.basename(f))[0] for f in files}
    memory = read(MEMORY) + "\n" + read(LESSONS_INDEX)

    all_links = set()
    problems = {"dead_links": [], "orphans": [], "frontmatter": [],
                "naming": [], "off_index": [], "memory_too_heavy": [],
                "unknown_type": [], "unknown_relation": [], "vocabulary_unreachable": [],
                # Counted as a real defect: a dirty engine silently blocks every
                # future update. An unversioned trunk is reported too, but NOT
                # counted — it is a legitimate choice, only an undisclosed one.
                "engine_dirty": []}

    # A vocabulary we could not reach means a check DID NOT RUN. Saying so is the whole
    # difference between "nothing to report" and "I did not look": a guard that goes
    # quiet when its reference disappears reports a clean trunk for ever.
    if VALID_TYPES is None:
        problems["vocabulary_unreachable"].append(
            "metadata.type — hooks/on_fiche_write.py unreadable, check 8 SKIPPED")
    if RELATION_TYPES is None:
        problems["vocabulary_unreachable"].append(
            "relations — hooks/graph_export.py unreadable, check 9 SKIPPED")

    # Structural maps contribute the links they carry, without themselves becoming
    # notes subject to the frontmatter/naming invariants.
    for f in files:
        txt = read(f)
        all_links |= extract_links(txt)

    # 1. dead links
    for l in sorted(all_links):
        if l in slugs or l in EXAMPLE_WHITELIST:
            continue
        problems["dead_links"].append(l)

    for f in checked_files:
        rel = os.path.relpath(f, BRAIN)
        base = os.path.splitext(os.path.basename(f))[0]
        zone = rel.split(os.sep)[0]
        txt = read(f)

        # 3+4. front matter & naming (woven areas only)
        if zone in LINKED_DIRS:
            fm = frontmatter(txt)
            if fm is None:
                problems["frontmatter"].append(f"{rel}: no front matter")
            else:
                if not fm.get("name"):
                    problems["frontmatter"].append(f"{rel} : 'name' manquant")
                elif fm["name"] != base:
                    problems["frontmatter"].append(f"{rel} : name='{fm['name']}' ≠ fichier '{base}'")
                if not fm.get("description"):
                    problems["frontmatter"].append(f"{rel} : 'description' manquante")
            if not re.fullmatch(r"[a-z0-9-]+", base):
                problems["naming"].append(f"{rel}: '{base}' is not kebab-case")

            # 8. a type outside the vocabulary the write hook enforces. The hook records
            # this at write time; doctor catches the notes that never went through it —
            # a git clone, a restore, an agent writing around the tool.
            if VALID_TYPES is not None and fm:
                t = fm.get("type")
                if t and t not in VALID_TYPES:
                    problems["unknown_type"].append(f"{rel} : type='{t}'")

            # 9. a typed relation the exporter would drop. Same parser, same vocabulary
            # as graph_export: an unknown type is not refused there, it is dropped in
            # SILENCE, and the qualified link disappears from the map as if never written.
            if RELATION_TYPES is not None:
                head = re.match(r"^---\n(.*?)\n---", txt, re.S)
                block = _REL_BLOCK.search(head.group(1) + "\n") if head else None
                if block:
                    for typ, _targets in _REL_LINE.findall(block.group(1)):
                        if typ not in RELATION_TYPES:
                            problems["unknown_relation"].append(f"{rel} : '{typ}'")

            # 2. orphan (never targeted by a link)
            if base not in INDEX_EXEMPT and base not in all_links:
                problems["orphans"].append(base)

            # 5. presence in the map (MEMORY.md + lessons/INDEX.md)
            if base not in INDEX_EXEMPT and base not in memory and rel not in memory:
                problems["off_index"].append(base)

    # 6. loading guard: warn before the effective limit (~24.4 kB).
    try:
        memory_bytes = os.path.getsize(MEMORY)
    except OSError:
        memory_bytes = 0
    if memory_bytes > MEMORY_WARN_BYTES:
        problems["memory_too_heavy"].append(
            f"MEMORY.md: {memory_bytes} bytes > {MEMORY_WARN_BYTES}"
        )

    # 7. drift git
    drift = []
    trunk_versionne = True
    try:
        r = subprocess.run(["git", "-C", BRAIN, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        drift = [l for l in r.stdout.splitlines() if l.strip()]
        trunk_versionne = r.returncode == 0
    except Exception:
        pass

    # 8. THE TWO BLIND SPOTS THIS DIAGNOSTIC USED TO HAVE (reported 2026-08-16,
    #    Maissane Lagsir). Both were invisible precisely when they mattered, and
    #    `brain doctor` is the output users are asked to paste into a bug report.
    #
    #    (a) THE ENGINE'S OWN WORKTREE. The gardening agents reach engine files
    #        through the symlinks mounted in the trunk, and dirty the engine repo.
    #        `cbrain/update.sh` then refuses to update a dirty engine — so the user
    #        silently falls behind for ever. Doctor looked only at the TRUNK, came
    #        back fully green, and could not see the one thing that was stuck.
    #
    #    (b) AN UNVERSIONED TRUNK. `hooks/commit_par_zone.py` treats it as "the
    #        normal case: nobody ran git init" and returns quietly. Consequence:
    #        the per-zone auto-save runs at the end of every session and saves
    #        NOTHING. Observed on a real install: three days, 23 notes, no history,
    #        no way back if an agent overwrites a note. It is a legitimate choice,
    #        but it must be a CHOICE — not a silent default nobody was told about.
    moteur_sale = []
    engine = os.path.realpath(os.path.expanduser("~/.c-brain/engine"))
    if os.path.isdir(engine) and os.path.realpath(engine) != BRAIN:
        try:
            r = subprocess.run(["git", "-C", engine, "status", "--porcelain",
                                "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10)
            moteur_sale = [l for l in r.stdout.splitlines() if l.strip()]
        except Exception:
            pass

    problems["engine_dirty"] = [l.split()[-1] for l in moteur_sale]

    total = sum(len(v) for v in problems.values())
    report = {"ok": total == 0, "total": total, "notes": len(checked_files),
              "trunk_versioned": trunk_versionne,
              "links": len(all_links), "memory_bytes": memory_bytes,
              "drift_git": len(drift), **problems}

    if "--json" in sys.argv:
        try:
            os.makedirs(os.path.join(BRAIN, "state"), exist_ok=True)
            json.dump(report, open(os.path.join(BRAIN, "state", "doctor.json"), "w"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass
        # historisation : une ligne compacte par run → tendance lisible dans le temps
        try:
            import time
            lessons = len([f for f in checked_files if os.path.relpath(f, BRAIN).startswith("lessons")])
            metric = {"ts": int(time.time()), "notes": len(checked_files), "lecons": lessons,
                      "links": len(all_links), "dead_links": len(problems["dead_links"]),
                      "orphans": len(problems["orphans"]),
                      "off_index": len(problems["off_index"]), "ok": report["ok"]}
            with open(os.path.join(BRAIN, "state", "metrics.jsonl"), "a", encoding="utf-8") as mf:
                mf.write(json.dumps(metric, ensure_ascii=False) + "\n")
        except Exception:
            pass

    if "--quiet" not in sys.argv and "--json" not in sys.argv:
        ico = "✅" if report["ok"] else "⚠️"
        print(f"{ico} brain_doctor — {len(files)} notes, {len(all_links)} links, "
              f"{len(drift)} uncommitted change(s)")
        labels = {"dead_links": "Dead links", "orphans": "Orphans",
                  "frontmatter": "Front matter", "naming": "Naming",
                  "off_index": "Off-map",
                  "memory_too_heavy": "MEMORY.md too heavy",
                  "unknown_type": "Unknown metadata.type",
                  "unknown_relation": "Relation the exporter would drop",
                  "vocabulary_unreachable": "Check SKIPPED"}
        for k, lab in labels.items():
            if problems[k]:
                print(f"  ⚠️  {lab} ({len(problems[k])}): " + ", ".join(map(str, problems[k][:12])))

        # The engine is a different repository. Its dirt is not a tidiness issue:
        # it is what stops updates from ever arriving, without saying so.
        if problems["engine_dirty"]:
            print(f"  ⚠️  Engine modified ({len(problems['engine_dirty'])}): "
                  + ", ".join(problems["engine_dirty"][:8]))
            print("      → this BLOCKS every future update (update.sh refuses a dirty engine).")
            print("      → if a gardening agent did it, it is not your work:")
            print("        git -C ~/.c-brain/engine checkout -- .")

        # Advisory, never counted: nothing is broken, but a feature the user believes
        # is running is in fact saving nothing.
        if not trunk_versionne:
            print("  ℹ️  Trunk not under git — per-zone auto-save is INERT.")
            print("      It runs at the end of every session and saves nothing:")
            print("      no history, no way back if an agent overwrites a note.")
            print("      → turn it on:  git -C ~/.c-brain/trunk init")

        if report["ok"] and trunk_versionne:
            print("  Nothing to report — the tree is consistent.")

    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
