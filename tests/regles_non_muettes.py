#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""Le contrôleur d'anonymisation ne doit pas pouvoir se désarmer lui-même.

CE QU'IL PROUVE. `generalize.py` remplace des motifs dans les fichiers du
paquet, et la liste de ces motifs vit dans `rules.json`, au même endroit. Le
20/09/2026, trois règles ont été élargies aux fichiers `.json` pour couvrir une
fuite dans un banc. Au premier passage, elles ont réécrit `rules.json` — leur
propre définition. Chaque `pattern` est devenu son `replace` : la règle existe
toujours, son compteur la déclare vivante, et elle ne remplace plus rien. Les
trois règles qui effacent le dossier personnel de l'auteur sont restées muettes
jusqu'à ce qu'un compteur tombe sous son seuil, par accident.

LES DEUX GARDES. Une règle dont le motif cherché est exactement le texte de
remplacement est un no-op : elle ne peut plus rien anonymiser. Et aucun glob,
si large soit-il, ne doit désigner les trois outils qui PORTENT les marqueurs
— c'est le métier de `leakcheck.py` de les lister, et celui de `rules.json` de
les décrire. `leakcheck.py` portait déjà cette exclusion ; l'outil jumeau ne
l'avait pas.

SABOTAGE. Retirer `SKIP_NAMES` de `generalize.py:targets` fait rougir le second
test ; remettre un `pattern` égal à son `replace` fait rougir le premier.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class ReglesNonMuettes(unittest.TestCase):

    def setUp(self):
        with open(os.path.join(ROOT, "rules.json"), encoding="utf-8") as f:
            self.rules = json.load(f)

    def test_aucune_regle_ne_cherche_ce_qu_elle_ecrit(self):
        muettes = [r.get("id", "?") for r in self.rules.get("replacements", [])
                   if "replace" in r and r.get("pattern") == r["replace"]]
        self.assertEqual(
            muettes, [],
            "règle(s) devenue(s) no-op — le motif cherché est déjà le texte de "
            f"remplacement, donc plus rien n'est anonymisé : {muettes}")

    def test_les_outils_qui_portent_les_marqueurs_ne_sont_jamais_reecrits(self):
        import generalize
        vises = {p.name for p in generalize.targets(["**/*.json", "**/*.py"])}
        for interdit in ("rules.json", "generalize.py", "leakcheck.py"):
            # assertNotIn recracherait les 140 noms de la cible dans le
            # message d'échec : un rouge illisible est un rouge qu'on survole.
            self.assertTrue(
                interdit not in vises,
                f"{interdit} est dans la cible d'une règle : il CONTIENT les "
                "marqueurs par métier, donc il se réécrirait lui-même et la "
                "règle se désarmerait en silence")


if __name__ == "__main__":
    unittest.main(verbosity=2)
