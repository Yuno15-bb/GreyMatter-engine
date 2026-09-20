#!/usr/bin/env python3
"""
banc_course_git.py — TÉMOIN NÉGATIF de la course Git. Phase 2A d'ADR-0017.

CE QUE CE BANC EST — ET N'EST PAS
    Ce n'est PAS un invariant. Ce n'est PAS une barrière. C'est le **témoin négatif**
    exigé par ADR-0017 : la moitié « SANS protection » du contraste 1/2.

        « un garde-fou qui n'a jamais été mesuré SANS lui ne prouve rien. »

    Il est écrit AVANT `git_guard`, délibérément, pour qu'aucun test de la primitive ne
    naisse vert sans avoir jamais rougi (cf. lessons/chaine-de-preuve-mesure-baseline-
    sabotage.md, ADR-0016). Tant que ce banc n'a pas montré l'incident, l'architecture
    d'ADR-0017 reste une HYPOTHÈSE.

VOCABULAIRE — LIRE AVANT D'INTERPRÉTER UN CODE DE SORTIE
    Ici « ROUGE » ne veut pas dire « le banc est cassé ». Il veut dire :

        ROUGE = la course a été REPRODUITE = le système sans verrou EST vulnérable.

    C'est le résultat ATTENDU de ce pas. Il doit rester rouge pour toujours : c'est un
    témoin daté, pas une santé à surveiller.

    ⚠️ CE BANC NE REND JAMAIS 0. Aucune sortie de ce fichier ne peut être lue comme
    « absence d'incident ». Les trois codes possibles :

        1  ROUGE — course reproduite par une variante FIDÈLE   (attendu de la phase 2A)
        2  NON CONCLUANT — rien de fidèle ne reproduit, ou banc non calibré  (→ STOP)
        3  BANC INEXÉCUTABLE — git absent, dépôt jetable impossible  (INCONNU, pas 2)

    Il n'est branché dans AUCUN runner : ni `hooks/selftest.sh`, ni la liste BANCS du
    `pre-commit`. Un témoin permanent non nul y bloquerait tous les commits.

ISOLATION — CONTRAINTE ABSOLUE
    Chaque exécution se fait dans un dépôt Git jetable neuf, sous le répertoire
    temporaire du système. `garde_isolation()` REFUSE de tourner si le chemin de travail
    touche `~/.c-brain/trunk`. Aucun `origin`, aucun distant, aucun `core.hooksPath` hérité,
    aucune config globale (GIT_CONFIG_GLOBAL=/dev/null) : les hooks du tronc ne peuvent
    pas s'exécuter ici. Zéro mutation du Brain de production, zéro réseau.

POURQUOI UN PANNEAU DE VARIANTES, ET PAS LE SEUL SCÉNARIO DEMANDÉ
    Le scénario « A stage → B reset → A commit » a été sondé à la main avant d'écrire ce
    fichier : avec la commande FIDÈLE au producteur (`git commit -q -F -`, sans
    `--allow-empty`), git REFUSE et HEAD ne bouge pas. Et `grep -rn -- "--allow-empty"
    hooks/ tools/ tests/ .git/hooks/` ne rend AUCUNE occurrence dans le tronc.

    Reproduire l'incident en ajoutant `--allow-empty` fabriquerait donc un rouge sous une
    commande que la production n'exécute jamais — une preuve qui ne prouve rien.

    Le panneau ci-dessous est donc FIXÉ AVANT LA MESURE, et TOUTES ses lignes sont
    rapportées, y compris celles qui ne reproduisent rien. Ce n'est pas « essayer jusqu'à
    obtenir le résultat attendu » : c'est déclarer les candidats, puis les départager.
    Chaque variante porte un drapeau `fidele` : vrai seulement si elle n'emploie que des
    commandes et des drapeaux réellement présents dans les producteurs du tronc
    (`hooks/commit_par_zone.py`, `tools/sync_depots.py`, `brain push`).

    Une reproduction QUALIFIANTE exige `fidele=True`. Une variante non fidèle qui
    reproduit est une information sur git, pas une preuve sur le Brain.

DEUX OBSERVABLES, PAS UN — les incidents du 2026-08-25 n'étaient pas tous le même
    commit_vide          tree(commit) == tree(parent)  →  le commit publié ne porte rien
    perimetre_contamine  le commit contient un fichier absent du plan de l'acteur
    echec_operation_de_a l'opération de A échoue à cause de l'autre acteur (refus, ou
                         index.lock pris) — une perte de travail, pas une corruption

    ATTRIBUTION. Un observable n'est porté au compte de A que si le commit de A a
    RÉUSSI. Sans cette règle le banc mentait sur S5 : HEAD avançait 10/10 et il lisait
    le commit de B comme celui de A, alors que celui de A était refusé. Un HEAD qui
    avance ne certifie pas que MON opération a abouti.

    La source de vérité est TOUJOURS le commit final, observé après coup : `git cat-file`
    sur son arbre, `git diff-tree` sur son contenu. Jamais `git status`, jamais
    `git diff --cached`, jamais l'intention de l'acteur — c'est exactement la faute que
    lessons/une-observation-pre-operation-ne-certifie-pas-le-resultat.md a coûté.
    Les codes de retour sont enregistrés comme données SECONDAIRES.

INTERLEAVING — IMPOSÉ, PAS ESPÉRÉ
    Les acteurs sont deux fils qui se relaient sur des `threading.Event` nommés. Chaque
    opération git reste un PROCESSUS distinct (`subprocess.run`), donc la contention sur
    `.git/index` est la vraie. BORNE ASSUMÉE : deux fils d'un même parent, pas deux
    sessions launchd. Ce que ce banc ne peut pas reproduire, il ne le prétend pas.

    Seule S3 relâche ses deux acteurs ensemble : elle mesure une contention non ordonnée,
    et se rapporte donc en n/N, jamais comme un déterminisme.

PHASE 2B — NE CHANGER QU'UNE VARIABLE
    `jouer()` prend un argument `protection` aujourd'hui TOUJOURS None. La phase 2B y
    passera `git_guard` et rejouera EXACTEMENT le même scénario. Le scénario et le
    garde-fou ne doivent jamais bouger dans la même mesure.

Usage :
  python3 tests/banc_course_git.py                  10 répétitions, écrit le témoin
  python3 tests/banc_course_git.py --repetitions 3  plus court
  python3 tests/banc_course_git.py --sans-ecrire    n'écrit aucun fichier de résultat
"""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import git_guard  # noqa: E402
TEMOIN = os.path.join(ICI, "banc-course-git", "resultats.json")

