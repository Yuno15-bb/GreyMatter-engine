#!/usr/bin/env python3
"""Banc de sabotage du capteur de dépense — il doit ROUGIR, et pas n'importe où.

POURQUOI CE BANC EXISTE. Le chantier sobriété (14/09) pose que « chaque levier installé a un
sabotage qui fait rougir son contrôle ». Un capteur de dépense est particulièrement exposé à
l'illusion : il lit des journaux qui existent toujours, il produit toujours un tableau, et un
tableau qui s'affiche ressemble à un contrôle qui marche. Trois fois dans ce dépôt un contrôle
vert n'atteignait pas son mécanisme (`brain status`, le sabotage qui passait au vert, le banc
d'équivalence vert sur du code inerte). On construit donc les journaux à la main.

CE QUI EST VÉRIFIÉ — cinq cas, chacun sur un jeu de journaux jetable :
  • un journal sobre laisse le capteur MUET (sortie 0) ;
  • chacune des trois mesures, poussée seule au-delà de son seuil, le fait ROUGIR ;
  • un rouge doit NOMMER sa mesure (M1, M2 ou M3), sinon n'importe quelle panne de lecture
    passerait pour une détection ;
  • un journal trop maigre rougit aussi : un capteur qui n'a rien à lire ne doit jamais
    se taire comme s'il avait mesuré.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTEUR = os.path.join(RACINE, "tools", "conso-jetons", "capteur.py")
SEUILS = json.load(open(os.path.join(RACINE, "tools", "conso-jetons", "seuils.json")))
HIER = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def journal(dossier, appels, ctx, octets_outils):
    """Écrit un journal jetable : `appels` échanges, chacun relisant `ctx` jetons de contexte
    et renvoyant `octets_outils` octets de résultat d'outil."""
    os.makedirs(os.path.join(dossier, "projet"), exist_ok=True)
    chemin = os.path.join(dossier, "projet", "session.jsonl")
    with open(chemin, "w") as f:
        for i in range(appels):
            horo = f"{HIER}T{i % 24:02d}:00:00.000Z"
            f.write(json.dumps({
                "uuid": f"u{i}a", "type": "user", "timestamp": horo,
                "message": {"content": [{
                    "type": "tool_result", "tool_use_id": f"t{i}",
                    "content": [{"type": "text", "text": "x" * octets_outils}]}]},
            }) + "\n")
            f.write(json.dumps({
                "uuid": f"u{i}b", "type": "assistant", "timestamp": horo,
                "requestId": f"r{i}",
                "message": {"id": f"m{i}", "model": "claude-opus-5",
                            "content": [{"type": "tool_use", "id": f"t{i}",
                                         "name": "Bash", "input": {}}],
                            "usage": {"input_tokens": 10,
                                      "cache_read_input_tokens": ctx(i),
                                      "cache_creation_input_tokens": 0,
                                      "output_tokens": 100}},
            }) + "\n")
    return chemin


def joue(appels, ctx, octets):
    dossier = tempfile.mkdtemp(prefix="capteur-conso-")
    try:
        journal(dossier, appels, ctx, octets)
        r = subprocess.run([sys.executable, CAPTEUR, "--check", "--jours", "3",
                            "--journaux", dossier],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


SOUS_SEUIL = SEUILS["M2_octets_outils_max"] - 1500  # marge : le capteur compte aussi l'appel

CAS = [
    ("journal sobre — le capteur doit se taire", False, None,
     dict(appels=60, ctx=lambda i: 120000, octets=SOUS_SEUIL)),
    ("contexte médian au-dessus du plafond", True, "M1",
     dict(appels=60, ctx=lambda i: 260000, octets=SOUS_SEUIL)),
    ("sorties d'outils trop bavardes", True, "M2",
     dict(appels=60, ctx=lambda i: 120000, octets=20000)),
    # M3 se teste avec une médiane BASSE et un pic HAUT : c'est la seule forme qui l'isole
    # de M1. Cinq appels sur soixante montent à 300k, aucune coupure n'est écrite.
    ("une session qui monte à 300k sans jamais se couper", True, "M3",
     dict(appels=60, ctx=lambda i: 300000 if i < 5 else 100000, octets=SOUS_SEUIL)),
    ("journal trop maigre — un capteur muet n'est pas un capteur vert", True, "conclure",
     dict(appels=5, ctx=lambda i: 120000, octets=SOUS_SEUIL)),
]


def main():
    conformes = 0
    for nom, doit_rougir, motif, kw in CAS:
        code, sortie = joue(**kw)
        rouge = code != 0
        ok = rouge == doit_rougir and (not motif or motif in sortie)
        conformes += ok
        etat = "ROUGE" if rouge else "vert "
        print(f"  {'✅' if ok else '❌'} {etat} {nom}")
        if not ok:
            print("     attendu :", "rouge" if doit_rougir else "vert",
                  f"portant « {motif} »" if motif else "")
            print("     obtenu  :", sortie.strip().splitlines()[-1:] or "(rien)")
    print(f"\n{conformes}/{len(CAS)} cas conformes")
    return 0 if conformes == len(CAS) else 1


if __name__ == "__main__":
    sys.exit(main())
