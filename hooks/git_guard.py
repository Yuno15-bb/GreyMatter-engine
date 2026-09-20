#!/usr/bin/env python3
"""
git_guard — le verrou DÉDIÉ aux mutations git. Phase 2B d'ADR-0017.

CE QU'IL EST
    Une primitive isolée : elle prend un verrou, laisse faire la transaction, CERTIFIE le
    résultat réel par observation, puis libère et journalise. Elle ne connaît aucun
    producteur et n'en modifie aucun. `commit_par_zone.py`, `sync_depots.py`, `brain push`
    et `auto_maintain.py` ne l'appellent PAS encore — c'est la phase 3 et suivantes.

CE QU'IL N'EST PAS
    Ce n'est pas « git est gouverné ». Tant que les producteurs n'y passent pas, un verrou
    correct ne protège rien de ce qui tourne réellement au SessionEnd.

POURQUOI PAS `maintenance.lock` (ADR-0017)
    *maintenance en cours* ≠ *transaction git en cours*. Les deux se chevauchent parfois,
    ils ne sont pas identiques, et une permission accordée à la maintenance ne doit jamais
    devenir implicitement une permission git. Le MÉCANISME de `hooks/brain_guard.py` est
    repris — création atomique `O_CREAT|O_EXCL`, propriétaire identifiable, récupération de
    zombie ; son FICHIER ne l'est pas.

LE TTL SORT D'UNE MESURE, PAS D'UNE COPIE — 300 s
    `brain_guard` emploie 20 minutes ; les recopier ici n'aurait eu aucune justification.
    Mesuré le 2026-08-26 sur un clone du tronc : une transaction `add + commit` avec les
    hooks réels prend **2,0 à 2,7 s**. Mais un `push` porte `timeout=180` dans
    `sync_depots.py` — une transaction qui publie peut donc légitimement durer ~3 minutes.
    300 s couvre ce cas le plus long avec de la marge, et reste 4 fois plus court que
    `brain_guard`, dont l'échelle est celle d'une maintenance, pas d'une opération git.

⚠️ LE TTL NE VOLE JAMAIS UN VERROU. C'est la règle la plus importante de ce fichier.
    Un verrou n'est récupérable que si son propriétaire est PROUVÉ MORT — processus
    disparu, ou PID réutilisé par un autre processus. Un propriétaire VIVANT garde son
    verrou quel que soit son âge : le TTL ne fait alors qu'élever le ton du journal
    (`verrou_ancien_mais_vivant`). Voler un verrou vivant parce qu'il est « ancien »
    remplacerait une course par une corruption silencieuse — un `git push` lent n'est pas
    un zombie.

LE PID NE SUFFIT PAS À IDENTIFIER UN PROPRIÉTAIRE
    Un PID est réutilisé. `os.kill(pid, 0)` répond « vivant » pour un processus qui n'a
    rien à voir avec celui qui a pris le verrou, et le verrou serait alors gardé pour
    toujours par un innocent. On enregistre donc l'HEURE DE DÉMARRAGE du processus
    (`ps -o lstart=`) : même PID + heure différente = le propriétaire d'origine est mort.
    Si `ps` ne répond pas, on ne conclut PAS — on reste prudent et on ne récupère pas.

AUCUNE PORTE DE SORTIE — ADR-0017
    Pas de variable d'environnement, pas de `--force`, pas de `skip`. Une porte serait
    lisible et positionnable par l'agent qu'elle est censée contraindre, ce qui rendrait
    l'interdit décoratif.

L'IDENTITÉ EST OBLIGATOIRE
    `acteur` doit être une chaîne non vide. Sans elle, l'acquisition est REFUSÉE et
    journalisée : le défaut d'aujourd'hui est précisément qu'aucun journal ne porte
    l'identité de qui a muté quoi.

Usage :
    from git_guard import transaction
    with transaction("commit_par_zone", "commit", ["lessons/x.md"]) as t:
        ...                       # t vaut None si le verrou n'a pas été obtenu
    git_guard.py etat             inspecte le verrou courant
    git_guard.py journal [n]      affiche les n derniers évènements
"""
import contextlib
import json
import os
import subprocess
import sys
import time

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))

