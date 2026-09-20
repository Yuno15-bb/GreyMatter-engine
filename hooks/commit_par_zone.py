#!/usr/bin/env python3
"""commit_par_zone — sauvegarde le tronc dans git, UNE ZONE PAR COMMIT.

Appelé à la fin de chaque session par auto_maintain, après le passage des
agents. Purement mécanique : aucun LLM, aucun réseau, rien qui sorte de la
machine.

POURQUOI PAS `git add -A`
    C'est ce que faisait la sauvegarde automatique jusqu'au 2026-08-13, et
    c'est ce qui a noyé 19 fichiers d'un chantier en cours dans le commit
    e61fd01 (2026-08-03) : un commit fourre-tout raconte plusieurs histoires
    et son message n'en dira qu'une. 612 commits de ce type dorment dans
    l'historique du Brain de l'auteur.
    Ici, chaque zone part dans son propre commit, avec son propre message —
    un chantier en cours reste identifiable au lieu d'être noyé.

SOUS VERROU DEPUIS LE 2026-08-26 (ADR-0017 phase 3)
    Chaque zone est une transaction `git_guard` : verrou dédié `state/git.lock`, identité
    attribuable, journal, périmètre porté par la commande (`git commit -- <zone>`). Si le
    verrou est tenu, la zone est REPORTÉE — jamais forcée. Si `git_guard` est introuvable,
    ce script ne commite rien du tout : il n'existe aucun repli vers git direct.

CE QU'IL NE FAIT PAS
    Il ne POUSSE rien. Un tronc contient des notes personnelles ; les envoyer
    vers un dépôt distant est une décision de son propriétaire, pas l'effet de
    bord d'une fin de session. (L'auteur, lui, pousse le sien depuis
    `tools/sync_depots.py`, qui ne fait pas partie du paquet.)

Usage :
  commit_par_zone.py             commite
  commit_par_zone.py --dry-run   dit ce qu'il ferait, n'écrit rien
"""
import os, sys, subprocess

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))

# ── LA PRIMITIVE EST OBLIGATOIRE — ADR-0017 phase 3 ─────────────────────────
# Si `git_guard` est introuvable, ce producteur NE COMMITE PAS. Il n'existe aucun repli
# vers un appel git direct : un repli transformerait la panne du garde-fou en retour
# silencieux au comportement qui a corrompu l'index le 2026-08-25. Une absence de commit
# est visible et rattrapable ; un commit non gouverné ne l'est pas.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import git_guard
    _GUARD_INDISPO = None
except Exception as _e:                                        # pragma: no cover
    git_guard = None
    _GUARD_INDISPO = "%s: %s" % (type(_e).__name__, _e)

# Attente avant de renoncer à une zone. 60 s : au-dessus d'une transaction locale
# (2,0–2,7 s mesurés) pour ne pas sauter une zone à la première concurrence, en dessous
# du TTL de 300 s pour ne jamais confondre « quelqu'un travaille » et « verrou mort ».
ATTENTE = 60.0

# ⚠️ CETTE TABLE EST UNE COPIE de celle du hook pre-commit, malgré ce que le commentaire
# d'origine affirmait ici (« on emploie SA table, pas une copie »). Elle l'a toujours été :
# le hook est du shell, ce module du Python. Une déclaration ne rend pas une copie unique.
# Tant qu'elles coexistent, tests/zones_de_commit.py rougit dès qu'elles s'écartent.
ZONES = (("hooks/", "moteur"), ("tests/", "moteur"), ("companion/", "moteur"),
         ("cbrain/", "moteur"), ("capsule/", "moteur"),
         ("projects/", "savoir"), ("lessons/", "savoir"), ("meta/", "savoir"),
         ("life/", "savoir"), ("agents/", "savoir"), ("skills/", "savoir"),
         ("sessions/", "archives"))
LIBELLE = {"moteur": "moteur : hooks, tests et capsule",
           "savoir": "savoir : fiches, leçons et cartes",
           "archives": "archives : sessions et journaux",
           "racine": "racine : cartes de démarrage, audits et outillage"}
ORDRE = ("archives", "savoir", "racine", "moteur")


def _artefacts_du_garde(cwd):
    """Chemins relatifs des fichiers que git_guard écrit dans le dépôt.

    POURQUOI CETTE EXCLUSION EXISTE. Elle a été trouvée par le banc, pas par relecture :
    `state/` est ignoré dans le tronc de l'auteur, mais RIEN ne le garantit ailleurs, et
    sans cette barrière un dépôt sans la règle d'ignore commiterait `state/git.lock`
    ALORS QU'IL EST TENU — un verrou vivant figé dans l'historique. La primitive ne doit
    jamais pouvoir se faire capturer par le producteur qu'elle gouverne."""
    if git_guard is None:
        return set()
    _, lock, journal = git_guard._chemins(cwd)
    racine = os.path.realpath(cwd)
    return {os.path.relpath(x, racine) for x in (lock, journal)}


