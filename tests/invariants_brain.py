
"""Relationship checks for behaviors that must stay consistent."""
import json, os, sys, unittest







CODE = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BRAIN = os.path.expanduser("~/.c-brain/trunk")











try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
    import i2_profil
    i2_profil.demarrer(
        "invariants_brain",
        ordre=["`state/` must exist; golden_recall creates it as a side effect "
               "earlier in the pre-commit loop"],
        mutations=["state/coherence.json — modified then restored; residue is possible "
                   "if the process is killed between the two (unmeasured, UNKNOWN)"])
except Exception:
    pass
sys.path.insert(0, os.path.join(CODE, "hooks"))




















NOT_INSTALLED = None
if not os.path.isdir(BRAIN):
    NOT_INSTALLED = "%s does not exist — nothing is installed here" % BRAIN
elif not os.path.exists(os.path.join(BRAIN, "hooks")) \
        and not os.path.exists(os.path.join(BRAIN, "MEMORY.md")):
    NOT_INSTALLED = ("%s is not an installed trunk: no engine mounts (hooks/, "
                     "agents/) and no MEMORY.md. Run ./install.sh, or point HOME "
                     "at an installation, to measure these invariants." % BRAIN)

MALFORMED = [{"note": "✓ arbitrated, false positive", "note2": "✓ same"}]
REAL_PAIR = [{"a": "x", "b": "y", "sim": 0.9, "ts": 0, "status": "heavy overlap"}]


class SensorNeverStuck(unittest.TestCase):
    """Check invariants across Brain hooks and public interfaces."""

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
    """Check invariants across Brain hooks and public interfaces."""

    def test_no_keyerror_on_a_legacy_entry(self):
        import check_coherence
        for flags in (MALFORMED, REAL_PAIR, [], MALFORMED + REAL_PAIR):
            with self.subTest(flags=flags):
                try:
                    pairs = check_coherence.existing_pairs(flags)
                except Exception as e:
                    self.fail(f"check_coherence breaks on {flags}: {e!r}")
                self.assertIsInstance(pairs, set)


class DocsAndCodeAgree(unittest.TestCase):
    """Check invariants across Brain hooks and public interfaces."""

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

    def test_the_readme_announces_the_ship_and_mission_counts(self):
        """Check invariants across Brain hooks and public interfaces."""
        import re, robots_permissions
        desc = re.search(r"^description:\s*(.*)$",
                         open(os.path.join(BRAIN, "agents", "README.md"),
                              encoding="utf-8").read(), re.M).group(1)
        vaisseaux = sorted(set(robots_permissions.FAMILLE.values()))
        annonce = re.search(r"(four) ships.*?(eight) missions", desc, re.I)
        self.assertIsNotNone(
            annonce, "the guide no longer announces the ship and mission counts; "
                     "the count can no longer be checked")
        self.assertEqual(
            (4, 8),
            (len(vaisseaux), len(robots_permissions.FAMILLE)),
            f"the guide announces {annonce.group(1)} ships and {annonce.group(2)} "
            f"missions; the table declares {len(vaisseaux)} and "
            f"{len(robots_permissions.FAMILLE)}")
        for v in vaisseaux:
            self.assertIn(v.upper(), desc,
                          f"{v} exists but is not named in the guide")

    def test_every_ORDER_agent_has_a_model_and_a_task(self):
        import brain_upkeep
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, brain_upkeep.MODEL, f"{agent} has no model → a silent default")
            self.assertIn(agent, brain_upkeep.TASKS, f"{agent} has no mission → KeyError on wake-up")

    def test_every_called_agent_exists_on_the_surface_claude_code_reads(self):
        """Check invariants across Brain hooks and public interfaces."""
        import re
        import brain_upkeep
        appeles = set(brain_upkeep.ORDER) | set(brain_upkeep.TASKS)



        am = open(os.path.join(BRAIN, "hooks", "auto_maintain.py"), encoding="utf-8").read()
        m = re.search(r"MODEL_L1\s*=\s*\{([^}]*)\}", am)
        self.assertIsNotNone(m, "MODEL_L1 changed shape; update the check rather than bypass it")
        appeles |= set(re.findall(r'"([a-z_]+)"\s*:', m.group(1)))






        import robots_permissions
        orphelines = sorted(m for m in appeles if m not in robots_permissions.FAMILLE)
        self.assertEqual(orphelines, [],
                         "these missions are called without a ship in "
                         "robots_permissions.FAMILLE; wake-up would raise KeyError")
        appeles = {robots_permissions.FAMILLE[m] for m in appeles}

        def manquants(noms, dossier):
            return sorted(n for n in noms
                          if not os.path.isfile(os.path.join(dossier, n + ".md")))




        import tempfile
        with tempfile.TemporaryDirectory() as faux:
            for n in sorted(appeles)[1:]:
                open(os.path.join(faux, n + ".md"), "w").close()
            self.assertEqual(manquants(appeles, faux), [sorted(appeles)[0]],
                             "the detector missed the absent agent")

        surface = os.path.expanduser("~/.claude/agents")
        if not os.path.isdir(surface):
            self.skipTest("~/.claude/agents is absent; there is nothing to link on this machine")
        absents = manquants(appeles, os.path.realpath(surface))
        self.assertEqual(absents, [],
                         "these agents are CALLED but missing where Claude Code looks "
                         "(%s → %s); every wake-up will log 'agent not found'."
                         % (surface, os.path.realpath(surface)))


