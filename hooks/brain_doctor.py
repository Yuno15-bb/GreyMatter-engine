#!/usr/bin/env python3
"""brain_doctor — integrity healthcheck of the trunk.

Checks, without modifying anything:
  1. dead [[x]] links (EXCLUDING doc examples and code blocks),
  2. orphan notes (never targeted by a link),
  3. complete front matter (name / description / metadata.type) and name == file name,
  4. kebab-case naming convention,
  5. presence in the map: MEMORY.md + lessons/INDEX.md,
  6. MEMORY.md size under the safe-loading threshold,
  7. git drift (uncommitted changes),
  8. a `metadata.type` outside the known vocabulary,
  9. a typed `relations:` entry the graph exporter would silently drop (and spelling drift),
 10. a typed relation that points to a note that DOES NOT EXIST,
 11. a `topic:` missing, doubled, or foreign to the trunk's meta/topics.json.

DOCTOR DIAGNOSES. IT NEVER REPAIRS, AND IT NEVER DEFINES.

Checks 8 to 11 are about vocabularies, and none of them is written here. They are
IMPORTED from the file that owns them:

    metadata.type      hooks/on_fiche_write.py   VALID_TYPES
    relations:         hooks/graph_export.py     RELATION_TYPES  (+ its own parser)
    topic:             hooks/topics_fiche.py     which reads meta/topics.json on every call

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

Usage:
  brain_doctor.py            → readable report + exit 0 (healthy) / 1 (anomalies)
  brain_doctor.py --json     → writes state/doctor.json (for the hooks) + exit code
  brain_doctor.py --quiet    → exit code only
"""
import os, re, sys, json, subprocess, glob, difflib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from identite_fiche import identite, scanner   # noqa: E402

# The two vocabularies, imported from the files that OWN them — never restated here.
# Guarded: a doctor that cannot run because a hook moved would be worse than a doctor
# that reports one check less. When a vocabulary cannot be reached, the corresponding
# check is skipped and SAYS SO, rather than passing silently on an empty set.
try:
    from on_fiche_write import VALID_TYPES
except Exception:
    VALID_TYPES = None
try:
    from graph_export import RELATION_TYPES, _REL_BLOCK, raw_relations
except Exception:
    RELATION_TYPES = _REL_BLOCK = raw_relations = None
# The topics live in the TRUNK (meta/topics.json), read by their single reader. A trunk
# without that file has simply not adopted topics: the check is then SKIPPED AND SAID,
# never counted as a fault — same rule as graph_export. A file that exists but cannot be
# read is a check that did not run, and that one is counted.
try:
    import topics_fiche
    TOPIC_IDS = topics_fiche.ids_canoniques() if os.path.exists(topics_fiche.SOURCE) else None
    TOPICS_ERROR = None
except Exception as e:
    topics_fiche = TOPIC_IDS = None
    TOPICS_ERROR = str(e)

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
LESSONS_INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")
# ⚠ TWO LIMITS, NOT ONE — and the FIRST ONE REACHED cuts, silently.
#   Measured on 2026-08-25 on harness 2.1.245 (protocol: a test map under a SEPARATE
#   project key, a sentinel on the last line, observable = the model quotes the sentinel
#   or does not):
#     · 200 lines pass, 201 truncate — WHATEVER the size;
#     · 24,000 bytes pass, 30,000 truncate (the harness publishes "limit: 24.4KB";
#       the exact byte boundary was never measured, do not write it down as a fact).
#   The harness warning is visible ONLY to the model: never an exit code, never a
#   refusal. Hence these two thresholds, with the same margin on both sides,
#   ~17 % under the measured limit: 200 × 0.825 ≈ 165.
#   Until 2026-09-20, ONLY the size was watched. The limit that actually broke a
#   projected map was the LINE one (292 against 200): the dimension that bites was
#   modelled nowhere, and raising the byte threshold alone would have kept the guard
#   green on a map that was really truncated.
MEMORY_WARN_BYTES = 20_000
MEMORY_WARN_LINES = 165
# ⚠ AND THE CEILING BELONGS TO THE HARNESS, NOT TO US: it can move from one version to
#   the next without notice, and the failure mode stays silent. The version under which
#   the two limits above were measured is therefore written here, and doctor compares
#   it with the one running. It is information, not a fault: it must never make doctor
#   exit 1, otherwise the slightest Claude Code update turns a healthy tree red and
#   nobody can honestly switch it off (ADR-0016).
MEMORY_LIMITS_MEASURED_ON = "2.1.245"


