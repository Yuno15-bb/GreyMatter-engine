#!/usr/bin/env python3
"""
regle_entree_carte.py — sabotages de la RÈGLE D'ENTRÉE de la carte (D5.2c).

Règle gravée par l'auteur le 2026-08-20 : un wikilink est une entrée seulement s'il occupe la
position structurante ; inséré dans une phrase, c'est une mention.

Une règle qui ne peut pas se tromper ne prouve rien : chaque cas ci-dessous est construit
pour que la règle DOIVE répondre, et la réponse attendue est écrite d'avance.

  python3 tests/regle_entree_carte.py
"""
import json, os, sys
ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "tools", "cartes"))
from regle_entree import lire

CAS = [
    ("puce simple",                 "- [[fiche-a]]",                              "entree"),
    ("puce étoilée",                "- ⭐⭐ [[fiche-a]] (annotation)",             "entree"),
    ("élément de liste en ligne",   "⭐ [[fiche-a]] (x) · ⭐ [[fiche-b]] (y)",      "entree"),
    ("annotation au tiret",         "**Skills** : ⭐⭐ [[fiche-a]] — du texte",     "entree"),
    ("titre portant un wikilink",   "## 🤖 Agents — Équipe de 8 [[readme]]",       "entree"),
    ("lien en milieu de phrase",    "- ⭐⭐ `x.md` — texte. Porte d'entrée : [[fiche-a]]. *fin*", "mention"),
    ("lien en fin de phrase",       "*Créé en juin. Voir [[fiche-a]].*",           "mention"),
    ("annotations empilées",        "⭐⭐ [[fiche-a]] (**D4** — a) (**D3** — b)",   "entree"),
]

print(f"{'cas':34}{'attendu':>10}{'obtenu':>10}")
print("-" * 56)
echecs = 0
for nom, ligne, attendu in CAS:
    lus = lire(ligne)
    # on juge le DERNIER lien de la ligne pour les cas de phrase, le premier sinon
    x = lus[-1] if attendu == "mention" else lus[0]
    ok = x["classe"] == attendu
    echecs += not ok
    print(f"{nom:34}{attendu:>10}{x['classe']:>10}   {'✅' if ok else '⛔'}")

# ── contre-épreuve sur la carte réelle : la règle reproduit-elle le manifeste ? ──
mem = open(os.path.join(BRAIN, "MEMORY.md"), encoding="utf-8").read()
lus = lire(mem)
entrees = {x["fiche"] for x in lus if x["classe"] == "entree"}
man = {e["fiche"] for e in json.load(open(os.path.join(BRAIN, "tools", "cartes",
        "manifeste-carte.json"), encoding="utf-8"))["entrees"]}
mentions = [x["fiche"] for x in lus if x["classe"] == "mention"]
print(f"\n── contre-épreuve sur MEMORY.md ──")
print(f"   {len(lus)} liens · {len(entrees)} entrées · {len(mentions)} mentions : {mentions}")
print(f"   entrées du manifeste que la règle refuse : {sorted(man - entrees)}")
print(f"   → attendu : 1 seul refus, `claude-brain` (« Voir [[…]]. » dans la phrase de pied de page)")

print(f"\n{'✅ règle conforme' if not echecs else f'⛔ {echecs} cas en échec'}")
sys.exit(1 if echecs else 0)
