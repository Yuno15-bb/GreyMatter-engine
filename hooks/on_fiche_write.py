#!/usr/bin/env python3
"""
PostToolUse (Write|Edit) hook — the instant mechanical guard.
On EVERY note landing in the trunk, with no LLM, no loop and no blocking:
  1. masks any plaintext secret
  2. checks that the note is on the MEMORY.md + lessons/INDEX.md map
     (otherwise -> state/a-classer.md; the map itself is never written here, ADR-0015)
  3. reports a missing front matter

Loop guard: this script edits files through direct Python I/O (not through the
Write/Edit tool), so it never re-triggers the hook. The semantic work
(dedup, refiling, distillation) stays with the gardener and distiller agents.

Golden rule: NEVER block. Always exits 0.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status
except Exception:
    def write_status(*a, **k): pass

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
LESSONS_INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")
MAP_RELS = {"MEMORY.md", os.path.join("lessons", "INDEX.md")}

# The `metadata.type` vocabulary. THESE FOUR ARE NOT CHOSEN HERE: they are the ones the
# writing agents are told to use, in agents/*.md ("type: user | feedback | project |
# reference"). tests/type_vocabulary.py compares the two lists so they cannot drift — a
# vocabulary written down twice is a vocabulary that will disagree with itself.
#
# WHY ONLY LOG, NEVER REFUSE. This hook's golden rule is that it never blocks. An unknown
# type is almost always a typo or an invention, not a catastrophe; what costs is that it
# passes IN SILENCE and nobody ever learns the note is mistyped. So it is recorded, and
# the status line says it once.
#
# `lesson` was added on 2026-08-17, WITH the briefs, in one commit — and not on the
# grounds the French branch gave for it. Its argument was that 205 of its notes live in
# lessons/, which is an argument about a FOLDER: it would have made this vocabulary a
# second name for the filing, and the two dimensions would have been impossible to tell
# apart afterwards.
#
# The measurement that settles it, taken on a 400-note trunk, is the one INSIDE that
# folder. lessons/ holds four types at once:
#
#     feedback 121 · lesson 67 · reference 54 · project 1
#
# So the folder is not the type: a majority of what sits in lessons/ is NOT a lesson. What
# the author sustains, across 188 notes in the same folder, is the distinction between
# what the user TOLD them (`feedback`) and what was learned by measuring (`lesson`) — an
# origin, which is exactly the kind of thing the other four express. That is a category,
# not a shelf, and it is why a fifth word is warranted where a folder name would not be.
#
# A note found by the natural path — write a lesson in lessons/, type it `lesson` — was
# reported by `brain doctor` as mistyped, on a trunk that ships a lessons/ folder and
# agents that talk about lessons. A check that fires on a correct value is a check people
# learn to ignore, which is what tests/type_vocabulary.py exists to prevent.
VALID_TYPES = {"user", "feedback", "project", "reference", "lesson"}

SECRET = re.compile(
    r'(ntn_[A-Za-z0-9]+|sk-ant-[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+|secret_[A-Za-z0-9]+'
    r'|eyJ[A-Za-z0-9_.-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})'
)

def get_target(data):
    ti = (data or {}).get("tool_input", {}) or {}
    return ti.get("file_path") or ti.get("path")

def main(data):
    fp = get_target(data)
    if not fp:
        return
    real = os.path.realpath(fp)
    # uniquement les fiches du tronc
    if not real.startswith(BRAIN + os.sep):
        return
    rel = os.path.relpath(real, BRAIN)

    # --- status pulse for the capsule (any activity on the tree) ---
    name = os.path.basename(rel)[:-3] if rel.endswith(".md") else os.path.basename(rel)
    if rel in MAP_RELS:
        write_status("busy", "mapping", "updating the map")
    elif rel.endswith(".md") and not rel.startswith("sessions" + os.sep):
        write_status("busy", "filing", name)

    # exclude the map itself, the automatic archive, and non-.md files from the mechanical work
    if rel in MAP_RELS or rel.startswith("sessions" + os.sep) or not rel.endswith(".md"):
        return
    if not os.path.exists(real):
        return
    try:
        txt = open(real, encoding="utf-8").read()
    except Exception:
        return

    # --- LEDGER « sauvegardes manuelles » (anti-redondance distillateur) ---
    # If YOU (the live session, not the headless gardener) write or refine a knowledge note,
    # we record it by session_id. At SessionEnd the distiller is told "do not recreate these notes"
    # → it does not redo work already done by hand (tokens saved, zero duplicates), while still
    # keeping the automatic net for knowledge NOT saved. Foreground only, knowledge areas only.
    if os.environ.get("CLAUDE_BRAIN_GARDENING") != "1":
        sid = (data or {}).get("session_id")
        if sid and rel.split(os.sep)[0] in ("projects", "lessons", "meta", "life"):
            try:
                import time
                led = os.path.join(BRAIN, "state", "manual-saves.jsonl")
                os.makedirs(os.path.dirname(led), exist_ok=True)
                with open(led, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": int(time.time()), "sid": sid, "path": rel},
                                       ensure_ascii=False) + "\n")
            except Exception:
                pass

    # coherence detection: flags overlapping notes, detached
    try:
        import subprocess
        cc = os.path.join(BRAIN, "hooks", "check_coherence.py")
        if os.path.exists(cc):
            subprocess.Popen([sys.executable, cc, real],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

    # --- 1. masquage des secrets (in place, I/O direct) ---
    masked = SECRET.sub("«SECRET-MASKED»", txt)
    if masked != txt:
        try:
            open(real, "w", encoding="utf-8").write(masked)
            txt = masked
            write_status("busy", "correcting", f"secret masked in {name}")
        except Exception:
            pass

    # slug / name used to detect presence on the map
    m = re.search(r'^name:\s*(.+)$', txt, re.M)
    slug = m.group(1).strip() if m else None
    fname = os.path.basename(rel)[:-3]

    # --- 1 bis. an unknown `type:` is recorded, never refused ---
    try:
        mt = re.search(r'^\s*type:\s*(\S+)\s*$', txt[:1200], re.M)
        if mt and mt.group(1) not in VALID_TYPES:
            import time
            with open(os.path.join(BRAIN, "state", "unknown-types.jsonl"),
                      "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": int(time.time()), "path": rel,
                                    "type": mt.group(1)}, ensure_ascii=False) + "\n")
            write_status("busy", "correcting", f"unknown type '{mt.group(1)}' in {fname}")
    except Exception:
        pass        # never block: a wobbly frontmatter must not cost a note its save

    # --- 1 ter. ADR-0019 vocabulary: OBSERVE AT WRITE TIME, never block ---
    # Decided by the author on 2026-09-17: the topic is mandatory on NEW notes only.
    # This rule cannot live in the doctor, which sees all 686 notes at once and would
    # accuse the 51 older ones without a topic; it lives at the ONLY moment where "new"
    # means something — when the note is written. Same shape as check 1 bis just above:
    # we record, we do not fix, we do not block.
    #
    # The vocabulary is not copied, it is IMPORTED: `TYPES_RELATION` and its reader
    # come from hooks/graph_export.py, the 12 topics from meta/topics.json via topics_fiche.
    # A third copy would be a third thing to drift apart — exactly the drift ADR-0019
    # just measured (309 qualified links out of 563 silently dropped).
    #
    # THIS JOURNAL HAS A NAMED READER, and that is the condition for writing it: ADR-0019
    # sets as a refutable hypothesis that forcing `related_to` to carry its reason produces
    # reasons actually written. The experiment that refutes it is "count, two weeks after
    # 17/09, the notes written AFTER that date that break the rule" — and only a journal
    # dated at write time can tell those notes apart from the older ones.
    if rel.split(os.sep)[0] in ("projects", "lessons", "meta", "life"):
        try:
            import time
            import topics_fiche
            from graph_export import TYPES_RELATION, _REL_BLOC, relations_brutes
            fm = re.match(r"^---\n(.*?)\n---", txt, re.S)
            ecarts = []
            if fm:
                topic, secondaires = topics_fiche.lire(txt)
                if not topic:
                    ecarts.append({"field": "topic", "gap": "missing"})
                elif isinstance(topic, list):     # `topic:` key written twice — see topics_fiche.lire
                    ecarts.append({"field": "topic", "gap": "duplicated", "value": ", ".join(topic)})
                elif topic not in topics_fiche.ids_canoniques():
                    ecarts.append({"field": "topic", "gap": "off-vocabulary", "value": topic})
                bloc_rel = _REL_BLOC.search(fm.group(1) + "\n")
                if bloc_rel:
                    for typ, cible, raison in relations_brutes(bloc_rel.group(1)):
                        if typ not in TYPES_RELATION:
                            ecarts.append({"field": "relation", "gap": "type-off-vocabulary",
                                           "value": typ, "target": cible})
                        elif typ == "related_to" and not raison:
                            ecarts.append({"field": "relation", "gap": "related_to-without-reason",
                                           "target": cible})
            if ecarts:
                journal = os.path.join(BRAIN, "state", "vocabulary-at-write.jsonl")
                os.makedirs(os.path.dirname(journal), exist_ok=True)
                with open(journal, "a", encoding="utf-8") as f:
                    for e in ecarts:
                        f.write(json.dumps(dict(e, ts=int(time.time()), path=rel),
                                           ensure_ascii=False) + "\n")
                premier = ecarts[0]
                write_status("busy", "correcting",
                             f"{premier['field']} {premier['gap']} in {fname}")
        except Exception:
            pass

    # --- 2. guarantee presence on the composed map ---
    try:
        mem = open(MEMORY, encoding="utf-8").read()
    except Exception:
        return
    try:
        lessons_index = open(LESSONS_INDEX, encoding="utf-8").read()
    except Exception:
        lessons_index = ""  # migration/recovery fallback: the Inbox stays functional
    card = mem + "\n" + lessons_index
    linked = (rel in card) or (fname in card) or (slug and f"[[{slug}]]" in card) \
             or (slug and f"({rel})" in card)
    # THE QUEUE IS NO LONGER IN MEMORY.md (2026-09-15). The Inbox dates from 21/06, before
    # two decisions that made it impossible: the map's 20,000-byte budget, and ADR-0015
    # (the manifest is authoritative, every map entry is validated by a human).
    # Measured on 15/09 on a copy: MEMORY.md 90 bytes under budget, ONE Inbox line pushed
    # it to 20,003 bytes and the pre-commit refused every commit, in every zone.
    # So the note waits in state/a-classer.md; the gardener PROPOSES its place in
    # state/a-valider.md; a human writes it into the map and reconciles the manifest.
    # No more race with the gardener (it no longer touches the map): the drop also holds
    # during a maintenance pass, otherwise notes written by a robot would be lost from view.
    if not linked:
        a_classer = os.path.join(BRAIN, "state", "a-classer.md")
        deja = ""
        for p in (a_classer, os.path.join(BRAIN, "state", "a-valider.md")):
            try:
                deja += open(p, encoding="utf-8").read()
            except Exception:
                pass
        if f"({rel})" not in deja:
            title = slug or fname
            try:
                os.makedirs(os.path.dirname(a_classer), exist_ok=True)
                with open(a_classer, "a", encoding="utf-8") as f:
                    f.write(f"- [{title}]({rel}) — not on the map yet\n")
            except Exception:
                pass

def refresh_doctor():
    """Refreshes state/doctor.json in the background (detached, never blocking)."""
    try:
        import subprocess
        doc = os.path.join(BRAIN, "hooks", "brain_doctor.py")
        if os.path.exists(doc):
            subprocess.Popen([sys.executable, doc, "--json"],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

def refresh_planet():
    """Regenerates planet/graph.json — the knowledge PLANET grows in real time
    with every note written (detached, never blocking)."""
    try:
        import subprocess
        ge = os.path.join(BRAIN, "hooks", "graph_export.py")
        if os.path.exists(ge):
            subprocess.Popen([sys.executable, ge],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    fp = get_target(data)
    in_brain = bool(fp) and os.path.realpath(fp).startswith(BRAIN + os.sep)
    try:
        main(data)
    except Exception:
        pass
    # refresh the artefacts (doctor.json + planet/graph.json) ONLY for a write INSIDE
    # the trunk. Before, the hook being global (Write|Edit), EVERY edit in any project
    # triggered two full scans of the trunk and appended a line to metrics.jsonl (over-frequency +
    # a polluted curve). We gate on belonging to the trunk.
    if in_brain:
        try:
            refresh_doctor()
        except Exception:
            pass
        try:
            refresh_planet()
        except Exception:
            pass
    sys.exit(0)
