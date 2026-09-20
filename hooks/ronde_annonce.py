#!/usr/bin/env python3
"""Affiche au démarrage d'une session la ronde matin/soir qui n'a pas été vue.

POURQUOI CE HOOK EXISTE. La ronde de `etat_projets.py` s'annonçait par une bannière macOS
(`osascript display notification`). Le 2026-08-14, l'auteur constate qu'il n'a rien reçu le matin.
Enquête : le service AVAIT tourné (`runs = 4`, `last exit code = 0`, ligne « matin » dans
`sessions/etat.log`) et `osascript` avait rendu 0 — mais Script Editor, l'app au nom de laquelle
un agent launchd poste ses notifications, n'apparaît nulle part dans `com.apple.ncprefs`, même
après une tentative forcée. Le canal échouait donc en silence tout en rendant un code vert.

C'est la règle « un code de sortie n'est jamais l'observable », appliquée cette fois au canal
d'annonce : la ronde était bonne, sa mesure était bonne, et personne ne l'a jamais lue.

Le remède n'est pas de réparer la bannière — on ne peut pas prouver sa livraison depuis un
script. C'est d'annoncer **là où l'auteur est certainement en train de regarder** : sa session de
travail. Le marqueur reste en attente jusqu'à ce qu'il soit affiché une fois, puis il se tait.

Usage : appelé sans argument par le hook SessionStart. N'écrit jamais sur stderr, ne bloque
jamais le démarrage : une panne ici ne doit pas coûter une session.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # CODE_ROOT, légitime
from brain_racine import brain_root

# I-1 (2026-08-21). Avant : `os.path.expanduser("~/.c-brain/trunk")` — un littéral qu'AUCUNE
# variable ne détournait. Ce module était le dernier I1-FAIL à maintenir un orchestrateur
# DÉJÀ conforme en E0* : son hook SessionStart porte BRAIN_HOME depuis L1.0, et l'enfant
# l'ignorait. Un parent qui transmet correctement une identité que l'enfant jette produit
# une conformité nominale — plus trompeuse que l'absence d'ancrage.
BRAIN = brain_root(__file__)
ANNONCE = os.path.join(BRAIN, "state", "ronde-a-annoncer.json")

# Au-delà, la ronde ne vaut plus la peine d'être annoncée : elle décrit un état dépassé, et
# l'annoncer ferait passer une vieille mesure pour la nouvelle.
PEREMPTION_H = 18


def main() -> int:
    try:
        with open(ANNONCE, encoding="utf-8") as f:
            marque = json.load(f)
    except FileNotFoundError:
        return 0
    except Exception:
        return 0

    if marque.get("annonce_le"):
        return 0                                    # déjà vue : on ne la répète pas

    texte = (marque.get("texte") or "").strip()
    if not texte:
        return 0

    try:
        ecrit = dt.datetime.fromisoformat(marque["ecrit_le"])
        heures = (dt.datetime.now() - ecrit).total_seconds() / 3600
    except Exception:
        heures = 0.0

    if heures > PEREMPTION_H:
        _marquer_vue(marque, "périmée")
        return 0

    quand = "à l'instant" if heures < 1 else f"il y a {int(heures)} h"
    print(f"<ronde-etat-projets>\nRonde des projets non lue, écrite {quand} "
          f"(la bannière macOS ne s'affiche pas : voir hooks/ronde_annonce.py).\n\n"
          f"{texte}\n</ronde-etat-projets>")
    _marquer_vue(marque, "affichée")
    return 0


def _marquer_vue(marque: dict, raison: str) -> None:
    marque["annonce_le"] = dt.datetime.now().isoformat()
    marque["raison"] = raison
    try:
        with open(ANNONCE, "w", encoding="utf-8") as f:
            json.dump(marque, f, ensure_ascii=False, indent=2)
    except Exception:
        pass                                        # au pire, elle se réaffichera une fois


if __name__ == "__main__":
    sys.exit(main())
