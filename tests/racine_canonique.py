#!/usr/bin/env python3
"""racine_canonique.py — « quel Brain ce processus mesure-t-il ? »

L'INVARIANT CIBLE :

    Un processus exécuté dans un Brain donné mesure CE Brain,
    jamais silencieusement un autre arbre.

CE QUE CE BANC EST, ET CE QU'IL N'EST PAS. Il ne migre rien et ne corrige rien.
Il FIGE l'état mesuré le 2026-08-20 : cinq dialectes de résolution de racine
coexistent, deux d'entre eux lisent le tronc auteur depuis un clone. `--check`
échoue si la réalité s'écarte de cet état **dans un sens comme dans l'autre** :
une classe qui devient rouge est une régression, une classe qui devient verte
est une migration à consigner. Même patron que `tools/temoins-bancs.json` — un
écart connu se DÉCLARE, il ne se mémorise pas.

⚠️ Le vert de ce banc ne veut donc PAS dire « tout va bien ». Il veut dire
« rien n'a bougé depuis la mesure ». Les classes rouges sont imprimées à chaque
passage, précisément pour qu'on ne l'oublie pas.

POURQUOI IL N'EST PAS BRANCHÉ AU pre-commit. Il construit un clone et un
worktree : quelques secondes, hors budget du garde de commit. Il se lance à la
main, et servira de barrière quand la migration commencera.

EFFET DE BORD NOMMÉ : le cas 11 lance le vrai CLI `brain doctor`, qui réécrit
`state/doctor.json` dans le tronc auteur — fichier ignoré par git et déjà
réécrit à chaque ouverture de session.

Lancer :
  python3 tests/racine_canonique.py            # rapport détaillé
  python3 tests/racine_canonique.py --check    # barrière (silencieuse si conforme)
  python3 tests/racine_canonique.py --sabotage # prouve que le banc sait rougir
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.join(ICI, ".."))

# Un représentant par dialecte. On charge le VRAI module et on lit le BRAIN
# qu'il a calculé — aucun résolveur n'est réimplémenté ici.
REPRESENTANTS = [
    ("A", "hooks/brain_corpus.py",     "BRAIN_HOME sinon ~/.c-brain/trunk"),
    ("B", "tools/verifier_temoins.py", "BRAIN_HOME sinon dirname(script)"),
    # ⚠️ TRANSITION CONSIGNÉE, 2026-08-21 — ne pas lire ce cas comme « la classe C ».
    # Au gel initial (2026-08-20), `hooks/ronde_annonce.py` faisait `expanduser("~/.c-brain/trunk")`
    # et représentait une classe C qui n'obéissait à RIEN. Il a été migré depuis, dans le lot
    # I-1 #1, et sa conformité est prouvée indépendamment de ce banc : contre-épreuve
    # comportementale CODE=A / BRAIN_HOME=B / HOME=C / cwd=D, plus `absent ≡ vide` et symlink
    # → realpath canonique (tools/matrice-i1-2026-08-21.md).
    #
    # UNE CLASSE HISTORIQUE N'EST PAS HOMOGÈNE APRÈS MIGRATION. Un représentant migré ne peut
    # plus servir à inférer l'état de toute sa classe : `mark_distilled.py`, `brain`,
    # `hooks/selftest.sh` et deux scripts capsule restent, eux, non conformes. On mesure donc
    # DEUX cas nommés au lieu d'une propriété globale devenue fausse des deux côtés.
    ("C", "hooks/ronde_annonce.py",    "MIGRÉ le 2026-08-21 — attendu : obéit"),
    ("C2", "hooks/mark_distilled.py",  "~/.c-brain/trunk EN DUR — attendu : ignore"),
    ("D", "tests/invariants_brain.py", "BRAIN_HOME sinon racine du dépôt"),
]

# ── COMMENT ON LIT LA RACINE DE CHAQUE REPRÉSENTANT ──────────────────────────
# Déclaré cas par cas, JAMAIS deviné. Une sonde qui essaierait une LISTE de noms
# (BRAIN, ROOT, RACINE, STATE_DIR…) mesurerait le VOCABULAIRE du module, pas sa
# racine — la faute exacte du classificateur statique, qui a produit cinq
# fausses accusations (tools/matrice-i1-2026-08-21.md §1). Un nom de variable ne
# prouve rien ; seule une donnée dont on connaît la place dans l'arbre prouve.
#
#   ("attribut", nom)          le module PUBLIE sa racine : on la lit telle quelle.
#   ("donnée", nom, suffixe)   le module ne publie AUCUNE racine. Il publie le
#                              chemin d'UNE donnée du Brain dont on connaît la
#                              place. La racine s'en déduit en retirant ce
#                              suffixe PAR SEGMENTS. Si le suffixe ne colle plus,
#                              la règle ne s'applique pas : NON-APPL, jamais un
#                              verdict inventé.
LECTURE = {
    "A":  ("attribut", "BRAIN"),
    "B":  ("attribut", "BRAIN"),
    "C":  ("attribut", "BRAIN"),
    # `mark_distilled.py` n'a pas de racine à publier : sa seule trace du Brain est
    # DISTILLED = <racine>/sessions/.distilled.json. C'est une donnée du Brain
    # (zone `sessions`), donc sa place est connue — c'est ce qui rend la
    # déduction légitime ici, et seulement ici.
    "C2": ("donnée", "DISTILLED", "sessions/.distilled.json"),
    "D":  ("attribut", "BRAIN"),
}

# Trois issues possibles, et une seule est une mesure.
MESURES = ("DEPOT", "AUTRE")


def est_mesure(v):
    """MESURÉ (DEPOT/AUTRE) · NON-APPL (règle inapplicable) · INCONNU (rien lu).
    Aucune conclusion ne se tire d'autre chose qu'une mesure."""
    return v in MESURES


def racine_par_segments(valeur, suffixe):
    """Retire un suffixe de chemin PAR SEGMENTS. None si le suffixe ne colle pas.

    Par segments et pas par chaîne : sous HOME=C, `expanduser("~/.c-brain/trunk")`
    donne `C/claude-brain/...`, et une comparaison de préfixe textuel s'y trompe.
    """
    v = os.path.normpath(valeur).split(os.sep)
    q = os.path.normpath(suffixe).split(os.sep)
    if len(v) <= len(q) or v[-len(q):] != q:
        return None
    return os.sep.join(v[:-len(q)]) or os.sep

# La sonde LIT et ne JUGE PAS : elle rend la valeur brute de l'attribut demandé,
# ou dit pourquoi elle n'a rien pu lire. Le verdict se calcule dans le parent, où
# la règle de lecture est visible.
SONDE = r'''
import importlib.util, json, os, sys
repo = sys.argv[1]
demandes = json.loads(sys.argv[2])
sys.path.insert(0, os.path.join(repo, "hooks"))
out = {}
for rel, attr in demandes:
    p = os.path.join(repo, rel)
    try:
        nom = "sonde_" + rel.replace("/", "_").replace(".", "_").replace("-", "_")
        spec = importlib.util.spec_from_file_location(nom, p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    except Exception as e:
        out[rel] = {"statut": "INCONNU", "raison": "import %s" % type(e).__name__}
        continue
    if not hasattr(m, attr):
        out[rel] = {"statut": "INCONNU", "raison": "attribut %s absent" % attr}
        continue
    v = getattr(m, attr)
    if isinstance(v, str) and v:
        out[rel] = {"statut": "BRUT", "valeur": v}
    else:
        out[rel] = {"statut": "INCONNU", "raison": "%s vide ou non textuel" % attr}
print(json.dumps(out))
'''


def sonder(repo, env=None, cwd=None):
    """Renvoie {classe: (verdict, détail)} pour un dépôt donné.

    verdict : 'DEPOT'    = il a résolu le dépôt où il se trouve (l'invariant tient)
              'AUTRE'    = il a résolu un autre arbre           (l'invariant tombe)
              'NON-APPL' = la règle de lecture déclarée ne s'applique plus à ce
                           module — on refuse de deviner
              'INCONNU'  = rien n'a pu être lu (import cassé, attribut absent)

    Seuls DEPOT et AUTRE sont des MESURES. Les deux autres sont des états
    explicites : aucun verdict aval ne se calcule à partir d'eux.
    """
    e = dict(os.environ)
    e.pop("BRAIN_HOME", None)
    if env:
        e.update(env)
    f = os.path.join(tempfile.gettempdir(), "sonde_racine_%d.py" % os.getpid())
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(SONDE)
    try:
        demandes = [[rel, LECTURE[cl][1]] for cl, rel, _ in REPRESENTANTS]
        r = subprocess.run([sys.executable, f, repo, json.dumps(demandes)],
                           capture_output=True, text=True, cwd=cwd or repo, env=e)
        brut = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
    except Exception:
        brut = {}
    finally:
        if os.path.exists(f):
            os.remove(f)
    attendu = os.path.realpath(repo)
    res = {}
    for cl, rel, _ in REPRESENTANTS:
        regle = LECTURE[cl]
        lu = brut.get(rel) or {"statut": "INCONNU", "raison": "sonde muette"}
        if lu.get("statut") != "BRUT":
            res[cl] = ("INCONNU", lu.get("raison", "?"))
            continue
        valeur = lu["valeur"]
        if regle[0] == "donnée":
            racine = racine_par_segments(valeur, regle[2])
            if racine is None:
                res[cl] = ("NON-APPL", "%s = %s — le suffixe %s ne colle plus"
                                       % (regle[1], valeur, regle[2]))
                continue
            valeur = racine
        res[cl] = ("DEPOT" if os.path.realpath(valeur) == attendu else "AUTRE", valeur)
    return res


# ── L'ÉTAT MESURÉ LE 2026-08-20, figé ────────────────────────────────────────
# Ce n'est PAS l'état souhaitable. C'est l'état constaté, gelé pour que toute
# évolution — dégradation OU migration — se voie.
# ⚠️ TRANSITION CONSIGNÉE (2026-08-21). La colonne **C** portait l'état gelé le 2026-08-20 :
# « ignore tout, y compris BRAIN_HOME explicite ». Son représentant `ronde_annonce.py` a été
# MIGRÉ depuis, et sa conformité est prouvée AILLEURS que par ce banc — contre-épreuve
# comportementale A/B/C/D du lot I-1 #1. L'attendu de C suit donc la migration ; il ne
# « descend » pas pour faire passer un test.
# La colonne **C2** (`mark_distilled.py`) conserve l'observation historique : un consommateur
# de l'ancienne classe C qu'aucune variable ne détourne. L'état initial n'est pas effacé, il
# change de porteur.
ATTENDU = {
    "1. tronc auteur, BRAIN_HOME absent":      {"A": "DEPOT", "B": "DEPOT", "C": "DEPOT", "D": "DEPOT", "C2": "DEPOT"},
    "2. clone, BRAIN_HOME absent":             {"A": "AUTRE", "B": "DEPOT", "C": "DEPOT", "D": "DEPOT", "C2": "AUTRE"},
    "3. worktree, BRAIN_HOME absent":          {"A": "AUTRE", "B": "DEPOT", "C": "DEPOT", "D": "DEPOT", "C2": "AUTRE"},
    "4. clone, BRAIN_HOME explicite":          {"A": "DEPOT", "B": "DEPOT", "C": "DEPOT", "D": "DEPOT", "C2": "AUTRE"},
    "5. worktree, BRAIN_HOME explicite":       {"A": "DEPOT", "B": "DEPOT", "C": "DEPOT", "D": "DEPOT", "C2": "AUTRE"},
    "6. clone, BRAIN_HOME défini mais VIDE":   {"A": "AUTRE", "B": "DEPOT", "C": "DEPOT", "D": "DEPOT", "C2": "AUTRE"},
    "7. clone, cwd extérieur au dépôt":        {"A": "AUTRE", "B": "DEPOT", "C": "DEPOT", "D": "DEPOT", "C2": "AUTRE"},
    "8. clone atteint PAR UN SYMLINK":         {"A": "AUTRE", "B": "DEPOT", "C": "DEPOT", "D": "DEPOT", "C2": "AUTRE"},
}


def bac():
    """Clone + worktree + symlink, tous jetables. Le tronc auteur n'est pas écrit."""
    d = tempfile.mkdtemp(prefix="racine-canonique-")
    clone = os.path.join(d, "clone")
    subprocess.run(["git", "clone", "--local", "--quiet", BRAIN, clone], check=True,
                   capture_output=True)
    wt = os.path.join(d, "worktree")
    subprocess.run(["git", "-C", clone, "worktree", "add", "--quiet", "--detach", wt, "HEAD"],
                   check=True, capture_output=True)
    lien = os.path.join(d, "lien-vers-clone")
    os.symlink(clone, lien)
    return d, clone, wt, lien


def mesurer(clone, wt, lien):
    return {
        "1. tronc auteur, BRAIN_HOME absent":    sonder(BRAIN),
        "2. clone, BRAIN_HOME absent":           sonder(clone),
        "3. worktree, BRAIN_HOME absent":        sonder(wt),
        "4. clone, BRAIN_HOME explicite":        sonder(clone, {"BRAIN_HOME": clone}),
        "5. worktree, BRAIN_HOME explicite":     sonder(wt, {"BRAIN_HOME": wt}),
        "6. clone, BRAIN_HOME défini mais VIDE": sonder(clone, {"BRAIN_HOME": ""}),
        "7. clone, cwd extérieur au dépôt":      sonder(clone, cwd=tempfile.gettempdir()),
        "8. clone atteint PAR UN SYMLINK":       sonder(lien),
    }


def cas_obeissance_croisee(clone, wt):
    """TROU COMBLÉ le 2026-08-20. La matrice pose toujours BRAIN_HOME ÉGAL au
    dépôt sondé : un dialecte qui CESSERAIT de lire la variable y resterait vert,
    puisque les deux comportements donnent le même chemin. Ici BRAIN_HOME pointe
    un AUTRE dépôt que celui où vit le script : seul un lecteur réel le suit."""
    res = sonder(clone, {"BRAIN_HOME": wt})
    cible = os.path.realpath(wt)
    out = {}
    for cl, _, _ in REPRESENTANTS:
        verdict, detail = res[cl]
        # UN NON-MESURÉ NE CONCLUT PAS. Avant le 2026-08-21, un module dont la
        # racine était illisible ressortait ici « IGNORE BRAIN_HOME » — une
        # non-mesure déguisée en constat, verte de surcroît. Trois états désormais :
        # True = suit · False = ignore · None = pas mesuré, et ça se dit.
        if not est_mesure(verdict):
            out[cl] = (None, "%s — %s" % (verdict, detail))
            continue
        out[cl] = (os.path.realpath(detail) == cible, detail)
    return out


# Qui DOIT suivre BRAIN_HOME quand il désigne un autre dépôt. Mesuré le 2026-08-20.
OBEISSANCE_ATTENDUE = {"A": True, "B": True, "C": True, "C2": False, "D": True}


def cas9_realpath(clone, lien):
    """Deux chemins, un seul arbre : la racine résolue doit être IDENTIQUE."""
    par_reel = sonder(clone, {"BRAIN_HOME": clone})
    par_lien = sonder(lien, {"BRAIN_HOME": lien})
    ecarts = []
    for cl, _, _ in REPRESENTANTS:
        a, b = par_reel[cl][1], par_lien[cl][1]
        if os.path.realpath(a) != os.path.realpath(b):
            ecarts.append((cl, a, b))
    return ecarts


def cas11_cli(wt):
    """Le VRAI point d'entrée. Observable différentiel : si la sortie obtenue
    depuis le worktree est IDENTIQUE à celle obtenue depuis le tronc auteur,
    c'est que le CLI n'a pas vu où il était lancé."""
    if not shutil.which("brain"):
        return None, "capacité absente : le CLI `brain` n'est pas dans le PATH"
    def run(cwd):
        r = subprocess.run(["brain", "doctor"], capture_output=True, text=True, cwd=cwd)
        m = re.search(r"(\d+)\s+fiches.*?(\d+)\s+modif", r.stdout + r.stderr, re.S)
        return (m.group(1), m.group(2)) if m else None
    return (run(wt), run(BRAIN)), None


def cas6_shell():
    """Y a-t-il seulement un consommateur SHELL de BRAIN_HOME ? Répondre
    explicitement plutôt que de laisser croire que le cas est couvert."""
    lecteurs = []
    for rel in ("brain", "hooks/selftest.sh", "tools/git-hooks/pre-commit"):
        p = os.path.join(BRAIN, rel)
        if os.path.exists(p):
            s = open(p, encoding="utf-8", errors="replace").read()
            if re.search(r'\$\{?BRAIN_HOME', s):
                lecteurs.append(rel)
    return lecteurs


def rapport(check=False):
    d, clone, wt, lien = bac()
    try:
        obs = mesurer(clone, wt, lien)
        echecs = []
        if not check:
            print("\nRACINE CANONIQUE — « quel Brain ce processus mesure-t-il ? »\n")
            print("  MESURÉ    · DEPOT = il mesure le dépôt où il se trouve"
                  " · AUTRE = il mesure un autre arbre")
            print("  NON MESURÉ · NON-APPL = la règle de lecture ne s'applique plus"
                  " · INCONNU = rien n'a pu être lu\n")
            print("  %-40s %s" % ("", "  ".join("%-8s" % c for c, _, _ in REPRESENTANTS)))
        for nom in ATTENDU:
            ligne = obs[nom]
            if not check:
                print("  %-40s %s" % (nom, "  ".join("%-8s" % ligne[c][0] for c, _, _ in REPRESENTANTS)))
            for cl, _, _ in REPRESENTANTS:
                v, chemin = ligne[cl]
                if v != ATTENDU[nom][cl]:
                    echecs.append("%s · classe %s : %s attendu, %s observé (%s)"
                                  % (nom, cl, ATTENDU[nom][cl], v, chemin))

        # obéissance croisée — BRAIN_HOME désigne un AUTRE dépôt
        ob = cas_obeissance_croisee(clone, wt)
        if not check:
            print("\n  8 bis. obéissance CROISÉE — BRAIN_HOME désigne un autre dépôt")
            for cl, _, _ in REPRESENTANTS:
                etat, det = ob[cl]
                if etat is None:
                    print("     ⛔  classe %s : NON MESURÉ (%s) — rien n'en est conclu" % (cl, det))
                else:
                    print("     %s  classe %s : %s"
                          % ("✅" if etat == OBEISSANCE_ATTENDUE[cl] else "❌",
                             cl, "suit BRAIN_HOME" if etat else "IGNORE BRAIN_HOME"))
        for cl, _, _ in REPRESENTANTS:
            etat, det = ob[cl]
            if etat is None:
                echecs.append("obéissance croisée · classe %s : NON MESURÉ (%s) — "
                              "un instrument qui ne mesure pas ne conclut pas" % (cl, det))
            elif etat != OBEISSANCE_ATTENDUE[cl]:
                echecs.append("obéissance croisée · classe %s : %s attendu, %s observé"
                              % (cl, "suit" if OBEISSANCE_ATTENDUE[cl] else "ignore",
                                 "suit" if etat else "ignore"))

        # cas 9
        ecarts = cas9_realpath(clone, lien)
        if not check:
            print("\n  9. deux chemins → un seul arbre : racines identiques ?")
            print("     %s" % ("✅ identiques pour les %d dialectes" % len(REPRESENTANTS)
                               if not ecarts
                               else "❌ divergent : %s" % ecarts))
        if ecarts:
            echecs.append("cas 9 : realpath ne réconcilie pas %s" % [e[0] for e in ecarts])

        # cas 10
        c4 = obs["4. clone, BRAIN_HOME explicite"]["C"][0]
        c2_4, c2_det = obs["4. clone, BRAIN_HOME explicite"]["C2"]
        if not check:
            print("\n  10. les deux cas NOMMÉS de l'ancienne classe C")
            print("     %s ronde_annonce.py : migration I-1 enregistrée, BRAIN_HOME %s"
                  % (("✅", "explicite honoré") if c4 == "DEPOT"
                     else ("❌", "IGNORÉ — la migration a régressé")))
            if not est_mesure(c2_4):
                print("     ⛔ mark_distilled.py : %s — %s" % (c2_4, c2_det))
                print("        AUCUNE conclusion : la règle de lecture ne mesure rien ici.")
            elif c2_4 == "AUTRE":
                print("     ✅ mark_distilled.py : toujours non conforme — dette I-1 nommée, attendu")
            else:
                print("     ⓘ mark_distilled.py : n'ignore plus BRAIN_HOME —"
                      " migration à consigner à son tour")
        if c4 != "DEPOT":
            echecs.append("cas 10 : la migration de ronde_annonce a régressé")

        # cas 11
        res, absent = cas11_cli(wt)
        if not check:
            print("\n  11. CLI réel `brain doctor`, lancé dans le worktree")
            if absent:
                print("     ⓘ  %s" % absent)
            elif res and res[0] and res[0] == res[1]:
                print("     ❌ sortie IDENTIQUE depuis le worktree et depuis le tronc auteur")
                print("        (%s fiches, %s modifs) → le CLI n'a pas vu où il était lancé"
                      % res[0])
            elif res and res[0]:
                print("     ✅ sorties différentes → le CLI distingue son emplacement")
            else:
                print("     ⓘ  sortie du CLI non interprétable — état explicite, pas de repli")

        # cas 6, versant shell
        lect = cas6_shell()
        if not check:
            print("\n  6 bis. consommateurs SHELL de BRAIN_HOME parmi les points d'entrée")
            print("     %s" % ("ⓘ  AUCUN — le versant shell de la clause 4 de la spec est"
                               " SANS OBJET aujourd'hui" if not lect else "lecteurs : %s" % lect))

        # cas 12 — contrôle négatif
        if not check:
            ok = all(obs["1. tronc auteur, BRAIN_HOME absent"][c][0] == "DEPOT"
                     for c, _, _ in REPRESENTANTS)
            print("\n  12. contrôle négatif — tronc auteur normal")
            print("     %s" % ("✅ les %d dialectes convergent : le défaut y est invisible"
                               % len(REPRESENTANTS)
                               if ok else "❌ le tronc auteur lui-même diverge"))
            rouges = sorted({cl for nom in ATTENDU for cl in ATTENDU[nom]
                             if ATTENDU[nom][cl] == "AUTRE"})
            print("\n  " + "-" * 72)
            print("  CLASSES ROUGES AUJOURD'HUI : %s" % ", ".join(rouges))
            print("  Le vert de ce banc signifie « rien n'a bougé », pas « tout va bien ».")

        if echecs:
            print("\n❌ ÉCART À L'ÉTAT FIGÉ DU 2026-08-20 :")
            for e in echecs:
                print("     %s" % e)
            print("\n   Une classe devenue ROUGE est une régression.")
            print("   Une classe devenue VERTE est une migration : la consigner ICI,")
            print("   dans ATTENDU, et dire pourquoi dans le commit.")
            return 1
        if not check:
            print("\n✅ conforme à l'état figé du 2026-08-20.")
        return 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sabotages():
    """Un banc dont personne n'a vu le rouge n'est pas une barrière."""
    print("\nSABOTAGES — sur des COPIES ; le tronc auteur n'est jamais écrit.\n")
    d, clone, wt, lien = bac()
    resultats = []
    try:
        cible = os.path.join(clone, "tests", "invariants_brain.py")  # classe D, la saine
        sain = open(cible, encoding="utf-8").read()

        def rejouer(titre, nouveau, sonde_args, attendu_verdict):
            open(cible, "w", encoding="utf-8").write(nouveau)
            r = sonder(*sonde_args)["D"][0]
            open(cible, "w", encoding="utf-8").write(sain)
            ok = r == attendu_verdict
            resultats.append(ok)
            print("  %s %-58s %s attendu, %s observé"
                  % ("✅" if ok else "❌", titre, attendu_verdict, r))

        # S1 — un résolveur sain forcé sur le tronc auteur
        rejouer("S1 · classe D recâblée en dur sur ~/.c-brain/trunk",
                sain.replace(
                    'os.environ.get("BRAIN_HOME")\n    or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")',
                    'os.path.expanduser("~/.c-brain/trunk")'),
                (clone, {"BRAIN_HOME": clone}), "AUTRE")

        # S2 — realpath remplacé par abspath : le cas symlink doit rougir
        open(cible, "w", encoding="utf-8").write(sain.replace("os.path.realpath(", "os.path.abspath(", 1))
        r = sonder(lien, {"BRAIN_HOME": lien})["D"]
        open(cible, "w", encoding="utf-8").write(sain)
        ok = os.path.realpath(r[1]) == os.path.realpath(lien) and r[1] != os.path.realpath(lien)
        resultats.append(ok)
        print("  %s %-58s chemin non canonique : %s"
              % ("✅" if ok else "❌", "S2 · realpath → abspath, atteint par symlink", r[1]))

        # S3 — BRAIN_HOME ignoré : jugé par l'OBÉISSANCE CROISÉE, seule capable
        # de distinguer « lit la variable » de « ne la lit pas ».
        open(cible, "w", encoding="utf-8").write(
            sain.replace('os.environ.get("BRAIN_HOME")\n    or ', ''))
        suit, _det = cas_obeissance_croisee(clone, wt)["D"]
        open(cible, "w", encoding="utf-8").write(sain)
        # `suit` vaut True / False / None depuis le 2026-08-21. Le dépaqueter :
        # un tuple non vide est TOUJOURS vrai, et `not (False, chemin)` vaut False.
        detecte = suit is False
        resultats.append(detecte)
        print("  %s %-58s %s"
              % ("✅" if detecte else "❌", "S3 · classe D cesse de lire BRAIN_HOME",
                 "n'obéit plus — détecté" if detecte
                 else ("obéit encore : sabotage INVISIBLE" if suit
                       else "NON MESURÉ (%s) — le sabotage n'est pas jugé" % _det)))

        # S4 — contrôle POSITIF : rien de saboté, BRAIN_HOME correct
        r = sonder(clone, {"BRAIN_HOME": clone})["D"][0]
        ok = r == "DEPOT"
        resultats.append(ok)
        print("  %s %-58s DEPOT attendu, %s observé"
              % ("✅" if ok else "❌", "S4 · contrôle — aucun sabotage, BRAIN_HOME correct", r))

        # S5 — capacité absente : état explicite, jamais repli silencieux
        faux = os.path.join(d, "pas-un-depot")
        os.makedirs(faux, exist_ok=True)
        r = sonder(faux)
        explicite = all(not est_mesure(v[0]) for v in r.values())
        resultats.append(explicite)
        print("  %s %-58s %s"
              % ("✅" if explicite else "❌", "S5 · dossier qui n'est pas un Brain",
                 "aucune classe ne MESURE — état explicite" if explicite
                 else "certaines ont résolu quand même : %s" % {k: v[0] for k, v in r.items()}))

        # ── La règle de lecture de C2 est elle-même un instrument : elle doit
        #    savoir rougir, et savoir se taire. S6 et S7 posés le 2026-08-21.
        md = os.path.join(clone, "hooks", "mark_distilled.py")
        sain_md = open(md, encoding="utf-8").read()
        LITTERAL = 'DISTILLED = os.path.expanduser("~/.c-brain/trunk/sessions/.distilled.json")'

        def rejouer_c2(titre, nouveau, attendu_verdict):
            # Un sabotage qui ne change rien ne prouve rien : on l'exige d'abord.
            assert nouveau != sain_md, "sabotage VIDE : %s" % titre
            open(md, "w", encoding="utf-8").write(nouveau)
            try:
                v = sonder(clone, {"BRAIN_HOME": clone})["C2"]
            finally:
                open(md, "w", encoding="utf-8").write(sain_md)
            ok = v[0] == attendu_verdict
            resultats.append(ok)
            print("  %s %-58s %s attendu, %s observé"
                  % ("✅" if ok else "❌", titre, attendu_verdict, v[0]))

        # S6 — mark_distilled MIGRÉ dans la copie : la migration doit SE VOIR.
        rejouer_c2("S6 · C2 migré (DISTILLED dérivé du dépôt)",
                   sain_md.replace(LITTERAL,
                       'DISTILLED = os.path.join(\n'
                       '    os.environ.get("BRAIN_HOME")\n'
                       '    or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),\n'
                       '    "sessions", ".distilled.json")'),
                   "DEPOT")

        # S7 — la donnée change de place : la règle ne s'applique plus. Elle doit
        #      le DIRE, pas produire un verdict par habitude.
        rejouer_c2("S7 · la donnée de C2 quitte sessions/.distilled.json",
                   sain_md.replace("~/.c-brain/trunk/sessions/.distilled.json",
                                   "~/.c-brain/trunk/state/distilled.json"),
                   "NON-APPL")

        print("\n%s" % ("✅ le banc sait rougir sur les %d sabotages." % len(resultats)
                        if all(resultats) else
                        "❌ un sabotage n'a PAS produit le rouge attendu — le banc ne prouve rien."))
        return 0 if all(resultats) else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    if "--sabotage" in sys.argv:
        sys.exit(sabotages())
    sys.exit(rapport(check="--check" in sys.argv))
