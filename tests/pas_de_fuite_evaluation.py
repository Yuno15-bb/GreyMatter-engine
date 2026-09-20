#!/usr/bin/env python3
"""
pas_de_fuite_evaluation.py — les données d'évaluation ne doivent pas entrer dans le corpus.

L'INVARIANT :

    Les données synthétiques utilisées pour évaluer C-Brain ne doivent jamais entrer
    dans le corpus récupérable par le système qu'elles évaluent.

L'INCIDENT QUI L'A PRODUIT (2026-08-12) :

    312 documents attendus  →  1 573 indexés
    cause       : les copies du banc, sous tools/, étaient vues par le rappel du vrai tronc
    conséquence : chaque fiche en 5 exemplaires, IDF faussé, TOUS les scores faux

Le banc mesurait un corpus qu'il avait lui-même gonflé. Rien ne rougissait : le rappel
répondait normalement, simplement sur un index contaminé.

POURQUOI CE FICHIER PLUTÔT QU'UNE CONVENTION. On s'est protégé en écrivant les fixtures
en JSON — le rappel n'indexe que les `.md`. Mais une convention n'est pas un garde-fou :
elle tient tant que tout le monde s'en souvient. Dans six mois, quelqu'un déposera un
`.md` dans `tests/` pour documenter un banc, et l'incident reviendra à l'identique, en
silence. `tests/` N'EST PAS dans SKIP_DIRS — c'est vérifié plus bas, et c'est précisément
ce qui rend ce contrôle nécessaire plutôt que théorique.

Lancer :
  python3 tests/pas_de_fuite_evaluation.py
  python3 tests/pas_de_fuite_evaluation.py --check    # barrière : sort 1 en cas de fuite
"""
import argparse
import os
import sys


ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)

# ── I-2 · PROFIL D'ÉTAT (lot 1, 2026-08-21) ──────────────────────────────────
# Ce banc ANNONCE désormais sous quel état il a rendu son verdict. Rien d'autre ne
# change : ni score, ni ordre, ni état. Un verdict rouge reste rouge ; un verdict
# vert avec dépendance déclarée ne devient pas meilleur. La déclaration fait passer
# une dépendance de SILENCIEUSE (I2-D) à ANNONCÉE (I2-C) — elle ne la rend pas saine.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
    import i2_profil
    i2_profil.demarrer("pas_de_fuite_evaluation")
except Exception:
    pass            # un banc ne doit jamais échouer à cause de son propre diagnostic

sys.path.insert(0, os.path.join(BRAIN, "hooks"))

import brain_recall as br  # noqa: E402

# Les zones qui contiennent des données d'ÉVALUATION. Ancrées par premier segment de
# chemin, pas par sous-chaîne : une exclusion écrite par nom frappe tous les dossiers qui
# portent ce nom, où qu'ils soient. cf. [[exclusion-par-nom-frappe-tous-les-dossiers]]
ZONES_EVAL = ("tests", "tools")


def fuites():
    docs = br.load_corpus()
    dedans = []
    for d in docs:
        premier = d["path"].split(os.sep)[0]
        if premier in ZONES_EVAL:
            dedans.append(d["path"])
    return dedans, len(docs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    dedans, total = fuites()
    print(f"Fuite d'évaluation — {total} documents dans le corpus du rappel\n")
    for z in ZONES_EVAL:
        etat = "exclue par SKIP_DIRS" if z in br.SKIP_DIRS else "⚠️ NON exclue par SKIP_DIRS"
        print(f"  {z + '/':10} {etat}")
    print()

    if dedans:
        print(f"❌ {len(dedans)} document(s) d'évaluation sont indexés par le rappel :")
        for p in dedans[:12]:
            print(f"     {p}")
        print("\n   Le système mesure un corpus qu'il a lui-même gonflé.")
        print("   Écrire la donnée en .json, ou exclure la zone dans brain_recall.SKIP_DIRS.")
        return 1 if a.check else 0

    print("✅ aucune donnée d'évaluation dans le corpus récupérable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