MSG = "auto: savoir : fiches, lecons et cartes\n\nCommit automatique par zone.\n"


# ── LA SEULE VARIABLE EXPÉRIMENTALE ─────────────────────────────────────────
# Phase 2B. Rien d'autre ne change entre les deux arms : mêmes commandes git, mêmes
# `Event`, mêmes observables, mêmes dépôts jetables. Seul un `with` s'ajoute autour des
# opérations — et sous la garde NEUTRE ce `with` ne fait littéralement rien.
#
# LE CONTRÔLE QUI REND CETTE AFFIRMATION VÉRIFIABLE : sous garde neutre, le panneau doit
# rendre EXACTEMENT les chiffres du témoin déjà commité. S'ils bougent, c'est
# l'instrumentation qui a changé le scénario, et plus aucun contraste ne signifie rien.
class GardeNeutre:
    """Ne verrouille rien. Rend un jeton vrai pour que le corps s'exécute comme avant."""
    nom = "aucune"

    @contextlib.contextmanager
    def transaction(self, acteur, operation, perimetre, repo):
        yield {"neutre": True}


class GardeGitGuard:
    """La VRAIE primitive hooks/git_guard.py, pas une imitation écrite pour le banc.

    `attente=0` : l'acteur concurrent est REFUSÉ immédiatement plutôt que mis en file.
    C'est le comportement le plus lisible pour un banc — le refus est un observable net,
    l'attente n'en est qu'un décalage. Les deux sont acceptables selon ADR-0017 ;
    `sabotage_attente()` éprouve la file séparément."""
    nom = "git_guard"

    def __init__(self, attente_b=0.0):
        self.attente_b = attente_b

    @contextlib.contextmanager
    def transaction(self, acteur, operation, perimetre, repo):
        attente = self.attente_b if acteur == "B" else 0.0
        with git_guard.transaction(acteur, operation, perimetre, depot=repo,
                                   attente=attente) as jeton:
            yield jeton