class ModelPerAgentLayerOne(unittest.TestCase):
    """Check invariants across Brain hooks and public interfaces."""

    RANK = {"haiku": 0, "sonnet": 1, "opus": 2}

    def test_distiller_at_least_as_strong_as_gardener(self):
        src = open(os.path.join(BRAIN, "hooks", "auto_maintain.py"), encoding="utf-8").read()
        self.assertIn("MODEL_L1", src, "the model is hardcoded, not configurable per agent")
        ns = {}
        for line in src.splitlines():
            if line.strip().startswith("MODEL_L1"):
                exec(line.strip(), {}, ns)
        m = ns["MODEL_L1"]
        self.assertGreaterEqual(self.RANK[m["distiller"]], self.RANK[m["gardener"]],
                                "the distiller (irreversible) runs below the gardener (replayable)")


class ComposedMapWithoutPollution(unittest.TestCase):
    """Check invariants across Brain hooks and public interfaces."""

    REL_INDEX = os.path.join("lessons", "INDEX.md")

    def test_memory_keeps_its_loading_margin(self):
        """Check invariants across Brain hooks and public interfaces."""
        import brain_doctor
        blob = open(os.path.join(BRAIN, "MEMORY.md"), "rb").read()
        lignes = blob.count(b"\n") + (1 if blob and not blob.endswith(b"\n") else 0)
        self.assertLessEqual(len(blob), brain_doctor.MEMORY_WARN_BYTES,
                             f"MEMORY.md is {len(blob)} bytes")
        self.assertLessEqual(lignes, brain_doctor.MEMORY_WARN_LINES,
                             f"MEMORY.md fait {lignes} lignes")

    def test_le_plafond_mesure_dit_sous_quel_harnais(self):
        """Check invariants across Brain hooks and public interfaces."""
        import brain_doctor
        self.assertRegex(brain_doctor.MEMORY_LIMITS_MEASURED_ON, r"^\d+\.\d+\.\d+$")
        self.assertIn("map_ceiling_not_remeasured", brain_doctor.INFORMATIONAL)

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
        for rel in ("agents/narcissus.md", "state/a-valider.md",
                    "capsule-v2/README.md", self.REL_INDEX):
            with self.subTest(rel=rel):
                self.assertTrue(brain_recall._skip(rel))


class ContextSignal(unittest.TestCase):
    """Check invariants across Brain hooks and public interfaces."""

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
    """Check invariants across Brain hooks and public interfaces."""

    AGENTS_QUI_ECRIVENT = ("architect", "archivist", "distiller", "gardener", "synthesizer")
    SHIP_FOR_MISSION = {"architect": "sulaco", "archivist": "sulaco",
                        "distiller": "narcissus", "gardener": "narcissus",
                        "synthesizer": "anesidora"}
    ANCRE = "The engine's files are NOT note content"

    def _brief(self, nom):
        ship = self.SHIP_FOR_MISSION.get(nom, nom)
        with open(os.path.join(CODE, "agents", f"{ship}.md"), encoding="utf-8") as f:
            return f.read()

    def test_every_writing_agent_carries_the_rule(self):
        for nom in self.AGENTS_QUI_ECRIVENT:
            self.assertIn(self.ANCRE, self._brief(nom),
                          f"{nom}.md can write but was never told the engine is off-limits")

    def test_the_rule_is_identical_everywhere(self):
        """Check invariants across Brain hooks and public interfaces."""
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
        """Check invariants across Brain hooks and public interfaces."""
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
        """Check invariants across Brain hooks and public interfaces."""
        self.assertIn("You do NOT touch note content", self._brief("nostromo"))


