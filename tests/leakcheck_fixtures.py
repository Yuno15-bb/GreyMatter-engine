#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""Prouve que l'exception « leurres de test » n'a pas ouvert une porte.

POURQUOI CE FICHIER EXISTE. Le contrôle de fuite bloquait les tests écrits POUR
LUI : `fiche_write_contract.py` doit contenir une fausse clé pour prouver qu'une
clé est refusée. On a donc ajouté une exception (`FIXTURES` dans leakcheck.py).
Une exception non testée est un trou qui s'ignore : ce fichier est la
contre-épreuve.

CE QU'IL VÉRIFIE. Les trois verrous, un par un, en essayant de les forcer :
  1. le leurre déclaré passe — sinon l'exception ne sert à rien ;
  2. le MÊME leurre hors de `tests/` reste ROUGE — l'exception ne fuit pas ;
  3. une valeur VOISINE mais non déclarée reste ROUGE — la liste est fermée ;
  4. une vraie clé et un vrai chemin, DANS `tests/`, restent ROUGES ;
  5. le nombre de marqueurs n'a pas bougé — personne n'en a désarmé un.

⚠ Les valeurs interdites de ce fichier sont ASSEMBLÉES À L'EXÉCUTION, jamais
écrites en clair : un littéral déclencherait le contrôle sur ce fichier même,
et il faudrait alors l'exempter — ce qui reviendrait à se mordre la queue.

Lancer : python3 tests/leakcheck_fixtures.py
"""

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("leakcheck", ROOT / "leakcheck.py")
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)

COMPILED = [(label, re.compile(motif)) for label, motif in lc.MARKERS]


def fuites(source: str, texte: str):
    """Rejoue le vrai `scan` du contrôleur, sans réimplémenter sa logique."""
    trouve = []
    lc.scan(source, texte, COMPILED, trouve)
    return [(label, extrait) for _, label, extrait in trouve]


# Valeurs assemblées — voir l'avertissement du docstring.
LEURRE_CLE = "sk-" + "ant-" + "AAAABBBBCCCCDDDDEEEE"
LEURRE_CHEMIN = "/Users/" + "x/"
VRAIE_CLE = "sk-" + "ant-" + "api03" + "-9f2Kd7Qm4Xr8Tz1Lb6Vn0Yc3Hs5Wj"
VRAI_CHEMIN = "/Users/" + "dylanp/"
VOISIN = "sk-" + "ant-" + "AAAABBBBCCCCDDDDEEEF"   # une lettre de plus, non déclaré

# ⚠ L'AFFECTATION AUSSI est assemblée, pas seulement la valeur. Un f-string qui
# écrirait le mot-clé, l'égal, le guillemet et un champ nommé sur une même ligne
# correspondrait LUI-MÊME au marqueur « secret assigné en clair » : le motif ne
# regarde pas la valeur, il regarde la FORME de la ligne. Constaté deux fois le
# 2026-08-26 — d'abord dans les cas de test, puis dans le commentaire qui
# l'expliquait en le citant. Ne rien écrire ici qui ait cette forme.
def _affectation(valeur: str) -> str:
    return "SECRET" + ' = "' + valeur + '"'


# ⚠ DURCI le 2026-08-26. Chaque cas nomme le marqueur qui DOIT se déclencher,
# au lieu de se contenter d'un « quelque chose a été signalé ». Un sabotage l'a
# prouvé nécessaire : en autorisant une vraie clé comme leurre, le cas « une
# VRAIE clé reste rouge » continuait de passer — parce qu'un AUTRE marqueur
# (« secret assigné en clair ») prenait le relais. Le contrôle semblait tenir
# alors que le marqueur visé avait été désarmé.
CAS = [
    # (intitulé, chemin, texte, marqueur attendu — None = doit rester vert)
    ("le leurre déclaré passe sous tests/",
     "tests/fiche_write_contract.py", _affectation(LEURRE_CLE), None),
    ("le chemin leurre passe sous tests/",
     "tests/a1_pixel_lib.py", f'p = "{LEURRE_CHEMIN}.c-brain"', None),

    ("le MÊME leurre hors de tests/ reste rouge",
     "cbrain/engine-lib.sh", _affectation(LEURRE_CLE), "clé Anthropic"),
    ("le MÊME chemin leurre hors de tests/ reste rouge",
     "install.sh", f'p = "{LEURRE_CHEMIN}.c-brain"', "chemin personnel"),

    ("une valeur VOISINE non déclarée reste rouge",
     "tests/fiche_write_contract.py", _affectation(VOISIN), "clé Anthropic"),

    ("une VRAIE clé dans tests/ reste rouge",
     "tests/fiche_write_contract.py", _affectation(VRAIE_CLE), "clé Anthropic"),
    ("un VRAI chemin personnel dans tests/ reste rouge",
     "tests/a1_pixel_lib.py", f'p = "{VRAI_CHEMIN}.c-brain"', "chemin personnel"),

    ("l'historique d'un test est traité comme le test",
     "historique:tests/fiche_write_contract.py", _affectation(LEURRE_CLE), None),
    ("l'historique d'un fichier moteur reste rouge",
     "historique:install.sh", _affectation(LEURRE_CLE), "clé Anthropic"),
]


def main() -> int:
    echecs = []

    for intitule, source, texte, marqueur_attendu in CAS:
        trouve = fuites(source, texte)
        labels = [l for l, _ in trouve]
        if marqueur_attendu is None:
            ok = not trouve
            attendu = "vert"
        else:
            # Il ne suffit PAS qu'un marqueur ait parlé : c'est CELUI-LÀ qui doit
            # parler. Sinon un marqueur désarmé passe inaperçu derrière un voisin.
            ok = marqueur_attendu in labels
            attendu = f"ROUGE sur « {marqueur_attendu} »"
        obtenu = f"ROUGE sur {labels}" if trouve else "vert"
        marque = "✅" if ok else "❌"
        print(f"  {marque} {intitule}\n       attendu {attendu}, obtenu {obtenu}")
        if not ok:
            echecs.append(intitule)

    # Personne n'a désarmé un marqueur en passant.
    attendus = 21
    if len(lc.MARKERS) != attendus:
        print(f"  ❌ le nombre de marqueurs a changé : {len(lc.MARKERS)} au lieu de {attendus}")
        echecs.append("nombre de marqueurs")
    else:
        print(f"  ✅ les {attendus} marqueurs sont toujours armés")

    # L'exception reste étroite : uniquement sous tests/.
    if lc.FIXTURES_DIRS != ("tests/",):
        print(f"  ❌ la portée des leurres s'est élargie : {lc.FIXTURES_DIRS}")
        echecs.append("portée des leurres")
    else:
        print("  ✅ les leurres restent confinés à tests/")

    print()
    if echecs:
        print(f"⛔ {len(echecs)} contre-épreuve(s) en échec — l'exception a ouvert un trou.")
        for e in echecs:
            print(f"   · {e}")
        return 1
    print("✅ L'exception tient : les leurres passent, tout le reste rougit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