TTL = 300.0          # secondes — justifié dans le docstring, PAS un seuil de vol
SONDAGE = 0.05       # pas d'attente quand un appelant accepte de patienter


def _chemins(depot, etat_dir=None, nom="git"):
    """(dépôt, verrou, journal). Le verrou peut vivre AILLEURS que dans le dépôt gouverné.

    POURQUOI CETTE SOUPLESSE EXISTE — mesurée, pas anticipée. Gouverner le dépôt PUBLIC
    voulait dire y écrire `state/git.lock`. Or son `leakcheck.py` balaie TOUS les fichiers
    (`ROOT.rglob("*")`), ne respecte PAS `.gitignore`, et `state` n'est pas dans ses
    `SKIP_DIRS` : le verrou — qui porte l'origine de l'appelant, donc un chemin `/Users/…` —
    y aurait été scanné et aurait pu faire rougir le contrôle, donc BLOQUER la publication.
    Un garde-fou qui empêche l'opération qu'il protège n'en est pas un.
    Le verrou du paquet vit donc dans le `state/` du tronc, sous un nom qui lui est propre.

    BORNE ASSUMÉE : seul un acteur qui connaît le tronc voit ce verrou-là. En pratique
    `sync_depots` est le seul à toucher le paquet ; un `git push` tapé à la main dans
    ~/c-brain-fr ne le verrait pas. C'est une exclusion entre acteurs gouvernés, pas une
    exclusion universelle."""
    d = os.path.realpath(depot or BRAIN)
    e = os.path.realpath(etat_dir) if etat_dir else os.path.join(d, "state")
    suffixe = "" if nom == "git" else "-" + nom
    return d, os.path.join(e, "git%s.lock" % suffixe), os.path.join(e, "git-journal.jsonl")


def _sh(args, cwd, timeout=60):
    """(code, sortie). Ne lève jamais : un échec git est une donnée."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:                                    # pragma: no cover
        return 127, str(e)


def _demarrage(pid):
    """Heure de démarrage du processus, ou None si on ne peut pas savoir.

    None n'est PAS « mort » : c'est « je ne sais pas », et l'appelant doit rester prudent."""
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))],
                           capture_output=True, text=True, timeout=10)
        s = r.stdout.strip()
        return s or None
    except Exception:
        return None


