#!/usr/bin/env python3
"""Invariants du C Brain — relations qui doivent rester vraies, pas cas particuliers.

Chaque test énonce une RELATION entre deux moitiés du système qui, lues séparément,
semblent justes. Lancer : python3 tests/invariants_brain.py   (rc != 0 si un invariant casse)

Nés de l'audit du 2026-07-10 : le capteur du challenger comptait `len(coherence.json)`
alors que le fichier peut contenir des entrées NON actionnables (notes d'arbitrage
laissées par un agent). Résultat : un agent sonnet réveillé toutes les 12 h pour rien,
qui préemptait l'architecte — et un check_coherence mort en KeyError sur la même entrée.
"""
import json, os, sys, unittest

# Deux racines DISTINCTES, et c'est volontaire :
#  · CODE  — d'où viennent les hooks à importer. Suit le fichier, car le moteur
#    peut vivre ailleurs que le tronc (installation par symlinks).
#  · BRAIN — le tronc de l'utilisateur, d'où viennent les DONNÉES (state/).
#    Toujours dérivé de $HOME : écrire dans le moteur casserait l'installation
#    et serait écrasé à la première mise à jour.
CODE = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BRAIN = os.path.expanduser("~/.c-brain/trunk")

# ── I-2 · PROFIL D'ÉTAT (lot 1, 2026-08-21) ──────────────────────────────────
# Ce banc porte DEUX faiblesses mesurées, et le lot 1 les rend VISIBLES sans les
# corriger — les corriger touche la séquence du pre-commit, différé au scellement.
#   · dépendance d'ORDRE : ROUGE si `state/` n'existe pas, VERT s'il existe même VIDE.
#     Or `state/` est créé en effet de bord par `golden_recall`, qui tourne AVANT lui
#     dans la boucle. Ce banc ne réclame cette précondition nulle part : il en hérite.
#     Déplacer golden_recall le ferait rougir sans que personne n'y touche.
#   · MUTATION : `_has_work` écrit `state/coherence.json` du Brain mesuré, lit le
#     capteur, puis restaure dans un `finally`. Contenu rendu, mtime réécrit. Le
#     `finally` couvre l'exception, pas un SIGKILL.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
    import i2_profil
    i2_profil.demarrer(
        "invariants_brain",
        ordre=["`state/` doit exister — créé en effet de bord par golden_recall, "
               "lancé avant dans la boucle du pre-commit"],
        mutations=["state/coherence.json — saboté puis restauré ; résidu possible "
                   "si le processus est tué entre les deux (non mesurable, INCONNU)"])
except Exception:
    pass
sys.path.insert(0, os.path.join(CODE, "hooks"))

MALFORMED = [{"note": "✓ arbitré, faux positif", "note2": "✓ idem"}]
REAL_PAIR = [{"a": "x", "b": "y", "sim": 0.9, "ts": 0, "status": "fort recouvrement"}]


