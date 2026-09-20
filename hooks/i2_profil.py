#!/usr/bin/env python3
"""i2_profil — un banc normatif annonce SOUS QUEL ÉTAT il a rendu son verdict.

I-2, lot 1 : DÉCLARER AVANT DE CORRIGER. Ce module ne change aucun score, aucun ordre,
aucun état. Il rend visible ce qui était silencieux.

CE QU'IL DÉCLARE — ce qui a été OBSERVÉ pendant CETTE exécution, jamais un manifeste
statique. La mesure du 2026-08-21 a montré que `golden_recall` lit ou ne lit PAS
`state/recall-utilite.json` selon la fraîcheur du cache : une dépendance annoncée « toujours
présente » serait fausse une fois sur deux.

DEUX NIVEAUX, À NE PAS CONFONDRE
    external_read_observed   ce fichier a été ouvert. C'est un FAIT, pas une preuve.
    verdict_dependency_proven une contre-épreuve a montré que son contenu CHANGE le verdict.
    « Fichier ouvert » ≠ « dépendance causale ». Le second niveau ne se remplit que depuis
    une mesure, jamais depuis une intuition.

repo_reproducible — défini avant d'être utilisé :
    « À HEAD, avec les dépendances versionnées et l'environnement déclaré par le banc, une
      autre exécution peut reconstruire le même profil d'expérience sans état local caché. »
    Ce n'est PAS : même score garanti · déterminisme absolu · absence de cache.
    Une dépendance locale non versionnée qui influence le verdict → false.
    Instrumentation incapable de conclure → "unknown". JAMAIS true par défaut.

BORNE, VISIBLE ET NON MASQUÉE
    `sys.addaudithook` ne voit que le processus courant. Un banc qui délègue à un
    sous-processus ne trace pas les accès de son enfant : le profil le dit alors, et son
    `repo_reproducible` passe à "unknown".
"""
import atexit, json, os, sys

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME")
                         or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

BRUIT = ("/lib/python", "site-packages", "/usr/", "encodings", "__pycache__", ".pyc",
         "Library/Caches/com.apple.python", "/dev/")

# Dépendances dont l'effet causal sur un verdict a été MESURÉ (matrice R0-R3 du
# 2026-08-21 : sans le fichier P@1 0,73 et q13 1er ; avec, 0,60 et q13 hors top-3).
CAUSALES_PROUVEES = {"state/recall-utilite.json"}

_etat = {"lus": set(), "ecrits": set(), "nom": None, "notes": [], "sous_processus": False}


def _hook(evenement, args):
    if evenement == "subprocess.Popen" or evenement == "os.exec":
        _etat["sous_processus"] = True
        return
    if evenement != "open":
        return
    c, mode = args[0], args[1]
    if not isinstance(c, str) or not c.startswith("/") or any(x in c for x in BRUIT):
        return
    (_etat["ecrits"] if mode and any(x in str(mode) for x in "wax+") else _etat["lus"]).add(c)


def _externe(chemin):
    """Hors du dépôt suivi, ou dans state/ : ce que HEAD ne contient pas."""
    if not chemin.startswith(BRAIN + "/"):
        return chemin.startswith(os.path.expanduser("~"))
    return os.path.relpath(chemin, BRAIN).startswith("state/")


def _rel(c):
    return os.path.relpath(c, BRAIN) if c.startswith(BRAIN + "/") else c


def demarrer(nom, ordre=(), mutations=(), notes=()):
    """À appeler en tête d'un banc normatif. `ordre` et `mutations` sont des faiblesses
    CONNUES et mesurées, que le lot 1 rend visibles sans les corriger."""
    _etat.update(nom=nom, ordre=list(ordre), mutations=list(mutations), notes=list(notes))
    sys.addaudithook(_hook)
    atexit.register(emettre)


def emettre():
    if not _etat.get("nom") or _etat.get("emis"):
        return
    _etat["emis"] = True
    # `open()` est audité à la TENTATIVE, pas au succès : un fichier absent apparaissait
    # dans la trace. Le sabotage S1 l'a montré — sans `recall-utilite.json`, le profil le
    # déclarait quand même lu, ce qui est exactement le mensonge que ce lot doit empêcher.
    # On ne retient donc que ce qui existe encore à l'émission.
    lus = sorted(_rel(c) for c in _etat["lus"] if _externe(c) and os.path.exists(c))
    # Les fichiers temporaires d'une écriture atomique (`.tmp`, `.NNN.tmp`) ne sont pas un
    # état local : ils sont le mécanisme d'écriture, et ils ont déjà disparu.
    ecrits = sorted(_rel(c) for c in _etat["ecrits"]
                    if _externe(c) and not c.endswith(".tmp") and os.path.exists(c))
    prouvees = [c for c in lus if c in CAUSALES_PROUVEES]
    state_root = os.path.join(BRAIN, "state")

    if _etat["sous_processus"]:
        repro = "unknown"
    elif lus or ecrits or _etat.get("ordre"):
        repro = False
    else:
        repro = True

    statut = ("I2-E" if _etat.get("ordre") else
              "I2-C" if lus or ecrits else "I2-A")

    profil = {"instrument": _etat["nom"], "brain_root": BRAIN,
              "state_root": state_root if os.path.isdir(state_root) else None,
              "external_reads_observed": lus, "verdict_dependency_proven": prouvees,
              "external_writes": ecrits, "order_dependencies": _etat.get("ordre", []),
              "mutations": _etat.get("mutations", []),
              "repo_reproducible": repro, "status": statut,
              "trace_limite_sous_processus": _etat["sous_processus"]}

    # Sortie COMPACTE, et sur STDERR — pas stdout.
    # POURQUOI stderr : `tests/racine_canonique.py` sonde des modules en LISANT leur
    # sortie standard. La première version imprimait le profil sur stdout et a fait
    # rougir ce banc, qui n'y comprenait plus rien. Un diagnostic ne doit jamais
    # contaminer le canal de données d'un autre instrument.
    def print(*a, **k):
        __builtins__["print"](*a, file=sys.stderr, **k) if isinstance(__builtins__, dict) \
            else __import__("builtins").print(*a, file=sys.stderr, **k)
    print("")
    if statut == "I2-A" and repro is True:
        print("  profil d'état : reproductible depuis le dépôt seul")
    else:
        print(f"  ⓘ profil d'état [{statut}] — reproductible depuis le dépôt seul : "
              f"{'oui' if repro is True else ('inconnu' if repro == 'unknown' else 'NON')}")
        for c in prouvees:
            print(f"     · verdict dépend d'un état local (causalité MESURÉE) : {c}")
        for c in lus:
            if c not in prouvees:
                print(f"     · état local lu : {c}")
        for c in ecrits:
            print(f"     · état local ÉCRIT par la mesure : {c}")
        for o in _etat.get("ordre", []):
            print(f"     · dépendance d'ordre : {o}")
        for m in _etat.get("mutations", []):
            print(f"     · mutation connue : {m}")
        if _etat["sous_processus"]:
            print("     · ⚠️ ce banc délègue à un sous-processus : la trace ne couvre PAS "
                  "ses accès")
    d = os.path.join(BRAIN, "state")
    if os.path.isdir(d):
        try:
            with open(os.path.join(d, "i2-profils.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(profil, ensure_ascii=False) + "\n")
        except OSError:
            pass