def _origine():
    """D'où vient cet appel ? Le nom du processus parent, lu sur le système.

    ADR-0017 exige une identité attribuable, et « unknown » n'en est pas une quand
    l'appelant PEUT être connu. `auto_maintain` lance ce script par un shell : le parent
    dit donc au moins par quel chemin on est arrivé. Aucun appelant n'est modifié pour
    ça — c'est le producteur qui se renseigne sur lui-même."""
    try:
        r = subprocess.run(["ps", "-o", "command=", "-p", str(os.getppid())],
                           capture_output=True, text=True, timeout=5)
        return (r.stdout.strip() or None)
    except Exception:
        return None


def zone(f):
    for prefixe, z in ZONES:
        if f.startswith(prefixe):
            return z
    return "racine"


def sh(cmd, cwd, timeout=180):
    """Renvoie (code, sortie). Jamais d'exception : ce script ne doit rien casser."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except Exception as e:
        return 1, str(e)


def modifies(cwd):
    _, out = sh(["git", "status", "--porcelain"], cwd)
    return [l[3:].strip().strip('"') for l in out.splitlines() if l.strip()]


def commit_par_zone(cwd, prefixe_msg="auto: ", dry=False, sid=None):
    """Un commit par zone, sous verrou git_guard. Renvoie le nombre de commits posés.

    LES DEUX `git reset` ONT ÉTÉ RETIRÉS (2026-08-26, ADR-0017 phase 3). Ils n'ont pas été
    supprimés par confort : leur rôle a été instruit, mesuré, et remplacé.

      · le reset de DÉBUT de boucle servait de précondition à « commiter l'index » : il
        vidait l'index pour que `git add -- <zone>` puis `git commit` ne prennent que
        cette zone. Ce rôle est désormais tenu par `git commit -- <zone>`, qui borne le
        commit par la COMMANDE et non par un état partagé qu'un tiers peut changer entre
        le contrôle et l'usage. Mesuré : S4 contamine 10/10 sans pathspec, 0/10 avec.
      · le reset FINAL était de l'hygiène : laisser l'index propre. Il est inutile — le
        commit consomme notre propre staging — et il est NUISIBLE.

    POURQUOI NUISIBLE, ET CE N'EST PAS THÉORIQUE. Un `git reset` global détruit le
    staging de TOUT LE MONDE. Mesuré le 2026-08-26 dans un dépôt jetable : un fichier
    stagé par un tiers SURVIT à `git commit -- <mon plan>` et est DÉTRUIT par
    `git reset`. Et au moment d'écrire ces lignes, le tronc portait justement deux
    fichiers stagés par un agent — l'ancien code les aurait effacés.

    CE QUI RESTE NÉCESSAIRE : le `git add`. Mesuré aussi — `git commit -- <fichier neuf>`
    échoue avec « pathspec did not match any file(s) known to git » tant que le fichier
    n'est pas connu de git. Le add ne borne rien, il rend committable ; c'est le pathspec
    qui borne.
    """
    if git_guard is None:
        print(f"    ⛔ git_guard indisponible ({_GUARD_INDISPO}) — AUCUN commit.")
        print("       Pas de repli vers git direct : ADR-0017 l'interdit explicitement.")
        return 0

    origine = _origine()
    exclus = _artefacts_du_garde(cwd)
    sid = sid or os.environ.get("CLAUDE_CODE_SESSION_ID")
    poses = 0
    for z in ORDRE:
        sel = [f for f in modifies(cwd) if zone(f) == z and f not in exclus]
        if not sel:
            continue
        if dry:
            # Lecture pure : aucune mutation, donc aucun verrou. Prendre le verrou pour
            # une simulation le retirerait à un acteur qui, lui, a du travail à faire.
            print(f"    [dry] {z:9} {len(sel):4d} fichier(s)")
            poses += 1
            continue

        with git_guard.transaction("commit_par_zone", f"commit-zone:{z}", sel, depot=cwd,
                                   sid=sid, attente=ATTENTE,
                                   extra={"origine": origine, "zone": z}) as jeton:
            if jeton:
                # LE PLAN SE RECALCULE SOUS LE VERROU. Le `sel` ci-dessus n'a servi qu'à
                # décider s'il valait la peine de demander le verrou ; entre ce coup d'œil
                # et l'acquisition, un agent a pu écrire. Committer la liste d'AVANT serait
                # exactement le contrôle-puis-usage que ce chantier existe pour supprimer.
                # Le jeton porte le plan RÉEL, sinon le journal certifierait un périmètre
                # qui n'est pas celui du commit.
                sel = [f for f in modifies(cwd) if zone(f) == z and f not in exclus]
                jeton["perimetre"] = sel
                if not sel:
                    continue
            if not jeton:
                # Refusé : un autre acteur détient git. On le DIT, on ne contourne pas.
                d = git_guard.diagnostic(cwd)
                p = (d.get("proprietaire") or {}).get("acteur", "?")
                print(f"    ⏸  {z:9} verrou tenu par « {p} » — zone reportée, rien de forcé")
                continue

            code, _ = sh(["git", "add", "--"] + sel, cwd)
            if code:
                continue
            # Pas de ligne « Co-Authored-By » ici : ce commit est pose dans le depot
            # de son proprietaire par sa propre machine. Y coller une adresse mail —
            # fut-elle publique — a la fois salit son historique et fait rougir
            # leakcheck, qui traque les adresses dans TOUT ce qui part dans le paquet.
            msg = (f"{prefixe_msg}{LIBELLE[z]}\n\n"
                   f"Commit automatique par zone ({len(sel)} fichier(s)).\n"
                   f"Une zone par commit : un chantier en cours reste identifiable "
                   f"dans l'historique au lieu d'etre noye par un `git add -A`.\n")
            # Auteur « C Brain » : un commit posé par la machine ne doit pas
            # porter la signature de l'humain.
            # `-- ` + sel : le PÉRIMÈTRE EST PORTÉ PAR LA COMMANDE. Même si l'index a
            # changé sous nos pieds, ce commit ne peut contenir que `sel`.
            r = subprocess.run(["git", "-c", "user.name=C Brain",
                                "-c", "user.email=brain@local",
                                "commit", "-q", "-F", "-", "--"] + sel, cwd=cwd,
                               input=msg, text=True, capture_output=True)
            if r.returncode == 0:
                print(f"    ✅ {z:9} {len(sel):4d} fichier(s)")
                poses += 1
            else:
                # le hook pre-commit du tronc peut refuser : on le DIT, on n'insiste pas.
                # ON MONTRE LA FIN, PAS LE DÉBUT — corrigé le 2026-09-19. Ce refus
                # affichait les 120 premiers caractères, c'est-à-dire le « ✅ 15 bancs au
                # vert » que le hook imprime AVANT de rendre la main. Le message disait
                # donc exactement le contraire de ce qui se passait, et la vraie erreur
                # — « error: Error building trees » — restait invisible. Il a fallu
                # rejouer le commit à la main pour la voir.
                lignes = [l for l in (r.stdout + r.stderr).strip().splitlines()
                          if l.strip() and not l.startswith("✅")]
                print(f"    ⚠️  {z:9} refusé :")
                for l in lignes[-6:]:
                    print(f"         {l.strip()[:150]}")
                # On défait NOTRE staging, et lui seul. Un `git reset` global rendrait
                # l'échec d'une zone destructeur pour le travail d'un tiers.
                sh(["git", "restore", "--staged", "--"] + sel, cwd)
    return poses


# LA RÉGÉNÉRATION DU GRAPHE N'EST PLUS ICI (2026-08-20, chantier B5).
# Elle a vécu dans cette fonction une demi-journée, le temps de comprendre qu'elle
# n'y couvrait qu'un seul chemin : un `git commit` manuel, lui, laissait
# `planet/graph.json` sur le HEAD d'avant, et l'invariant refusait le commit
# suivant. Deux producteurs pour la même opération auraient régénéré deux fois par
# commit. Le déclenchement vit donc désormais dans `tools/git-hooks/post-commit`,
# installé aussi sous `post-merge` — là où TOUS les écrivains passent, automatiques
# comme manuels. `hooks/graph_export.py` reste, comme avant, la seule définition.
def main():
    dry = "--dry-run" in sys.argv
    code, _ = sh(["git", "rev-parse", "--git-dir"], BRAIN)
    if code:
        print("  tronc hors git — rien à sauvegarder")   # cas normal : personne n'a fait `git init`
        return 0
    n = len(modifies(BRAIN))
    if not n:
        print("  rien à commiter")
        return 0
    print(f"  {n} fichier(s) modifié(s)")
    commit_par_zone(BRAIN, dry=dry)
    # Rien à régénérer ici : chaque commit posé ci-dessus a déclenché le hook
    # `post-commit` du dépôt, qui s'en charge — et qui couvre aussi le commit
    # manuel, que ce script ne voit jamais passer.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"commit_par_zone : {e}")
        sys.exit(0)                              # ne casse JAMAIS l'appelant