def _vivant(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # existe, mais appartient à quelqu'un d'autre
    except Exception:
        return None          # indéterminé — surtout pas « mort »


def _lire_verrou(lock):
    try:
        return json.load(open(lock, encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return {"_illisible": True}


def journaliser(_depot, _evenement, _etat_dir=None, _nom="git", **champs):
    """Paramètres préfixés d'un `_` DÉLIBÉRÉMENT, et ce n'est pas cosmétique.

    Sans ça, un appelant qui journalise un champ nommé `depot` ou `nom` provoque
    « got multiple values for argument 'depot' » — une TypeError levée AVANT le corps de
    la fonction, donc avant tout try/except. Mesuré le 2026-08-27 : `publier()` passait
    `extra={"depot": …}`, l'exception remontait depuis `acquerir()` APRÈS l'écriture
    atomique du verrou mais AVANT que le `with` soit entré, donc sans `finally` pour
    libérer. Résultat : verrou orphelin, journal vide, publication muette.

    Le journal ne doit pas pouvoir être cassé par ce qu'on lui donne à écrire."""
    # JSONL : un journal qui s'ajoute ne se corrompt pas quand deux acteurs écrivent,
    # contrairement à un JSON global relu-modifié-réécrit.
    _, _, jr = _chemins(_depot, _etat_dir, _nom)
    ligne = dict(champs, evenement=_evenement, ts=time.time(),
                 quand=time.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        os.makedirs(os.path.dirname(jr), exist_ok=True)
        with open(jr, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return ligne


def diagnostic(depot=None, etat_dir=None, nom="git"):
    """Décrit le verrou courant SANS le toucher. Rend aussi le verdict de récupérabilité.

    Trois états seulement, et « ancien » n'en est pas un :
      libre · tenu (par un vivant, jeune ou ancien) · recuperable (propriétaire prouvé mort)
    """
    d, lock, _ = _chemins(depot, etat_dir, nom)
    v = _lire_verrou(lock)
    if v is None:
        return {"etat": "libre"}
    if v.get("_illisible"):
        # Un verrou illisible ne peut désigner aucun propriétaire : personne ne peut donc
        # être lésé par sa récupération, et le laisser bloquerait le dépôt pour toujours.
        return {"etat": "recuperable", "raison": "verrou illisible", "proprietaire": None}

    pid, age = v.get("pid"), time.time() - float(v.get("ts") or 0)
    vivant = _vivant(pid)
    demarrage_actuel = _demarrage(pid)
    base = {"proprietaire": v, "age_s": round(age, 1), "pid_vivant": vivant,
            "ttl_s": TTL, "ttl_depasse": age > TTL}

    if vivant is False:
        return dict(base, etat="recuperable", raison="processus %s disparu" % pid)
    if (v.get("demarrage") and demarrage_actuel and demarrage_actuel != v["demarrage"]):
        return dict(base, etat="recuperable",
                    raison="PID %s réutilisé — le propriétaire d'origine est mort" % pid)
    if vivant is None and demarrage_actuel is None:
        # On ne sait pas. On ne récupère pas : préférer un blocage visible à un vol.
        return dict(base, etat="tenu", raison="propriétaire indéterminé — aucune récupération")
    if base["ttl_depasse"]:
        # ⚠️ Le seul endroit où le TTL parle. Il ne donne PAS le droit de prendre.
        return dict(base, etat="tenu", raison="verrou_ancien_mais_vivant")
    return dict(base, etat="tenu", raison="propriétaire vivant")


def _ecrire_atomique(lock, charge):
    """True si on a créé le fichier. O_EXCL ferme la course « deux acteurs voient libre »."""
    try:
        os.makedirs(os.path.dirname(lock), exist_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, json.dumps(charge, ensure_ascii=False).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:
        return False


def acquerir(acteur, operation, perimetre=None, depot=None, sid=None, attente=0.0,
             extra=None, etat_dir=None, nom="git"):
    """Rend un jeton, ou None si le verrou n'a pas été obtenu. Journalise dans les 2 cas."""
    d, lock, _ = _chemins(depot, etat_dir, nom)
    if not isinstance(acteur, str) or not acteur.strip():
        # Identité absente : refus EXPLICITE. Jamais d'attribution silencieuse.
        journaliser(depot, "refus_identite_absente", etat_dir, nom, operation=operation,
                    perimetre=perimetre, pid=os.getpid())
        return None

    # `extra` : ce que l'APPELANT sait de lui-même et que la primitive ne peut pas
    # deviner — son origine, la zone qu'il traite. Les clés du noyau ne sont jamais
    # écrasées : une identité ne se remplace pas depuis l'extérieur.
    charge = dict(extra or {})
    charge.update({"acteur": acteur.strip(), "pid": os.getpid(),
                   "demarrage": _demarrage(os.getpid()), "sid": sid,
                   "operation": operation, "perimetre": perimetre, "ts": time.time(),
                   "head_avant": _sh(["git", "rev-parse", "HEAD"], d)[1]})

    limite = time.time() + max(0.0, float(attente))
    while True:
        if _ecrire_atomique(lock, charge):
            try:
                journaliser(depot, "acquis", etat_dir, nom, **charge)
            except Exception as e:                 # ceinture ET bretelles
                # Le verrou est DÉJÀ pris ; échouer ici sans le rendre laisserait un
                # orphelin que personne n'a demandé. On le retire et on refuse
                # franchement plutôt que de gouverner sans trace.
                try:
                    os.unlink(lock)
                except Exception:
                    pass
                print("git_guard : journal impossible (%s) — acquisition ANNULÉE" % e)
                return None
            return charge

        diag = diagnostic(depot, etat_dir, nom)
        if diag["etat"] == "recuperable":
            # Récupération GOUVERNÉE : on trace qui on retire, et pourquoi, AVANT de retirer.
            journaliser(depot, "recuperation_zombie", etat_dir, nom, acteur=charge["acteur"],
                        pid=charge["pid"], raison=diag.get("raison"),
                        proprietaire_retire=diag.get("proprietaire"))
            try:
                os.unlink(lock)
            except Exception:
                pass
            continue                       # on retente la création atomique, sans la forcer

        if time.time() >= limite:
            journaliser(depot, "refuse", etat_dir, nom, acteur=charge["acteur"], pid=charge["pid"],
                        operation=operation, perimetre=perimetre,
                        proprietaire_actuel=diag.get("proprietaire"),
                        raison=diag.get("raison"), age_du_verrou_s=diag.get("age_s"))
            return None
        time.sleep(SONDAGE)


def liberer(jeton, depot=None, resultat=None, etat_dir=None, nom="git"):
    """Libère, et CERTIFIE le résultat réel par observation — pas par ce que l'appelant croit.

    ADR-0017 : « Plan validé ≠ résultat supposé. » HEAD après et la liste des fichiers
    réellement commités sont LUS sur le dépôt, jamais recopiés depuis l'intention."""
    d, lock, _ = _chemins(depot, etat_dir, nom)
    if not jeton:
        return None
    head_apres = _sh(["git", "rev-parse", "HEAD"], d)[1]
    bouge = head_apres != jeton.get("head_avant")
    fichiers = []
    if bouge and head_apres:
        fichiers = [x for x in _sh(["git", "diff-tree", "--no-commit-id", "--name-only",
                                    "-r", head_apres], d)[1].splitlines() if x]
    # On ne retire QUE son propre verrou : sinon on ferait, en libérant, exactement le vol
    # que la règle du TTL interdit.
    v = _lire_verrou(lock)
    a_nous = bool(v) and not v.get("_illisible") and v.get("pid") == jeton.get("pid") \
        and v.get("ts") == jeton.get("ts")
    if a_nous:
        try:
            os.unlink(lock)
        except Exception:
            pass
    bilan = journaliser(depot, "libere", etat_dir, nom, acteur=jeton.get("acteur"), pid=jeton.get("pid"),
                        operation=jeton.get("operation"), perimetre=jeton.get("perimetre"),
                        head_avant=jeton.get("head_avant"), head_apres=head_apres,
                        head_a_bouge=bouge, fichiers_commites=fichiers,
                        hors_perimetre=sorted(set(fichiers) - set(jeton.get("perimetre") or []))
                        if jeton.get("perimetre") else None,
                        resultat_annonce=resultat, verrou_etait_le_notre=a_nous,
                        duree_s=round(time.time() - float(jeton.get("ts") or 0), 3))
    return bilan


@contextlib.contextmanager
def transaction(acteur, operation, perimetre=None, depot=None, sid=None, attente=0.0,
                extra=None, etat_dir=None, nom="git"):
    """`with transaction(...) as t:` — t vaut None si le verrou n'a pas été obtenu.

    Le corps DOIT vérifier `t` : un `with` qui s'exécute quand même serait un verrou
    décoratif. La libération passe par `finally` — un crash du corps laisse un état
    inspectable dans le journal, jamais un verrou orphelin pris pour vivant."""
    jeton = acquerir(acteur, operation, perimetre, depot, sid, attente, extra, etat_dir, nom)
    try:
        yield jeton
    finally:
        if jeton:
            liberer(jeton, depot, None, etat_dir, nom)


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "etat"
    if cmd == "etat":
        print(json.dumps(diagnostic(), ensure_ascii=False, indent=1))
        return 0
    if cmd == "journal":
        n = int(args[1]) if len(args) > 1 else 20
        _, _, jr = _chemins(None)
        try:
            lignes = open(jr, encoding="utf-8").read().splitlines()[-n:]
        except FileNotFoundError:
            print("journal vide")
            return 0
        for l in lignes:
            try:
                o = json.loads(l)
                print("%s  %-22s %-18s %s" % (o.get("quand"), o.get("evenement"),
                                              o.get("acteur"), o.get("operation") or ""))
            except Exception:
                print(l)
        return 0
    print(__doc__.strip().splitlines()[-4:][0])
    return 2


if __name__ == "__main__":
    sys.exit(main())