def harness_version():
    """The running Claude Code version, WITHOUT starting a process.

    `claude --version` costs a node start-up on every doctor call, and doctor runs
    inside hooks. Two file reads are enough: the native installer makes `claude` a link
    to `…/versions/<version>`, and `~/.claude.json` keeps the last version seen at
    onboarding. Returns None if neither answers — a ceiling whose harness is unknown
    is not made up.
    """
    import shutil
    exe = shutil.which("claude")
    if exe:
        try:
            target = os.path.basename(os.path.realpath(exe))
            if re.match(r"^\d+\.\d+\.\d+$", target):
                return target
        except OSError:
            pass
    try:
        with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as f:
            v = json.load(f).get("lastOnboardingVersion")
        if isinstance(v, str) and re.match(r"^\d+\.\d+\.\d+$", v):
            return v
    except (OSError, ValueError):
        pass
    return None


STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}
LINKED_DIRS = ("projects", "lessons", "life", "meta", "skills")   # the woven areas
# THE NOTES, in the sense of the two classification axes. `skills/` is left out: a
# SKILL.md comes from outside (a Claude Code convention) and was never sorted by topic.
# Asking it for a `topic:` would accuse files nobody wrote here, and the real missing
# piece would drown in those accusations.
NOTE_ZONES = ("projects", "lessons", "meta", "life")
# MEASURES THAT ARE NOT FAULTS. The rule "a topic is mandatory" and "`related_to` carries
# its reason" (ADR-0019) applies to NEW notes only. Notes written before did not break a
# rule that did not exist: turning them red would make doctor carry a false accusation
# and — worse — invite making up topics and reasons, that is, fabricating provenance.
# So these numbers are MEASURED and SHOWN, and never make doctor exit 1. The same goes
# for a harness version change: information, not a fault.
INFORMATIONAL = {"topic_missing", "related_to_without_reason", "map_ceiling_not_remeasured"}
# skip logic consistent with brain_recall/brain_embed: FOLDER segments (set) + prefixes (startswith).
# The old `"sessions/archive" in parts` (multi-segment token vs single segment) NEVER matched
# → the archive notes + TIMELINE were being counted as "notes", polluting the counter and
# the metrics.jsonl curve. cf. [[scan-skip-par-segment-pas-substring]]
SKIP_DIRS = {".git", "node_modules", "capsule", "corpus", "audits", "state",
             # `archive/` = the cold layer: its journals are not notes, and their frozen
             # [[links]] must not pollute the counter nor the dead links.
             "archive",
             # `vision/` = vision source documents (cf. brain_corpus.py): neither knowledge
             # notes nor woven by [[links]]. Counting them would skew the note counter and
             # metrics.jsonl, and ask them for a place in the map they already hold, as a
             # SOURCE and not as a note.
             "vision",
             # `references/` and `_refs/` = skills' internal resources, not notes
             "references", "_refs"}
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
        parts = rel.split(os.sep)[:-1]          # FOLDER segments (file name excluded)
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
    # THE LOGICAL IDENTITY IS NO LONGER THE FILE NAME. `skills/design/SKILL.md` is called
    # `design`: Claude Code's constraint has authority over the physical form, and it is
    # the indexer that learns. The rule lives in hooks/identite_fiche.py — one definition,
    # several importers.
    slugs = set()
    for f in files:
        slug, canonical, _ = identite(os.path.relpath(f, BRAIN))
        if slug and canonical:
            slugs.add(slug)
    # A TARGET CAN LIVE OUTSIDE THE CORPUS WITHOUT BEING DEAD. `vision/` is deliberately
    # out of recall and its documents are not notes — but they EXIST, and a note may say
    # where it comes from. Counting them dead would be a false accusation.
    outside_corpus = {os.path.basename(p)[:-3]
                      for p in glob.glob(os.path.join(BRAIN, "vision", "*.md"))}
    # COMPETING representations are reported, never indexed silently: indexing both would
    # give two identities per skill and a resolution of `[[design]]` that depends on the
    # order the disk is walked in.
    _, competing, _ = scanner(BRAIN, sorted(LINKED_DIRS))
    memory = read(MEMORY) + "\n" + read(LESSONS_INDEX)

    all_links = set()
    problems = {"dead_links": [], "orphans": [], "frontmatter": [],
                "naming": [], "off_index": [], "memory_too_heavy": [],
                "memory_too_many_lines": [], "map_ceiling_not_remeasured": [],
                "unknown_type": [], "unknown_relation": [], "vocabulary_unreachable": [],
                # two files for one logical identity: a choice to make, not a duplicate
                # to absorb. cf. hooks/identite_fiche.py
                "competing_representations": [],
                # 10/11 — Until these, nobody looked: the graph exporter dropped unknown
                # types without a word, and no instrument read a relation's TARGET. A
                # qualified link to a vanished note read as a valid link — that is, as
                # knowledge that still exists.
                "relation_dead_target": [], "related_to_without_reason": [],
                "topic_invalid": [], "topic_missing": [],
                # THE STATUS ROUND THAT STOPPED MEASURING. `etat_projets.py` runs at 8 am
                # and 7 pm, exits 0, shows its banner — and can go on doing so for weeks
                # without MEASURING anything (a launchd service denied disk access keeps,
                # quite correctly, its last complete measurement). One day is a passing
                # state; weeks are a breakdown. What turns one into the other is an AGE
                # THRESHOLD: three days, six missed measurements in a row.
                "status_round_stale": [],
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
            "relations — hooks/graph_export.py unreadable, checks 9 and 10 SKIPPED")
    if TOPICS_ERROR:
        problems["vocabulary_unreachable"].append(
            f"topic — meta/topics.json or hooks/topics_fiche.py unreadable ({TOPICS_ERROR}), "
            "check 11 SKIPPED: a made-up topic would pass")

    for slug, canonical, competitor, _reason in competing:
        problems["competing_representations"].append(
            "%s : %s (canonical %s)" % (slug, competitor, canonical or "NONE"))

    # Has the status round still been able to measure? We read the dated ARTIFACT it
    # writes, never its exit code nor its banner: both stay green through the breakdown.
    _ROUND_DAYS = 3
    _cache = os.path.join(BRAIN, "state", "project-status.json")
    try:
        import datetime as _dt
        _measured = json.load(open(_cache, encoding="utf-8")).get("measured_at")
        _age = (_dt.datetime.now() - _dt.datetime.fromisoformat(_measured)).days
        if _age >= _ROUND_DAYS:
            problems["status_round_stale"].append(
                "state/project-status.json: last COMPLETE measurement %d day(s) ago (%s) — "
                "the round runs and announces itself, but no longer writes. Likely cause: "
                "the launchd service is denied disk access to the projects folder."
                % (_age, _measured[:10]))
    except FileNotFoundError:
        pass
    except Exception as _e:
        problems["status_round_stale"].append("status round age unreadable: %s" % _e)

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
        # `base` is the LOGICAL identity. Using the file name here is exactly what broke
        # the skills: `SKILL.md` gave base="SKILL", the front matter said name="design",
        # doctor complained — and renaming the file was the only way to silence it.
        base, canonical, _reason = identite(rel)
        if base is None:
            continue                       # internal resource or tooling: not a note
        if not canonical:
            continue                       # already reported as a competing representation
        zone = rel.split(os.sep)[0]
        txt = read(f)

        # 3+4. front matter & naming (woven areas only)
        if zone in LINKED_DIRS:
            fm = frontmatter(txt)
            if fm is None:
                problems["frontmatter"].append(f"{rel}: no front matter")
            else:
                if not fm.get("name"):
                    problems["frontmatter"].append(f"{rel} : 'name' missing")
                elif fm["name"] != base:
                    problems["frontmatter"].append(f"{rel} : name='{fm['name']}' ≠ identity '{base}'")
                if not fm.get("description"):
                    problems["frontmatter"].append(f"{rel} : 'description' missing")
            if not re.fullmatch(r"[a-z0-9-]+", base):
                problems["naming"].append(f"{rel}: '{base}' is not kebab-case")

            # 8. a type outside the vocabulary the write hook enforces. The hook records
            # this at write time; doctor catches the notes that never went through it —
            # a git clone, a restore, an agent writing around the tool.
            if VALID_TYPES is not None and fm:
                t = fm.get("type")
                if t and t not in VALID_TYPES:
                    problems["unknown_type"].append(f"{rel} : type='{t}'")

            # 9/10. TYPED RELATIONS. Same parser and same vocabulary as graph_export: what
            # turns red here is EXACTLY what the map loses — an unknown type is not refused
            # there, it is dropped in SILENCE, and the qualified link disappears as if never
            # written. Unknown types count once per note, as graph_export counts them.
            # Targets are checked for EVERY type, known or not: a link that leads nowhere
            # leads nowhere whatever word qualifies it.
            if RELATION_TYPES is not None:
                head = re.match(r"^---\n(.*?)\n---", txt, re.S)
                block = _REL_BLOCK.search(head.group(1) + "\n") if head else None
                if block:
                    seen = set()
                    for typ, target, reason in raw_relations(block.group(1)):
                        if typ not in RELATION_TYPES and typ not in seen:
                            # SPELLING DRIFT: `base_on` for `based_on` is not one more type,
                            # it is the same type misspelt. Naming it avoids "settling" a
                            # vocabulary that never diverged.
                            close = difflib.get_close_matches(typ, sorted(RELATION_TYPES), 1, 0.6)
                            drift = f" (drift of '{close[0]}'?)" if close else ""
                            problems["unknown_relation"].append(f"{rel} : '{typ}'{drift}")
                            seen.add(typ)
                        if target and target not in slugs and target not in outside_corpus \
                                and target not in EXAMPLE_WHITELIST:
                            problems["relation_dead_target"].append(f"{rel} : {typ} → {target}")
                        # `related_to` is the ONLY catch-all, and it is paid for with a
                        # sentence: without it, it becomes the bare link again.
                        if typ == "related_to" and not reason:
                            problems["related_to_without_reason"].append(f"{rel} → {target}")

            # 2. orphan (never targeted by a link)
            if base not in INDEX_EXEMPT and base not in all_links:
                problems["orphans"].append(base)

            # 5. presence in the map (MEMORY.md + lessons/INDEX.md)
            #
            # `map: excluded` — a DELIBERATE absence from the start-up projection. Without
            # it, a note left out of the map by explicit decision shows up here as
            # "Off-map", and the gardener — whose golden rule is "every note is in the map"
            # and who goes first for what this report flags — inserts it into MEMORY.md.
            # The agent does its job: the defect was that no "off-map ON PURPOSE" decision
            # could be written anywhere an instrument reads it.
            #
            # ⚠️ THIS FIELD ONLY SPEAKS OF THE `MEMORY.md` MAP. It removes nothing from the
            # corpus, BM25 recall, the graph or the links: the note stays ordinary
            # knowledge, simply not required in the start-up projection.
            excluded_from_map = (fm or {}).get("map", "").strip() == "excluded"
            if base not in INDEX_EXEMPT and not excluded_from_map \
                    and base not in memory and rel not in memory:
                problems["off_index"].append(base)

            # 11. THE TOPIC. `lire` returns what is WRITTEN without guessing anything,
            # `valider` refuses; both live in topics_fiche, with the tool that writes topics.
            if zone in NOTE_ZONES and TOPIC_IDS is not None:
                topic, secondary = topics_fiche.lire(txt)
                try:
                    topics_fiche.valider(topic, secondary, TOPIC_IDS)
                except topics_fiche.SujetInvalide as e:
                    problems["topic_missing" if not topic else "topic_invalid"].append(f"{rel} : {e}")

    # 6. loading guard: warn before BOTH measured limits of the harness.
    try:
        with open(MEMORY, "rb") as _f:
            _blob = _f.read()
        memory_bytes = len(_blob)
        # the last line counts even without a final newline: it is the one truncation
        # takes first, and that is where the closing pointers go.
        memory_lines = _blob.count(b"\n") + (1 if _blob and not _blob.endswith(b"\n") else 0)
    except OSError:
        memory_bytes = memory_lines = 0
    if memory_bytes > MEMORY_WARN_BYTES:
        problems["memory_too_heavy"].append(
            f"MEMORY.md: {memory_bytes} bytes > {MEMORY_WARN_BYTES}"
        )
    if memory_lines > MEMORY_WARN_LINES:
        problems["memory_too_many_lines"].append(
            f"MEMORY.md: {memory_lines} lines > {MEMORY_WARN_LINES} "
            f"(measured limit 200 lines, SILENT truncation beyond)"
        )
    _vh = harness_version()
    if _vh and _vh != MEMORY_LIMITS_MEASURED_ON:
        problems["map_ceiling_not_remeasured"].append(
            f"limits measured under Claude Code {MEMORY_LIMITS_MEASURED_ON}, "
            f"current harness {_vh} — both thresholds rest on another version's measurement"
        )

    # 7. git drift
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
    #    a tester). Both were invisible precisely when they mattered, and
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
    #
    #    ⚠ HOW (a) IS MEASURED CHANGED ON 2026-08-17. An installed engine is no
    #    longer a git checkout — it is an immutable export under `versions/`,
    #    with no `.git` for `git status` to answer about. The oracle is now the
    #    manifest the installer wrote beside it: sha256 per file, in `shasum -c`
    #    format. A file that differs, or has gone missing, means SOMETHING WROTE
    #    TO A VERSION THAT IS SUPPOSED TO BE FROZEN — an agent through the
    #    trunk's mounts, a hand, an interrupted copy.
    #
    #    It is REPORTED AND NEVER REPAIRED. Overwriting it back to the manifest
    #    would destroy whatever got written there, which is the whole family of
    #    faults the ownership work exists to end. Doctor's job is to make it
    #    visible; deciding what to do with it is the user's.
    #
    #    A --dev engine keeps the git check: there, a dirty tree is normal work
    #    and the question "has this changed" has a different, correct answer.
    moteur_sale = []
    engine = os.path.realpath(os.path.expanduser("~/.c-brain/engine"))
    manifest = os.path.join(engine, ".cbrain-manifest")
    if os.path.isdir(engine) and engine != BRAIN:
        if os.path.isfile(manifest):
            try:
                r = subprocess.run(["shasum", "-a", "256", "-c", ".cbrain-manifest"],
                                   cwd=engine, capture_output=True, text=True,
                                   timeout=120)
                # `shasum -c` prints "<file>: FAILED" per mismatch, and
                # "<file>: FAILED open or read" for one that has disappeared.
                moteur_sale = [l.rsplit(":", 1)[0] for l in r.stdout.splitlines()
                               if l.strip().endswith("FAILED")
                               or l.strip().endswith("FAILED open or read")]
            except Exception:
                pass
        else:
            try:
                r = subprocess.run(["git", "-C", engine, "status", "--porcelain",
                                    "--untracked-files=no"],
                                   capture_output=True, text=True, timeout=10)
                moteur_sale = [l.split()[-1] for l in r.stdout.splitlines() if l.strip()]
            except Exception:
                pass

    problems["engine_dirty"] = moteur_sale

    total = sum(len(v) for k, v in problems.items() if k not in INFORMATIONAL)
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
        # history: one compact line per run → a trend readable over time
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
                  "relation_dead_target": "Relation to a note that does not exist",
                  "related_to_without_reason": "related_to without its reason (measure only)",
                  "topic_invalid": "Topic unknown to meta/topics.json, or doubled",
                  "topic_missing": "No topic (measure only)",
                  "competing_representations": "Competing representations",
                  "memory_too_many_lines": "MEMORY.md too many lines",
                  "map_ceiling_not_remeasured": "Loading ceiling measured under another harness",
                  "status_round_stale": "Status round: no complete measurement any more",
                  "vocabulary_unreachable": "Check SKIPPED"}
        for k, lab in labels.items():
            if problems[k]:
                ico_k = "ℹ️ " if k in INFORMATIONAL else "⚠️ "
                # A SILENT CUT MAKES YOU BELIEVE YOU SAW EVERYTHING. Measured: 58 front
                # matter complaints, 57 from a single identity defect, and the skill a test
                # sabotaged on purpose came 13th — off screen. The number in brackets is not
                # enough: it asks for a subtraction and does not say WHERE the list stops.
                # The cut is named where it cuts.
                shown = problems[k][:12]
                cut = len(problems[k]) - len(shown)
                print(f"  {ico_k} {lab} ({len(problems[k])}): " + ", ".join(map(str, shown))
                      + (f"  … +{cut} not shown" if cut else ""))
                # for relations, the COUNT PER TYPE says whether it is a mass drift
                # or three isolated cases.
                if k == "unknown_relation":
                    per_type = {}
                    for x in problems[k]:
                        t = re.search(r"'([^']+)'", x)
                        if t:
                            per_type[t.group(1)] = per_type.get(t.group(1), 0) + 1
                    print("        per type: " + ", ".join(
                        f"{t} × {n}" for t, n in sorted(per_type.items(), key=lambda i: -i[1])))
        if TOPIC_IDS is None and not TOPICS_ERROR:
            print("  ℹ️  No meta/topics.json in this trunk — check 11 (topics) not set up.")

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
            print("      Resume points are OFF too: they are ranked by commit date.")
            print("      → turn it on:  git -C ~/.c-brain/trunk init")

        if report["ok"] and trunk_versionne:
            print("  Nothing to report — the tree is consistent.")

    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
