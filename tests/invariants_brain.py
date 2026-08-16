#!/usr/bin/env python3
"""C Brain invariants — relations that must stay true, not special cases.

Each test states a RELATION between two halves of the system that, read separately,
look right. Run: python3 tests/invariants_brain.py   (rc != 0 when an invariant breaks)

Born of a real audit: the challenger's sensor counted `len(coherence.json)`
while the file can hold NON-actionable entries (arbitration notes left by an
agent). The result: a sonnet agent woken every 12 h for nothing, which
preempted the architect — and a check_coherence dying on a KeyError over the same entry.
"""
import json, os, sys, unittest

# TWO DISTINCT roots, on purpose:
#  · CODE  — where the hooks to import come from. Follows the file, because the engine
#    can live somewhere other than the trunk (symlink installation).
#  · BRAIN — the user's trunk, where the DATA comes from (state/).
#    Always derived from $HOME: writing into the engine would break the installation
#    and be wiped on the first update.
CODE = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BRAIN = os.path.expanduser("~/.c-brain/trunk")
sys.path.insert(0, os.path.join(CODE, "hooks"))

MALFORMED = [{"note": "✓ arbitrated, false positive", "note2": "✓ same"}]
REAL_PAIR = [{"a": "x", "b": "y", "sim": 0.9, "ts": 0, "status": "heavy overlap"}]


class SensorNeverStuck(unittest.TestCase):
    """INVARIANT: an agent is woken only when it has ACTIONABLE work.

    A sensor counting lines rather than units of work never comes back down
    → the agent relights on every cooldown, forever, doing nothing.
    """

    def _has_work(self, coherence_content):
        import brain_upkeep
        path = os.path.join(BRAIN, "state", "coherence.json")
        backup = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        try:
            json.dump(coherence_content, open(path, "w", encoding="utf-8"))
            return brain_upkeep.sensor_signal()["challenger"][0]
        finally:
            if backup is not None:
                open(path, "w", encoding="utf-8").write(backup)

    def test_non_actionable_entries_do_not_wake_the_challenger(self):
        self.assertFalse(self._has_work(MALFORMED),
                         "challenger woken on an entry with no (a,b) pair to arbitrate")

    def test_a_real_pair_does_wake_the_challenger(self):
        self.assertTrue(self._has_work(REAL_PAIR),
                        "challenger left asleep while a real pair waits for arbitration")

    def test_an_empty_sensor_wakes_nobody(self):
        self.assertFalse(self._has_work([]))


class CheckCoherenceToleratesOldEntries(unittest.TestCase):
    """INVARIANT: the detector survives any content already present in its own state.

    check_coherence RE-READS coherence.json then writes back to it. If it assumes a
    schema the existing entries do not respect, it dies — silently, because it runs
    detached — and NO overlap is ever detected again.
    """

    def test_no_keyerror_on_a_legacy_entry(self):
        import check_coherence
        for flags in (MALFORMED, REAL_PAIR, [], MALFORMED + REAL_PAIR):
            with self.subTest(flags=flags):
                try:
                    pairs = check_coherence.existing_pairs(flags)
                except Exception as e:  # noqa: BLE001
                    self.fail(f"check_coherence breaks on {flags}: {e!r}")
                self.assertIsInstance(pairs, set)


class DocsAndCodeAgree(unittest.TestCase):
    """INVARIANT: every agent that can wake autonomously is documented as such.

    An agent wired into ORDER runs with --dangerously-skip-permissions. If the docs
    call it "optional, not wired in", nobody knows it can write on its own.
    """

    SECOND_LAYER_HEADING = "## The second autonomous layer"

    def test_every_ORDER_agent_is_announced_in_the_readme(self):
        import brain_upkeep
        readme = open(os.path.join(BRAIN, "agents", "README.md"), encoding="utf-8").read()
        self.assertIn(self.SECOND_LAYER_HEADING, readme,
                      "the watch section heading has moved — the split below would silently "
                      "return the WHOLE readme and the test would stop testing anything")
        block = readme.split(self.SECOND_LAYER_HEADING)[-1]
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, block,
                          f"{agent} wakes autonomously but is missing from the watch documentation")

    def test_every_ORDER_agent_has_a_model_and_a_task(self):
        import brain_upkeep
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, brain_upkeep.MODEL, f"{agent} has no model → a silent default")
            self.assertIn(agent, brain_upkeep.TASKS, f"{agent} has no mission → KeyError on wake-up")