class SensorNeverStuck(unittest.TestCase):
    """INVARIANT : un agent n'est réveillé que s'il a du travail ACTIONNABLE.

    Un capteur qui compte des lignes plutôt que des unités de travail ne redescend
    jamais → l'agent se rallume à chaque cooldown, indéfiniment, sans rien faire.
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

    def test_entrees_non_actionnables_ne_reveillent_pas_le_challenger(self):
        self.assertFalse(self._has_work(MALFORMED),
                         "challenger réveillé sur une entrée sans paire (a,b) à arbitrer")

    def test_vraie_paire_reveille_bien_le_challenger(self):
        self.assertTrue(self._has_work(REAL_PAIR),
                        "challenger endormi alors qu'une vraie paire attend un arbitrage")

    def test_capteur_vide_ne_reveille_personne(self):
        self.assertFalse(self._has_work([]))


class CheckCoherenceTolerantAuxVieillesEntrees(unittest.TestCase):
    """INVARIANT : le détecteur survit à tout contenu déjà présent dans son propre état.

    check_coherence RELIT coherence.json puis y réécrit. S'il suppose un schéma que
    les entrées existantes ne respectent pas, il meurt — silencieusement, car il est
    lancé détaché — et plus AUCUN recouvrement n'est jamais détecté.
    """

    def test_pas_de_keyerror_sur_entree_legacy(self):
        import check_coherence
        for flags in (MALFORMED, REAL_PAIR, [], MALFORMED + REAL_PAIR):
            with self.subTest(flags=flags):
                try:
                    pairs = check_coherence.existing_pairs(flags)
                except Exception as e:  # noqa: BLE001
                    self.fail(f"check_coherence casse sur {flags}: {e!r}")
                self.assertIsInstance(pairs, set)


class DocEtCodeDAccord(unittest.TestCase):
    """INVARIANT : tout agent réveillable en autonome est documenté comme tel.

    Un agent branché dans ORDER tourne avec --dangerously-skip-permissions. Si la doc
    le dit « optionnel, non branché », personne ne sait qu'il peut écrire tout seul.
    """

    def test_tout_agent_de_ORDER_est_annonce_dans_le_readme(self):
        import brain_upkeep
        readme = open(os.path.join(BRAIN, "agents", "readme.md"), encoding="utf-8").read()
        bloc = readme.split("## Seconde couche")[-1]
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, bloc,
                          f"{agent} est réveillé en auto mais absent de la doc de la veille")

    def test_le_readme_annonce_le_bon_compte_de_vaisseaux_et_de_missions(self):
        """INVARIANT : la première phrase que lit un nouvel arrivant dit VRAI.

        Le paquet public portait pour ça une règle de généralisation,
        `compte-agents-perime` : le guide s'annonçait « 7 agents » alors que le
        dossier en contenait 8, et la règle recollait le bon chiffre à la sortie.
        Un correctif en aval ne rougit jamais et ne protège que le paquet — le
        tronc, lui, continuait de mentir. Le compte se vérifie donc ICI, à la
        source, où il peut passer au rouge.
        """
        import re, robots_permissions
        desc = re.search(r"^description:\s*(.*)$",
                         open(os.path.join(BRAIN, "agents", "readme.md"),
                              encoding="utf-8").read(), re.M).group(1)
        vaisseaux = sorted(set(robots_permissions.FAMILLE.values()))
        annonce = re.search(r"(\d+) vaisseaux.*?(\d+) missions", desc)
        self.assertIsNotNone(
            annonce, "le guide n'annonce plus « N vaisseaux … N missions » : "
                     "le compte n'est plus vérifiable, donc plus protégé")
        self.assertEqual(
            (int(annonce.group(1)), int(annonce.group(2))),
            (len(vaisseaux), len(robots_permissions.FAMILLE)),
            f"le guide annonce {annonce.group(1)} vaisseaux et {annonce.group(2)} "
            f"missions ; la table en déclare {len(vaisseaux)} et "
            f"{len(robots_permissions.FAMILLE)}")
        for v in vaisseaux:
            self.assertIn(v.upper(), desc,
                          f"{v} existe mais n'est pas nommé dans le guide")

    def test_tout_agent_de_ORDER_a_un_modele_et_une_tache(self):
        import brain_upkeep
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, brain_upkeep.MODEL, f"{agent} sans modèle → défaut silencieux")
            self.assertIn(agent, brain_upkeep.TASKS, f"{agent} sans mission → KeyError au réveil")

    def test_tout_agent_appele_existe_sur_la_surface_que_claude_code_lit(self):
        """INVARIANT né de l'incident du 2026-08-19 : `--agent 'distillateur' not found`,
        74 fois, plus 44 pour `architecte` — 118 échecs en 39 heures, et pas un capteur.

        Ce qui avait cassé n'est ni le code ni les fiches d'agent : c'est le SYMLINK
        `~/.claude/agents`, repointé par l'installeur anglais vers un dossier où les
        agents portent des noms traduits (`distiller`, `gardener`). Les deux côtés
        étaient cohérents avec eux-mêmes ; c'est le raccord qui ne l'était plus.
        Personne ne comparait « les noms qu'on appelle » à « les noms qui existent
        LÀ OÙ Claude Code va les chercher ». D'où cet invariant, et pas un de plus :
        il lit la surface réelle, pas le dossier du dépôt, parce que c'est la surface
        qui avait menti. cf. projects/claude-brain/incident-fr-en-surfaces-auteur-2026-08-19.md
        et meta/decisions/adr-0013-langue-configuration-centrale.md (« un identifiant
        interne ne se traduit jamais »).
        """
        import re
        import brain_upkeep
        appeles = set(brain_upkeep.ORDER) | set(brain_upkeep.TASKS)
        # MODEL_L1 est déclaré DANS une fonction : il se lit à la source, comme les deux
        # barres du banc du rappel. Un agent de couche 1 absent d'ici passerait inaperçu,
        # et c'est précisément `distillateur` qui a le plus échoué en août.
        am = open(os.path.join(BRAIN, "hooks", "auto_maintain.py"), encoding="utf-8").read()
        m = re.search(r"MODEL_L1\s*=\s*\{([^}]*)\}", am)
        self.assertIsNotNone(m, "MODEL_L1 a changé de forme : le capteur ne voit plus "
                                "la couche 1, il doit être réécrit, pas contourné")
        appeles |= set(re.findall(r'"([a-z_]+)"\s*:', m.group(1)))

        # DEPUIS LE 2026-09-20 : ce qu'on appelle n'est plus la mission, c'est le VAISSEAU.
        # Les huit rôles survivent comme missions (mêmes outils, mêmes zones d'écriture),
        # mais `--agent` porte la famille, et c'est donc le fichier de famille qui doit
        # exister là où Claude Code regarde. Le trou que ce test surveille se déplace sans
        # disparaître : une mission sans famille déclarée planterait au réveil.
        import robots_permissions
        orphelines = sorted(m for m in appeles if m not in robots_permissions.FAMILLE)
        self.assertEqual(orphelines, [],
                         "ces missions sont appelées sans vaisseau déclaré dans "
                         "robots_permissions.FAMILLE : le réveil lèverait un KeyError")
        appeles = {robots_permissions.FAMILLE[m] for m in appeles}

        def manquants(noms, dossier):
            return sorted(n for n in noms
                          if not os.path.isfile(os.path.join(dossier, n + ".md")))

        # CONTRE-ÉPREUVE EN PLACE. Sans elle, ce test serait vert sur une machine bien
        # câblée sans qu'on sache s'il sait rougir. On lui donne un dossier où il manque
        # exactement un agent, et il doit le nommer.
        import tempfile
        with tempfile.TemporaryDirectory() as faux:
            for n in sorted(appeles)[1:]:
                open(os.path.join(faux, n + ".md"), "w").close()
            self.assertEqual(manquants(appeles, faux), [sorted(appeles)[0]],
                             "le détecteur ne voit pas un agent absent : il ne garde rien")

        surface = os.path.expanduser("~/.claude/agents")
        if not os.path.isdir(surface):
            self.skipTest("~/.claude/agents absent : rien à raccorder sur cette machine")
        absents = manquants(appeles, os.path.realpath(surface))
        self.assertEqual(absents, [], 
                         "ces agents sont APPELÉS et introuvables là où Claude Code les "
                         "cherche (%s → %s) : chaque réveil rendra « agent not found » "
                         "dans un journal que personne ne lit — le défaut du 19/08."
                         % (surface, os.path.realpath(surface)))


class ModeleParAgentCoucheUn(unittest.TestCase):
    """INVARIANT : l'étage créatif (distillateur) n'est jamais moins bien doté que l'étage
    mécanique (jardinier). Un échec de distillation perd du savoir DÉFINITIVEMENT ;
    un jardinage raté se rejoue."""

    RANG = {"haiku": 0, "sonnet": 1, "opus": 2}

    def test_distillateur_au_moins_aussi_fort_que_jardinier(self):
        src = open(os.path.join(BRAIN, "hooks", "auto_maintain.py"), encoding="utf-8").read()
        self.assertIn("MODEL_L1", src, "le modèle est codé en dur, non réglable par agent")
        ns = {}
        for line in src.splitlines():
            if line.strip().startswith("MODEL_L1"):
                exec(line.strip(), {}, ns)  # noqa: S102
        m = ns["MODEL_L1"]
        self.assertGreaterEqual(self.RANG[m["distillateur"]], self.RANG[m["jardinier"]],
                                "le distillateur (irréversible) tourne sous le jardinier (rejouable)")


class CarteComposeeSansPollution(unittest.TestCase):
    """INVARIANT : l'index secondaire allège le démarrage sans devenir du savoir."""

    REL_INDEX = os.path.join("lessons", "INDEX.md")

    def test_memory_garde_sa_marge_de_chargement(self):
        """LES DEUX AXES, parce que le harnais en a deux et que le premier atteint coupe.

        Jusqu'au 2026-09-20 cet invariant ne regardait que les octets. La limite qui a
        réellement invalidé la projection D3 est celle des LIGNES (292 contre 200) :
        surveiller la seule taille laisse passer une carte tronquée en silence, et le
        modèle est le seul à voir l'avertissement — jamais un code de sortie.
        """
        import brain_doctor
        blob = open(os.path.join(BRAIN, "MEMORY.md"), "rb").read()
        lignes = blob.count(b"\n") + (1 if blob and not blob.endswith(b"\n") else 0)
        self.assertLessEqual(len(blob), brain_doctor.MEMORY_WARN_BYTES,
                             f"MEMORY.md pèse {len(blob)} octets")
        self.assertLessEqual(lignes, brain_doctor.MEMORY_WARN_LINES,
                             f"MEMORY.md fait {lignes} lignes")

    def test_le_plafond_mesure_dit_sous_quel_harnais(self):
        """Un seuil sans la version qui l'a mesuré ne peut pas se périmer visiblement.

        Le plafond appartient à Claude Code : il peut bouger d'une version à l'autre,
        et le mode d'échec est une troncature silencieuse. La version de mesure est donc
        écrite à côté des seuils, et l'écart avec le harnais qui tourne est INFORMATIF —
        il n'a jamais le droit de faire sortir le docteur en 1, sinon la moindre mise à
        jour rougit un arbre sain et personne ne peut l'éteindre honnêtement (ADR-0016).
        """
        import brain_doctor
        self.assertRegex(brain_doctor.MEMORY_LIMITS_MEASURED_ON, r"^\d+\.\d+\.\d+$")
        self.assertIn("carte_plafond_non_remesure", brain_doctor.INFORMATIFS)

    def test_index_structurel_est_exclu_des_moteurs_de_savoir(self):
        import brain_recall
        import brain_topology
        import brain_utility
        import track_read
        self.assertTrue(brain_recall._skip(self.REL_INDEX))
        self.assertIn(self.REL_INDEX, brain_topology.STRUCTURAL_MAPS)
        self.assertIn(self.REL_INDEX, brain_utility.STRUCTURAL_MAPS)
        self.assertIn(self.REL_INDEX, track_read.STRUCTURAL_MAPS)

    def test_catalogues_infra_sont_exclus_du_rappel(self):
        import brain_recall
        for rel in ("agents/narcissus.md", "state/a-valider.md",
                    "capsule-v2/README.md", self.REL_INDEX):
            with self.subTest(rel=rel):
                self.assertTrue(brain_recall._skip(rel))


