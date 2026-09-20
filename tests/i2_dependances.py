#!/usr/bin/env python3
"""i2_dependances — ce dont un verdict DÉPEND réellement, observé, pas déclaré.

I-2 pose une question que ni I-1 ni I-3 ne posent :
    « un verdict normatif dépend-il d'un état externe, local ou d'un ordre d'exécution
      qui n'est pas déclaré dans l'identité de l'expérience ? »

MÉTHODE — on n'interroge pas le code, on regarde ce qu'il OUVRE.
`sys.addaudithook` capte chaque `open()` du processus : chemin et mode. On obtient donc
la liste réelle des fichiers lus et écrits, y compris ceux qu'aucune lecture de source
n'aurait révélés (imports, caches, fichiers construits par concaténation).

CLASSES
    I2-A  versionné / intrinsèque à l'expérience
    I2-B  externe mais explicitement injecté
    I2-C  externe, volontairement local, ANNONCÉ
    I2-D  externe et influençant SILENCIEUSEMENT le verdict     ← rouge
    I2-E  effet de bord d'un autre banc / dépendance d'ordre     ← rouge
    I2-F  inconnu

BORNE CONNUE : l'audit hook ne voit que le processus courant. Un banc qui lance un
sous-processus (verifier_temoins → golden_recall) masque les accès de son enfant. C'est
écrit ici plutôt que découvert plus tard.

Usage :  i2_dependances.py <script.py> [args…]     trace un instrument
"""
import json, os, sys

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME")
                         or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

TRACE = {"lus": set(), "ecrits": set()}


def _hook(evenement, args):
    if evenement != "open":
        return
    chemin, mode = args[0], args[1]
    if not isinstance(chemin, str) or not chemin.startswith("/"):
        return
    # Le cache de bytecode de l'interpréteur n'est pas une dépendance de VERDICT : il est
    # reconstructible, indifférent au contenu, et il polluait la classe I2-D de 4 à 19 entrées
    # par instrument à la première passe. Un instrument qui signale du bruit finit ignoré.
    BRUIT = ("/lib/python", "site-packages", "/usr/", "encodings",
             "Library/Caches/com.apple.python", "__pycache__", ".pyc")
    if any(x in chemin for x in BRUIT):
        return
    (TRACE["ecrits"] if mode and any(c in str(mode) for c in "wax+") else TRACE["lus"]).add(chemin)


def classe(chemin, versionnes):
    rel = os.path.relpath(chemin, BRAIN) if chemin.startswith(BRAIN + "/") else None
    if rel and rel in versionnes:
        return "I2-A"
    if rel and rel.startswith("state/"):
        return "I2-D"                      # externe au dépôt ET dans l'arbre mesuré
    if chemin.startswith(os.path.expanduser("~")) and not chemin.startswith(BRAIN):
        return "I2-D"
    if rel:
        return "I2-F"                      # dans le dépôt mais non suivi : généré ou oublié
    return "I2-C"                          # hors dépôt, hors foyer : temporaire, système


def main():
    cible = sys.argv[1]
    sys.argv = sys.argv[1:]
    import subprocess
    versionnes = set(subprocess.run(["git", "-C", BRAIN, "ls-files"],
                                    capture_output=True, text=True).stdout.split())
    avant_state = set(os.listdir(os.path.join(BRAIN, "state"))) if os.path.isdir(os.path.join(BRAIN, "state")) else set()
    sys.addaudithook(_hook)
    code = 0
    try:
        import runpy
        runpy.run_path(cible, run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 0
    except BaseException as e:
        code = f"{type(e).__name__}"
    apres_state = set(os.listdir(os.path.join(BRAIN, "state"))) if os.path.isdir(os.path.join(BRAIN, "state")) else set()

    res = {"instrument": os.path.relpath(cible, BRAIN), "code": code,
           "crees_dans_state": sorted(apres_state - avant_state), "lus": {}, "ecrits": {}}
    for k in ("lus", "ecrits"):
        for c in sorted(TRACE[k]):
            res[k].setdefault(classe(c, versionnes), []).append(
                os.path.relpath(c, BRAIN) if c.startswith(BRAIN + "/") else c)
    print("§§I2§§" + json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