# ── Isolation ────────────────────────────────────────────────────────────────
def garde_isolation(chemin):
    """REFUSE tout chemin de travail qui pourrait toucher le tronc de production.

    Ce garde est la seule chose entre ce banc et un `git reset` sur le vrai dépôt.
    Il vérifie le chemin RÉEL (realpath) : un symlink ne doit pas pouvoir le contourner,
    et `~/.c-brain/trunk` EST un symlink chez son auteur."""
    reel = os.path.realpath(chemin)
    interdit = os.path.realpath(BRAIN)
    if reel == interdit or reel.startswith(interdit + os.sep):
        raise RuntimeError("ISOLATION VIOLÉE : %s est dans le tronc %s" % (reel, interdit))
    if not reel.startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError("ISOLATION VIOLÉE : %s est hors du répertoire temporaire" % reel)
    return reel


ENV = dict(os.environ,
           GIT_CONFIG_GLOBAL="/dev/null",   # aucune config utilisateur
           GIT_CONFIG_SYSTEM="/dev/null",   # aucune config système
           GIT_TERMINAL_PROMPT="0")


def sh(cmd, repo, entree=None):
    """(code, sortie). Jamais d'exception : un échec git est une DONNÉE, pas un crash."""
    try:
        r = subprocess.run(["git"] + cmd, cwd=repo, env=ENV, input=entree,
                           text=True, capture_output=True, timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:                                    # pragma: no cover
        return 127, str(e)


def depot_jetable():
    """Dépôt neuf, hermétique : pas de hooks, pas de distant, pas de config héritée.

    core.hooksPath pointe sur un dossier VIDE : même si le template global installait des
    hooks, aucun ne peut s'exécuter. C'est ce qui garantit que le pre-commit du tronc ne
    tourne pas ici."""
    tmp = garde_isolation(tempfile.mkdtemp(prefix="banc-course-git-"))
    vide = os.path.join(tmp, "hooks-vides")
    os.makedirs(vide)
    repo = os.path.join(tmp, "depot")
    os.makedirs(repo)
    sh(["init", "-q", "--initial-branch=main", "."], repo)
    for c, v in (("user.name", "Banc"), ("user.email", "banc@local"),
                 ("commit.gpgsign", "false"), ("core.hooksPath", vide)):
        sh(["config", c, v], repo)
    # C0 — l'état de base versionné
    for nom, contenu in (("f1.md", "base f1\n"), ("f2.md", "base f2\n")):
        open(os.path.join(repo, nom), "w").write(contenu)
    sh(["add", "f1.md", "f2.md"], repo)
    sh(["commit", "-q", "-m", "C0"], repo)
    # les modifications destinées à C1, présentes dans l'arbre de travail, NON stagées
    for nom in ("f1.md", "f2.md"):
        open(os.path.join(repo, nom), "a").write("modif destinee a C1\n")
    return tmp, repo


# ── Observation : uniquement APRÈS l'opération, uniquement sur l'objet réel ──
def index_stage(repo):
    return sorted(x for x in sh(["diff", "--cached", "--name-only"], repo)[1].splitlines() if x)


def observer(repo, parent):
    """Lit le commit RÉELLEMENT produit. Rien ici ne dépend d'une observation antérieure."""
    tete = sh(["rev-parse", "HEAD"], repo)[1]
    o = {"parent": parent, "head_apres": tete, "head_a_bouge": tete != parent}
    if not o["head_a_bouge"]:
        o.update(commit=None, tree=None, tree_parent=sh(["rev-parse", parent + "^{tree}"], repo)[1],
                 fichiers=[], commit_vide=False, perimetre_contamine=False)
        return o
    o["commit"] = tete
    o["tree"] = sh(["rev-parse", tete + "^{tree}"], repo)[1]
    o["tree_parent"] = sh(["rev-parse", parent + "^{tree}"], repo)[1]
    o["fichiers"] = sorted(x for x in sh(
        ["diff-tree", "--no-commit-id", "--name-only", "-r", tete], repo)[1].splitlines() if x)
    # LE critère : l'arbre du commit est-il celui de son parent ?
    o["commit_vide"] = (o["tree"] == o["tree_parent"])
    return o


# ── Le panneau — FIXÉ AVANT LA MESURE ────────────────────────────────────────
# plan  = ce que l'acteur A a l'intention de committer. Sert au seul calcul du
#         périmètre contaminé ; il n'est JAMAIS utilisé pour conclure sur le commit.
def variante_T(repo, cmt, plan, ev, g):
    """CONTRÔLE — A seul, aucun acteur B. Calibration : doit produire un commit NON VIDE."""
    with g.transaction("A", "add+commit", plan, repo) as jeton:
        ev["jeton_a"] = bool(jeton)
        sh(["add", "--"] + plan, repo)
        idx = index_stage(repo)
        code, _ = sh(cmt, repo, entree=MSG)
    return idx, [], code


def variante_S1(repo, cmt, plan, ev, g):
    """A stage → B reset → A commit. La séquence littérale d'ADR-0017, commande FIDÈLE."""
    def acteur_b():
        ev["INDEX_PRET"].wait(30)
        # B demande le verrou pour SA mutation. Refusé, il ne mute pas — mais il signale
        # quand même : sans ça, A attendrait un évènement qui n'arrive jamais et le banc
        # mesurerait un interblocage au lieu d'un refus.
        with g.transaction("B", "reset", ["f2.md"], repo) as jeton_b:
            ev["b_refuse"] = not bool(jeton_b)
            if jeton_b:
                ev["code_b"] = sh(["reset", "-q"], repo)[0]
                ev["idx_apres_b"] = index_stage(repo)
        ev["RESET_FAIT"].set()

    t = threading.Thread(target=acteur_b, daemon=True)
    t.start()
    jeton_a = g.transaction("A", "add+commit", plan, repo)
    jeton_a.__enter__()
    ev["jeton_a"] = True
    sh(["add", "--"] + plan, repo)
    idx = index_stage(repo)
    ev["INDEX_PRET"].set()
    ev["RESET_FAIT"].wait(30)          # attente EXPLICITE, pas un sleep d'espoir
    code, _ = sh(cmt, repo, entree=MSG)
    jeton_a.__exit__(None, None, None)
    t.join(5)
    return idx, ev.get("idx_apres_b", []), code


def variante_S3(repo, cmt, plan, ev, g):
    """commit et reset relâchés ENSEMBLE — contention réelle sur .git/index.lock.

    Seule variante non ordonnée : elle ne peut donc PAS se rapporter comme déterministe."""
    resultat = {}

    def acteur_b():
        ev["INDEX_PRET"].wait(30)
        ev["TOP"].wait(30)
        with g.transaction("B", "reset", ["f2.md"], repo) as jeton_b:
            ev["b_refuse"] = not bool(jeton_b)
            if jeton_b:
                resultat["code_b"] = sh(["reset", "-q"], repo)[0]

    t = threading.Thread(target=acteur_b, daemon=True)
    t.start()
    jeton_a = g.transaction("A", "add+commit", plan, repo)
    jeton_a.__enter__()
    ev["jeton_a"] = True
    sh(["add", "--"] + plan, repo)
    idx = index_stage(repo)
    ev["INDEX_PRET"].set()
    time.sleep(0.02)                   # laisse B atteindre la barrière, pas la course
    ev["TOP"].set()
    code, _ = sh(cmt, repo, entree=MSG)
    jeton_a.__exit__(None, None, None)
    t.join(5)
    return idx, [], code


def variante_S4(repo, cmt, plan, ev, g):
    """A stage f1 → B stage f2 → A commit SANS pathspec. Périmètre, pas commit vide.

    C'est la forme exacte de commit_par_zone : il commite L'INDEX, pas sa sélection."""
    def acteur_b():
        ev["INDEX_PRET"].wait(30)
        # B demande le verrou pour SA mutation. Refusé, il ne mute pas — mais il signale
        # quand même : sans ça, A attendrait un évènement qui n'arrive jamais et le banc
        # mesurerait un interblocage au lieu d'un refus.
        with g.transaction("B", "add", ["f2.md"], repo) as jeton_b:
            ev["b_refuse"] = not bool(jeton_b)
            if jeton_b:
                ev["code_b"] = sh(["add", "--", "f2.md"], repo)[0]
                ev["idx_apres_b"] = index_stage(repo)
        ev["ADD_FAIT"].set()

    t = threading.Thread(target=acteur_b, daemon=True)
    t.start()
    jeton_a = g.transaction("A", "add+commit", plan, repo)
    jeton_a.__enter__()
    ev["jeton_a"] = True
    sh(["add", "--"] + plan, repo)
    idx = index_stage(repo)
    ev["INDEX_PRET"].set()
    ev["ADD_FAIT"].wait(30)
    code, _ = sh(cmt, repo, entree=MSG)
    jeton_a.__exit__(None, None, None)
    t.join(5)
    return idx, ev.get("idx_apres_b", []), code


def variante_S5(repo, cmt, plan, ev, g):
    """A stage → B COMMITE le même contenu → A commit. HEAD bouge sous A."""
    def acteur_b():
        ev["INDEX_PRET"].wait(30)
        # B demande le verrou pour SA mutation. Refusé, il ne mute pas — mais il signale
        # quand même : sans ça, A attendrait un évènement qui n'arrive jamais et le banc
        # mesurerait un interblocage au lieu d'un refus.
        with g.transaction("B", "commit", ["f2.md"], repo) as jeton_b:
            ev["b_refuse"] = not bool(jeton_b)
            if jeton_b:
                ev["code_b"] = sh(["commit", "-q", "-F", "-"], repo, entree="commit de B\n")[0]
                ev["idx_apres_b"] = index_stage(repo)
        ev["COMMIT_B_FAIT"].set()

    t = threading.Thread(target=acteur_b, daemon=True)
    t.start()
    jeton_a = g.transaction("A", "add+commit", plan, repo)
    jeton_a.__enter__()
    ev["jeton_a"] = True
    sh(["add", "--"] + plan, repo)
    idx = index_stage(repo)
    ev["INDEX_PRET"].set()
    ev["COMMIT_B_FAIT"].wait(30)
    code, _ = sh(cmt, repo, entree=MSG)
    jeton_a.__exit__(None, None, None)
    t.join(5)
    return idx, ev.get("idx_apres_b", []), code


def variante_S6(repo, cmt, plan, ev, g):
    """S4 à l'identique, MAIS le commit porte son périmètre : `git commit -- f1.md`.

    Mesure la seule parade qu'ADR-0017 affirme sans l'avoir mesurée : « préférer les
    commandes qui portent l'intention dans l'opération ». ⚠️ Ce n'est PAS git_guard, et
    cela ne clôt PAS la phase 2B : le pathspec protège le PÉRIMÈTRE, jamais l'état
    partagé. La variante existe parce que ce banc ne doit pas s'appuyer sur une
    affirmation non mesurée pour se faire committer lui-même."""
    return variante_S4(repo, cmt + ["--"] + plan, plan, ev, g)


CMT_FIDELE = ["commit", "-q", "-F", "-"]          # littéralement commit_par_zone.py:88-91
CMT_VIDE_OK = ["commit", "-q", "--allow-empty", "-F", "-"]

PANNEAU = [
    ("T",  "CONTRÔLE — A seul, aucun acteur concurrent",              variante_T,  CMT_FIDELE,  True,  True),
    ("S1", "A stage → B reset → A commit (commande fidèle)",          variante_S1, CMT_FIDELE,  True,  True),
    ("S2", "idem S1 mais avec --allow-empty",                         variante_S1, CMT_VIDE_OK, False, True),
    ("S3", "commit et reset relâchés ensemble (index.lock)",          variante_S3, CMT_FIDELE,  True,  False),
    ("S4", "A stage f1 → B stage f2 → A commit (périmètre)",          variante_S4, CMT_FIDELE,  True,  True),
    ("S5", "A stage → B commite → A commit (HEAD bouge sous A)",      variante_S5, CMT_FIDELE,  True,  True),
    ("S6", "S4 mais `git commit -- <plan>` (périmètre porté)",         variante_S6, CMT_FIDELE,  True,  True),
]


def jouer(fn, cmt, plan, protection=None):
    """Un tir dans un dépôt jetable neuf. Rend le dossier observable de ce tir.

    `protection` est le SEUL levier que la phase 2B change. None = garde neutre, le
    système nu ; une GardeGitGuard = le même scénario avec la primitive. Rien d'autre ne
    diffère entre les deux arms."""
    g = protection or GardeNeutre()
    tmp, repo = depot_jetable()
    try:
        parent = sh(["rev-parse", "HEAD"], repo)[1]
        ev = {"INDEX_PRET": threading.Event(), "RESET_FAIT": threading.Event(),
              "ADD_FAIT": threading.Event(), "COMMIT_B_FAIT": threading.Event(),
              "TOP": threading.Event()}
        idx_apres_add, idx_apres_b, code_a = fn(repo, cmt, plan, ev, g)
        o = observer(repo, parent)                     # ← la seule source de vérité
        # ATTRIBUTION. Défaut trouvé sur S5 : HEAD avait bougé 10/10 et le banc lisait ce
        # commit comme « celui de A », alors que le commit de A était REFUSÉ (code 1) et
        # que HEAD portait le commit de B. Un HEAD qui avance ne prouve pas que MON
        # opération a réussi — c'est la même faute que celle d'ADR-0017, appliquée à
        # l'instrument lui-même. Les observables ne sont attribués à A que si A a réussi.
        o["commit_attribuable_a_a"] = (code_a == 0 and o["head_a_bouge"])
        o["echec_operation_de_a"] = (code_a != 0)
        o["plan_de_a"] = plan
        o["index_apres_add"] = idx_apres_add
        o["staging_confirme"] = (sorted(idx_apres_add) == sorted(plan))
        o["index_apres_acteur_b"] = idx_apres_b
        o["b_a_agi_apres_le_staging"] = bool(idx_apres_add) and "code_b" in ev
        o["perimetre_contamine"] = (bool(set(o["fichiers"]) - set(plan))
                                    if o["commit_attribuable_a_a"] else False)
        if not o["commit_attribuable_a_a"]:
            o["commit_vide"] = False            # on n'attribue pas à A l'arbre d'un autre
        # L'acteur B a-t-il été REFUSÉ par la garde ? False sous garde neutre, où
        # personne ne refuse rien. C'est l'observable propre au mécanisme de protection :
        # il ne dit pas que l'incident est évité, il dit POURQUOI il l'est.
        o["acteur_b_refuse"] = bool(ev.get("b_refuse"))
        o["protection"] = g.nom
        o["codes_secondaires"] = {"a": code_a, "b": ev.get("code_b")}
        return o
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    argv = sys.argv[1:]
    n = 10
    if "--repetitions" in argv:
        n = int(argv[argv.index("--repetitions") + 1])
    ecrire = "--sans-ecrire" not in argv

    print("=" * 78)
    protege = "--avec-git-guard" in argv
    print("BANC DE COURSE GIT — ADR-0017 · %s" %
          ("phase 2B : QUALIFICATION de git_guard" if protege
           else "phase 2A : TÉMOIN NÉGATIF, sans protection"))
    print("  dépôts jetables · %d répétitions · protection : %s"
          % (n, "git_guard" if protege else "AUCUNE"))
    print("  ⚠️  « ROUGE » ici = incident REPRODUIT = vulnérabilité démontrée.")
    print("=" * 78)

    try:
        code, sortie = sh(["--version"], tempfile.gettempdir())
        if code:
            raise RuntimeError(sortie)
        print("  git : %s\n" % sortie)
    except Exception as e:
        print("BANC INEXÉCUTABLE — git indisponible : %s" % e)
        return 3

    protection = GardeGitGuard() if "--avec-git-guard" in argv else None
    if protection:
        print("  ⚙️  PROTECTION ACTIVE : %s — même scénario, une seule variable changée\n"
              % protection.nom)

    resultats, lignes = {}, []
    for cle, titre, fn, cmt, fidele, ordonne in PANNEAU:
        plan = ["f1.md"]
        tirs = []
        try:
            for _ in range(n):
                tirs.append(jouer(fn, cmt, plan, protection))
        except Exception as e:
            print("BANC INEXÉCUTABLE — %s a levé : %s" % (cle, e))
            return 3
        agg = {o: sum(t[o] for t in tirs) for o in
               ("commit_vide", "perimetre_contamine", "echec_operation_de_a",
                "head_a_bouge", "commit_attribuable_a_a", "staging_confirme",
                "acteur_b_refuse")}
        resultats[cle] = dict(agg, titre=titre, fidele=fidele, ordonne=ordonne,
                              commande=" ".join(["git"] + cmt), plan_de_a=plan,
                              repetitions=n, tirs=tirs)
        lignes.append((cle, titre, fidele, agg))

    print("  clé  fidèle   commit    commit   périm.    échec de   B refusé")
    print("            de A      VIDE     contaminé  l'opé. A   par la garde")
    print("  " + "-" * 66)
    for cle, titre, fidele, a in lignes:
        f = lambda k: "%d/%d" % (a[k], n)
        print("  %-4s %-8s %-9s %-8s %-10s %-10s %s" % (
            cle, "oui" if fidele else "NON",
            f("commit_attribuable_a_a"), f("commit_vide"),
            f("perimetre_contamine"), f("echec_operation_de_a"),
            f("acteur_b_refuse")))
    print()
    for cle, titre, *_ in lignes:
        print("  %-4s %s" % (cle, titre))
    print()

    # ── Verdict ──────────────────────────────────────────────────────────────
    T = resultats["T"]
    calibre = (T["commit_attribuable_a_a"] == n and T["commit_vide"] == 0
               and T["perimetre_contamine"] == 0 and T["staging_confirme"] == n
               and T["echec_operation_de_a"] == 0)
    print("  CALIBRATION — le contrôle T produit-il un commit NON VIDE à chaque fois ?")
    print("     %s  T : commit de A abouti %d/%d · vide %d/%d · contaminé %d/%d · "
          "staging confirmé %d/%d"
          % ("✅" if calibre else "❌", T["commit_attribuable_a_a"], n, T["commit_vide"], n,
             T["perimetre_contamine"], n, T["staging_confirme"], n))

    OBSERVABLES = ("commit_vide", "perimetre_contamine", "echec_operation_de_a")
    qualifiantes = {o: [c for c, r in resultats.items()
                        if c != "T" and r["fidele"] and r[o] == n]
                    for o in OBSERVABLES}
    non_fideles = {o: [c for c, r in resultats.items()
                       if c != "T" and not r["fidele"] and r[o] > 0]
                   for o in OBSERVABLES}

    verdict = {"calibre": calibre, "repetitions": n,
               "reproductions_qualifiantes": qualifiantes,
               "reproductions_non_fideles": non_fideles}

    if ecrire:
        os.makedirs(os.path.dirname(TEMOIN), exist_ok=True)
        chemin = TEMOIN if not protection else TEMOIN.replace(".json", "-git-guard.json")
        json.dump({"_lisez_moi": "Témoin négatif d'ADR-0017 phase 2A : le comportement du "
                                 "dépôt SANS git_guard. Preuve DATÉE, pas test de santé. "
                                 "La phase 2B rejoue le même panneau avec la protection.",
                   "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "git": sortie, "protection": protection.nom if protection else "aucune",
                   "verdict": verdict, "variantes": resultats},
                  open(chemin, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n  témoin écrit : %s" % os.path.relpath(chemin, BRAIN))

    print("\n" + "-" * 78)
    if not calibre:
        print("NON CONCLUANT — BANC NON CALIBRÉ.")
        print("  Le contrôle T ne produit pas un commit non vide à chaque tir. Tant que le")
        print("  scénario normal n'est pas démontré sain, aucun rouge ne peut être attribué")
        print("  à l'interleaving. Ne pas conclure. Ne PAS lire ceci comme « pas d'incident ».")
        return 2

    # ── BRAS PROTÉGÉ — le critère n'est PAS « rien ne se reproduit » dans l'absolu.
    # C'est : « ce qui se reproduisait n/n SANS protection ne se reproduit plus AVEC ».
    # La référence est le témoin du bras nu, lu sur le disque : sans lui on ne compare
    # rien et on ne peut rien qualifier — un banc protégé seul serait un vert vide.
    if protection:
        try:
            nu = json.load(open(TEMOIN, encoding="utf-8"))["variantes"]
        except Exception as e:
            print("NON CONCLUANT — témoin du bras NU introuvable (%s)." % e)
            print("  Rien à comparer : lancer d'abord `python3 tests/banc_course_git.py`.")
            return 2
        attendus, tenus, rates = [], [], []
        for cle, r in resultats.items():
            if cle == "T" or not r["fidele"]:
                continue
            for o in OBSERVABLES:
                if nu.get(cle, {}).get(o) == nu.get(cle, {}).get("repetitions"):
                    attendus.append((cle, o))
                    (tenus if r[o] == 0 else rates).append((cle, o, r[o]))
        print()
        if not calibre:
            print("ROUGE — la protection a cassé le chemin NORMAL : le contrôle T ne")
            print("  produit plus un commit propre. Un garde-fou qui empêche aussi le")
            print("  travail légitime n'est pas un garde-fou.")
            return 1
        if not attendus:
            print("NON CONCLUANT — le témoin nu ne déclare aucun incident fidèle à")
            print("  empêcher. Il n'y a rien à qualifier.")
            return 2
        print("  QUALIFICATION — ce qui se reproduisait 10/10 SANS protection :")
        for cle, o, v in [(c, o, 0) for c, o in tenus] if False else tenus:
            print("     ✅ %-3s %-22s %d/%d sous protection · B refusé %d/%d"
                  % (cle, o, v, n, resultats[cle]["acteur_b_refuse"], n))
        for cle, o, v in rates:
            print("     ❌ %-3s %-22s SE REPRODUIT ENCORE %d/%d" % (cle, o, v, n))
        print()
        if rates:
            print("ROUGE — git_guard ne tient pas : %d incident(s) subsistent." % len(rates))
            return 1
        print("DÉMONTRÉ SOUS LE BANC — git_guard empêche les incidents S1/S4/S5 dans les")
        print("  conditions testées : %d couple(s) (variante, observable) qui se"
              % len(tenus))
        print("  reproduisaient 10/10 sans protection tombent à 0/10 avec, et le chemin")
        print("  normal (T) reste intact 10/10.")
        print()
        print("  ⚠️  CE N'EST PAS « GIT EST GOUVERNÉ ». Aucun producteur de production ne")
        print("  passe encore par la primitive : commit_par_zone, sync_depots, brain push")
        print("  et auto_maintain mutent toujours git en direct. La portée de ce vert")
        print("  s'arrête aux dépôts jetables de ce banc.")
        return 0

    gagnantes = sorted({c for o in OBSERVABLES for c in qualifiantes[o]})
    if gagnantes:
        print("ROUGE — course Git reproduite.")
        for o in OBSERVABLES:
            if qualifiantes[o]:
                print("  · %-20s reproduit %d/%d par : %s  (commandes de production)"
                      % (o, n, n, ", ".join(qualifiantes[o])))
            else:
                print("  · %-20s NON reproduit par une variante fidèle%s"
                      % (o, ("  — seulement par %s, hors production"
                             % ", ".join(non_fideles[o])) if non_fideles[o] else ""))
        print("\n  Témoin négatif obtenu. Le mécanisme ci-dessus n'a plus besoin d'être")
        print("  supposé : il est OBSERVÉ. Phase 2B autorisée — rejouer CE panneau avec")
        print("  git_guard pour seule variable changée.")
        return 1

    print("NON CONCLUANT — aucune variante FIDÈLE ne reproduit un incident.")
    for o in OBSERVABLES:
        if non_fideles[o]:
            print("  · %s : reproduit seulement par %s, qui emploie une commande ABSENTE de"
                  % (o, ", ".join(non_fideles[o])))
            print("    la production — donc sans valeur de preuve sur le Brain.")
    print("\n  RÉSULTAT POSSIBLE 2 d'ADR-0017 : STOP. Ne pas adapter le banc jusqu'à")
    print("  obtenir le résultat attendu. L'hypothèse « un reset concurrent seul explique")
    print("  le commit vide » reste NON ÉTABLIE. Ne PAS lire ceci comme « pas d'incident ».")
    return 2


if __name__ == "__main__":
    sys.exit(main())