class ModelPerAgentLayerOne(unittest.TestCase):
    """INVARIANT: the creative stage (distiller) is never given a weaker model than the
    mechanical one (gardener). A failed distillation loses knowledge PERMANENTLY;
    a failed gardening pass simply replays."""

    RANK = {"haiku": 0, "sonnet": 1, "opus": 2}

    def test_distiller_at_least_as_strong_as_gardener(self):
        src = open(os.path.join(BRAIN, "hooks", "auto_maintain.py"), encoding="utf-8").read()
        self.assertIn("MODEL_L1", src, "the model is hardcoded, not configurable per agent")
        ns = {}
        for line in src.splitlines():
            if line.strip().startswith("MODEL_L1"):
                exec(line.strip(), {}, ns)  # noqa: S102
        m = ns["MODEL_L1"]
        self.assertGreaterEqual(self.RANK[m["distiller"]], self.RANK[m["gardener"]],
                                "the distiller (irreversible) runs below the gardener (replayable)")


class ComposedMapWithoutPollution(unittest.TestCase):
    """INVARIANT: the secondary index lightens startup without becoming knowledge."""

    REL_INDEX = os.path.join("lessons", "INDEX.md")

    def test_memory_keeps_its_loading_margin(self):
        import brain_doctor
        size = os.path.getsize(os.path.join(BRAIN, "MEMORY.md"))
        self.assertLessEqual(size, brain_doctor.MEMORY_WARN_BYTES)

    def test_structural_index_is_excluded_from_the_knowledge_engines(self):
        import brain_recall
        import brain_topology
        import brain_utility
        import track_read
        self.assertTrue(brain_recall._skip(self.REL_INDEX))
        self.assertIn(self.REL_INDEX, brain_topology.STRUCTURAL_MAPS)
        self.assertIn(self.REL_INDEX, brain_utility.STRUCTURAL_MAPS)
        self.assertIn(self.REL_INDEX, track_read.STRUCTURAL_MAPS)

    def test_infra_catalogues_are_excluded_from_recall(self):
        import brain_recall
        for rel in ("agents/gardener.md", "state/to-validate.md",
                    "capsule-v2/README.md", self.REL_INDEX):
            with self.subTest(rel=rel):
                self.assertTrue(brain_recall._skip(rel))


class ContextSignal(unittest.TestCase):
    """INVARIANT: the context warning does not depend on any recall result."""

    def test_shared_usage_sum(self):
        import context_usage
        self.assertEqual(context_usage.usage_tokens({
            "input_tokens": 10,
            "cache_read_input_tokens": 20,
            "cache_creation_input_tokens": 30,
        }), 60)

    def test_warns_strictly_above_300k(self):
        import inject_recall
        original = inject_recall.read_context_tokens
        try:
            inject_recall.read_context_tokens = lambda _path: 300_000
            self.assertIsNone(inject_recall.context_notice({"transcript_path": "x"}))
            inject_recall.read_context_tokens = lambda _path: 300_001
            self.assertIn("300k tokens", inject_recall.context_notice({"transcript_path": "x"}))
        finally:
            inject_recall.read_context_tokens = original