class ResumeDetectorStaysAudible(unittest.TestCase):
    """Check invariants across Brain hooks and public interfaces."""

    REAL_MARKERS = (
        "## RESTE À FAIRE : brancher le token Notion du compte partagé",  # i18n-ok
        "Point de reprise : finir la refonte de l'interface",  # i18n-ok
        "Réglé le lot A ; RESTE À FAIRE : le lot B",  # i18n-ok
        "## À faire\n- brancher le webhook",  # i18n-ok
        "À faire : relancer l'export",  # i18n-ok
    )

    def test_a_real_resume_point_is_still_detected(self):
        import brain_anticipate as ba
        for line in self.REAL_MARKERS:
            self.assertIsNotNone(ba.best_marker(line),
                                 f"real resume point lost: {line!r}")


class FeedbackProducerAndConsumerAgree(unittest.TestCase):
    """Check invariants across Brain hooks and public interfaces."""

    NOTE = "lessons/a-note.md"

    PROBE = r'''
import json, os, sys, time
BRAIN = os.environ["BRAIN_HOME"]
for d in ("state", "lessons"):
    os.makedirs(os.path.join(BRAIN, d), exist_ok=True)
with open(os.path.join(BRAIN, "lessons", "a-note.md"), "w", encoding="utf-8") as f:
    f.write("---\nname: a-note\ndescription: peculiar vocabulary zzyzx\n---\n\nzzyzx\n")

# One suggestion, then a read in the SAME session: that is what counts as a hit.
now = int(time.time())
with open(os.path.join(BRAIN, "state", "recall_log.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"path": "lessons/a-note.md", "sid": "s1", "ts": now}) + "\n")
with open(os.path.join(BRAIN, "state", "read_log.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"path": "lessons/a-note.md", "sid": "s1", "ts": now + 1}) + "\n")

sys.path.insert(0, os.environ["HOOKS"])
import recall_feedback as rf
utility, _ = rf.compute()
rf.write(rf.UTILITY, utility)                       # the PRODUCER, its own write path

import brain_recall as br                           # the CONSUMER, its own read path
seen = br._utility()
records = br.BM25(br.load_corpus()).rank("zzyzx", k=3)
factor = next((r["utility_factor"] for r in records
               if r["doc"]["path"] == "lessons/a-note.md"), None)
print(json.dumps({
    "produced": utility.get("lessons/a-note.md"),
    "read_back": seen.get("lessons/a-note.md"),
    "utility_factor": factor,
}))
'''

    def test_the_consumer_reads_what_the_producer_wrote(self):
        import json as _json
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as trunk:
            env = dict(os.environ, BRAIN_HOME=trunk, HOOKS=os.path.join(CODE, "hooks"))
            out = subprocess.run([sys.executable, "-c", self.PROBE],
                                 capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(out.returncode, 0, f"round trip crashed:\n{out.stderr}")
            got = _json.loads(out.stdout.strip().splitlines()[-1])

        self.assertEqual({k: got["produced"].get(k) for k in ("sugg", "hit")},
                         {"sugg": 1, "hit": 1},
                         "the producer no longer computes the {sugg, hit} shape")
        self.assertEqual(got["read_back"], got["produced"],
                         "brain_recall does not read back what recall_feedback wrote — "
                         "the file name or the record shape has drifted between them")



        self.assertIsNotNone(got["utility_factor"], "the note did not come back at all")
        self.assertEqual(got["utility_factor"], 1.0,
                         "utility_factor must remain fixed at 1.0 under ADR-0018 (M5)")


class UnePierreTombaleNestPasUneTache(unittest.TestCase):
    """Check invariants across Brain hooks and public interfaces."""

    def test_struck_through_or_negated_marker_is_not_a_resume_point(self):
        import brain_anticipate as ba
        for ligne in (
            "Le point est fermé, ce n'est plus un reste à faire.",  # i18n-ok
            "## ~~À reprendre en phase vernissage~~ — ABANDONNÉ le 13/08",  # i18n-ok
            "Aucun reste à faire sur ce lot.",  # i18n-ok
            "Il n'y a plus de point de reprise ici.",  # i18n-ok


            "✅ **TRANCHÉ le 2026-08-11 — plus rien à faire.** Les packs contenaient bien tout.",  # i18n-ok


            "Question de l'auteur : un simple repomix suffit-il à faire auditer un produit ?",  # i18n-ok
        ):
            self.assertIsNone(ba.best_marker(ligne), f"false positive: {ligne}")

    def test_a_real_resume_point_is_still_detected(self):
        """Check invariants across Brain hooks and public interfaces."""
        import brain_anticipate as ba
        for ligne in (
            "## RESTE À FAIRE : brancher le token Notion du compte partagé",  # i18n-ok
            "Point de reprise : finir la refonte de l'interface",  # i18n-ok
            "Réglé le lot A ; RESTE À FAIRE : le lot B",  # i18n-ok

            "## À faire\n- brancher le webhook",  # i18n-ok
            "À faire : relancer l'export",  # i18n-ok
        ):
            self.assertIsNotNone(ba.best_marker(ligne), f"real resume point was missed: {ligne}")

    def test_the_dashboard_does_not_detect_itself(self):
        """Check invariants across Brain hooks and public interfaces."""
        import brain_anticipate as ba
        noms = {it["path"] for it in ba.collect()}
        self.assertNotIn(os.path.join("projects", "ETAT-DES-PROJETS.md"), noms)

    def test_the_planet_badge_matches_the_brains_resume_points(self):
        """Check invariants across Brain hooks and public interfaces."""
        import json
        import brain_anticipate as ba
        chemin = os.path.join(BRAIN, "planet", "graph.json")
        if not os.path.exists(chemin):
            self.skipTest("graph.json has not been generated yet")
        with open(chemin, encoding="utf-8") as f:
            graphe = json.load(f)
        if graphe.get("reprises_indisponibles"):
            self.skipTest("badge ↻ non calculable : %s" % graphe["reprises_indisponibles"])
        # ⚠ THIS INVARIANT RUNS IN THE SELFTEST, AND THE SELFTEST IS THE UPDATE GATE. It reads a
        # FILE ON DISK that an OLDER engine may have written. Two readings are therefore not a
        # verdict on the code under test, and failing on them locks the Mac out of every release
        # — including the one that repairs the exporter (found on a blank Mac, 2026-09-26):
        #   · no `head`: the graph predates the single detector. Its badges came from a regex
        #     that lit any note merely mentioning a resume point. Comparing them proves nothing
        #     about this engine.
        #   · another `head`: the snapshot is stale. The shipped engine regenerates the graph
        #     BEFORE the session-end commit and installs no post-commit trigger, so after any
        #     commit the graph describes the previous HEAD. That is the normal state, not a fault.
        # Both are named as skips. The real inconsistency — two detectors disagreeing at the
        # SAME head — still fails below.
        if "head" not in graphe:
            self.skipTest("planet/graph.json predates the `head` field: written by an older "
                          "exporter, regenerated at the next session end")
        import subprocess
        r = subprocess.run(["git", "-C", BRAIN, "rev-parse", "HEAD"],
                           capture_output=True, text=True)
        head_courant = r.stdout.strip() if r.returncode == 0 else None
        head_graphe = graphe["head"]                 # None when the trunk is not a repository
        if head_courant != head_graphe:
            self.skipTest("planet/graph.json describes HEAD %s, the trunk is at %s: a stale "
                          "snapshot, not an inconsistency" % ((head_graphe or "none")[:12], (head_courant or "none")[:12]))
        allumes = {n["file"] for n in graphe["nodes"] if n.get("resume")}
        attendus = {it["path"] for it in ba.collect()[:ba.TOP_REPRISES]}
        self.assertEqual(allumes, attendus,
                         "the ↻ badge and startup resume list differ at THE SAME HEAD; "
                         "this is a real inconsistency, not missing capability or a stale snapshot")


if __name__ == "__main__":
    if NOT_INSTALLED:



        print("⤳ SKIPPED — these invariants measure an INSTALLED trunk.")
        print("   %s" % NOT_INSTALLED)
        print("   Nothing was measured. This is not a pass.")
        sys.exit(0)
    unittest.main(verbosity=1)