class SignalDeContexte(unittest.TestCase):
    """INVARIANT : l'alerte de contexte ne dépend pas d'un résultat de rappel."""

    def test_somme_usage_partagee(self):
        import context_usage
        self.assertEqual(context_usage.usage_tokens({
            "input_tokens": 10,
            "cache_read_input_tokens": 20,
            "cache_creation_input_tokens": 30,
        }), 60)

    def test_alerte_strictement_au_dessus_de_300k(self):
        import inject_recall
        original = inject_recall.read_context_tokens
        try:
            inject_recall.read_context_tokens = lambda _path: 300_000
            self.assertIsNone(inject_recall.context_notice({"transcript_path": "x"}))
            inject_recall.read_context_tokens = lambda _path: 300_001
            self.assertIn("300k tokens", inject_recall.context_notice({"transcript_path": "x"}))
        finally:
            inject_recall.read_context_tokens = original


class UnePierreTombaleNestPasUneTache(unittest.TestCase):
    """INVARIANT : une décision CONSIGNÉE ne se relit pas comme une tâche OUVERTE.

    Les deux moitiés semblent justes séparément : le détecteur cherche « reste à faire »,
    et une fiche bien tenue écrit noir sur blanc qu'une chose est close. Ensemble, elles
    produisent l'inverse du but — le 2026-08-13, les deux décisions que l'utilisateur venait de
    trancher sont ressorties le soir même en tête des points de reprise, en citant la
    phrase qui disait qu'elles étaient closes.

    C'est la fiche la MIEUX rédigée qui souffre le plus : plus on consigne proprement,
    plus on pollue la file. D'où un invariant et pas un correctif ponctuel.
    """

    def test_marqueur_barre_ou_nie_nest_pas_une_reprise(self):
        import brain_anticipate as ba
        for ligne in (
            "Le point est fermé, ce n'est plus un reste à faire.",
            "## ~~À reprendre en phase vernissage~~ — ABANDONNÉ le 13/08",
            "Aucun reste à faire sur ce lot.",
            "Il n'y a plus de point de reprise ici.",
            # trouvé le 2026-08-14 : le marqueur est « à faire », donc la fenêtre d'avant se
            # termine par « rien » et le motif `rien à` ne pouvait pas s'y appliquer.
            "✅ **TRANCHÉ le 2026-08-11 — plus rien à faire.** Les packs contenaient bien tout.",
            # « à faire » comme verbe français, pas comme tâche — c'est cette phrase-là qui
            # allumait le badge ↻ sur `audit-pack-outillage`.
            "Question de l'auteur : un simple repomix suffit-il à faire auditer un produit ?",
        ):
            self.assertIsNone(ba.best_marker(ligne), f"faux positif sur : {ligne}")

    def test_un_vrai_point_de_reprise_reste_detecte(self):
        """Le filtre ne doit pas rendre le détecteur muet — sinon il « passe » en ne
        trouvant plus rien, ce qui est la panne, pas la réussite."""
        import brain_anticipate as ba
        for ligne in (
            "## RESTE À FAIRE : brancher le token Notion du compte partagé",
            "Point de reprise : finir la refonte de l'interface",
            "Réglé le lot A ; RESTE À FAIRE : le lot B",
            # le marqueur faible reste valide quand il est PRÉSENTÉ comme une tâche
            "## À faire\n- brancher le webhook",
            "À faire : relancer l'export",
        ):
            self.assertIsNotNone(ba.best_marker(ligne), f"vrai point de reprise perdu : {ligne}")

    def test_le_tableau_de_bord_ne_se_detecte_pas_lui_meme(self):
        """ETAT-DES-PROJETS.md contient « ce qu'il faut reprendre » par construction :
        s'il entre dans le scan, il squatte la première place à chaque passage."""
        import brain_anticipate as ba
        noms = {it["path"] for it in ba.collect()}
        self.assertNotIn(os.path.join("projects", "ETAT-DES-PROJETS.md"), noms)

    def test_le_badge_de_la_planete_montre_les_memes_reprises_que_le_brain(self):
        """Le badge ↻ a longtemps eu SON propre détecteur (une recherche de « à reprendre »
        n'importe où dans le texte) : 32 fiches allumées en continu, dont des leçons qui
        PARLENT du marqueur et des tâches explicitement closes. Un marqueur allumé partout
        ne marque plus rien, et la carte contredisait le message de démarrage de session.
        Une seule source, un seul classement — et cet invariant pour que ça le reste."""
        import json
        import brain_anticipate as ba
        chemin = os.path.join(BRAIN, "planet", "graph.json")
        if not os.path.exists(chemin):
            self.skipTest("graph.json pas encore généré")
        graphe = json.load(open(chemin, encoding="utf-8"))
        # TROIS ÉTATS, PAS DEUX (2026-08-20). « Les ensembles diffèrent » recouvrait
        # jusqu'ici trois causes très différentes : la capacité manque, l'instantané
        # est périmé, ou il y a une vraie incohérence. Les confondre a coûté une
        # demi-journée de diagnostic : on comparait un instantané à un recalcul en
        # croyant comparer deux détecteurs.
        if graphe.get("reprises_indisponibles"):
            self.skipTest("badge ↻ non calculable : %s" % graphe["reprises_indisponibles"])
        import subprocess
        r = subprocess.run(["git", "-C", BRAIN, "rev-parse", "HEAD"],
                           capture_output=True, text=True)
        head_courant = r.stdout.strip() if r.returncode == 0 else None
        head_graphe = graphe.get("head")
        if head_courant and head_graphe and head_courant != head_graphe:
            self.fail("planet/graph.json décrit le HEAD %s, le tronc est sur %s : "
                      "l'instantané est PÉRIMÉ, pas incohérent. `commit_par_zone` "
                      "régénère le graphe après chaque commit — si ce message "
                      "apparaît, cette régénération a échoué et l'a dit."
                      % (head_graphe[:12], head_courant[:12]))
        allumes = {n["file"] for n in graphe["nodes"] if n.get("resume")}
        attendus = {it["path"] for it in ba.collect()[:ba.TOP_REPRISES]}
        self.assertEqual(allumes, attendus,
                         "le badge ↻ et les reprises proposées au démarrage ont divergé "
                         "SUR LE MÊME HEAD — ce n'est ni un manque de capacité ni un "
                         "instantané périmé, c'est une vraie incohérence")


if __name__ == "__main__":
    unittest.main(verbosity=2)