class WritingAgentsKnowTheEngineIsOffLimits(unittest.TestCase):
    """INVARIANT: every agent that can WRITE knows the engine's files are not notes.

    THE BUG (2026-08-16, Maissane Lagsir). `install.sh` mounts `agents/`, `hooks/`,
    `capsule/`, `planet/`, `companion/` and `tests/` inside the trunk as symlinks into
    the ENGINE's git repository. Nothing told the gardening agents, so the architect
    wove `[[...]]` links into the agent briefs — its exact job, done to the wrong repo.
    That closed a loop: each pass dirtied the engine, `update.sh` refuses to update a
    dirty engine, and the install fell behind for ever without a signal.

    WHY THIS TEST AND NOT JUST THE PROSE. The fix is the same paragraph in FIVE briefs.
    A rule copied five times drifts — this repository watched exactly that happen the
    same day, with two recall engines that had silently disagreed on 65 documents. So
    the copies are compared to each other, and to the canonical path list they cite.
    """

    AGENTS_QUI_ECRIVENT = ("architect", "archivist", "distiller", "gardener", "synthesizer")
    ANCRE = "The engine's files are NOT note content"

    def _brief(self, nom):
        with open(os.path.join(CODE, "agents", f"{nom}.md"), encoding="utf-8") as f:
            return f.read()

    def test_every_writing_agent_carries_the_rule(self):
        for nom in self.AGENTS_QUI_ECRIVENT:
            self.assertIn(self.ANCRE, self._brief(nom),
                          f"{nom}.md can write but was never told the engine is off-limits")

    def test_the_rule_is_identical_everywhere(self):
        """Five copies that have drifted are five different rules."""
        def extraire(txt):
            i = txt.index(self.ANCRE)
            fin = txt.find("\n## ", i)
            return txt[i:fin if fin != -1 else len(txt)].strip()

        versions = {nom: extraire(self._brief(nom)) for nom in self.AGENTS_QUI_ECRIVENT}
        distinctes = set(versions.values())
        self.assertEqual(len(distinctes), 1,
                         "the rule has drifted between briefs: "
                         + ", ".join(sorted(versions)))

    def test_the_rule_matches_the_canonical_path_list(self):
        """The briefs must not name a set of directories the installer no longer mounts."""
        liste = os.path.join(CODE, "cbrain", "engine-paths.txt")
        self.assertTrue(os.path.exists(liste), "cbrain/engine-paths.txt is missing")
        with open(liste, encoding="utf-8") as f:
            attendus = [l.strip() for l in f
                        if l.strip() and not l.lstrip().startswith("#")]
        brief = self._brief("architect")
        for d in attendus:
            self.assertIn(f"`{d}/`", brief,
                          f"{d}/ is mounted into the trunk but the rule never names it")

    def test_the_mechanic_still_carries_the_mirror_rule(self):
        """The separation of powers only holds if BOTH halves are written."""
        self.assertIn("You do NOT touch note content", self._brief("mechanic"))


class ResumeDetectorStaysAudible(unittest.TestCase):
    """INVARIANT: the resume-point detector still FINDS a real resume point.

    WHY THIS GUARD LANDS BEFORE THE FILTER IT GUARDS. The French branch narrows
    `best_marker` so a struck-through or negated marker stops counting as work to
    resume ("nothing left to do", "~~to resume~~ — ABANDONED"). Measured here on
    2026-08-16, this engine reports 6 false positives out of 6 on those sentences,
    so the filter is a real improvement and it is coming.

    But a filter that over-matches "passes" by finding NOTHING AT ALL, and a mute
    detector is the failure, not the success — it would report a clean trunk for
    ever. So the anti-mute half is installed FIRST, while the detector is still
    permissive and this test is green for the right reason. When the filter lands,
    this test is already standing behind it.

    The fixtures are French because the markers the detector matches are French —
    they are the user's notes, not this codebase's UI.
    """

    REAL_MARKERS = (
        "## RESTE À FAIRE : brancher le token Notion du compte partagé",   # i18n-ok
        "Point de reprise : finir la refonte de l'interface",              # i18n-ok
        "Réglé le lot A ; RESTE À FAIRE : le lot B",                       # i18n-ok
        "## À faire\n- brancher le webhook",                               # i18n-ok
        "À faire : relancer l'export",                                     # i18n-ok
    )

    def test_a_real_resume_point_is_still_detected(self):
        import brain_anticipate as ba
        for line in self.REAL_MARKERS:
            self.assertIsNotNone(ba.best_marker(line),
                                 f"real resume point lost: {line!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
