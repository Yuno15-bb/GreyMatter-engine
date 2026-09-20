#!/usr/bin/env python3
"""
en_clair_obligatoire.py — toute fiche servie au rappel porte son bloc « ## En clair ».

POURQUOI CE BANC EXISTE (constat de l'auteur, 2026-09-19)
  « chaque fiche créée après une session documente du flou, un externe ne peut rien
  comprendre sans contexte ; c'est plus du cache technique que la narration d'un problème
  abordé et résolu. » La convention qui répond à ce constat existe depuis le 2026-08-14
  (meta/fiche-format-en-clair.md) : un bloc en français courant, sans jargon, en tête de
  fiche. Rien ne l'imposait. Mesuré le 2026-09-20, AVANT réparation : 49 fiches du corpus
  de rappel sur 718 n'avaient pas de bloc, dont les 20 fiches de septembre — c'est-à-dire
  que la convention se dégradait exactement là où le travail était le plus récent.

  Une convention que rien ne mesure ne se perd pas d'un coup : elle s'effrite par la fiche
  neuve, celle qu'on écrit vite en fin de session. C'est le dernier fichier écrit qui la
  casse, jamais l'ancien.

CE QUE CE BANC VÉRIFIE
  1. Toute fiche du corpus de rappel (hooks/brain_corpus.indexable) portant un `name:`
     contient une ligne exactement `## En clair` — le motif que lit l'extracteur
     (hooks/graph_export.py). Un titre décoré, « ## En clair — à lire avant… », NE COMPTE
     PAS : mesuré le 2026-09-20 sur deux fiches, le bloc existait et l'afficheur ne le
     voyait pas. Le banc mesure ce que la machine lit, pas ce que l'humain reconnaît.
  2. La dette déclarée (tests/en_clair_dette.txt) ne peut que FONDRE : une fiche qui a
     reçu son bloc doit sortir de la liste, et une entrée qui ne désigne plus aucune fiche
     du corpus est une erreur. Sans ce second point, la liste d'exemptions deviendrait le
     dépotoir où l'on range ce qu'on ne veut pas écrire.

CE QU'IL NE VÉRIFIE PAS
  · La QUALITÉ du bloc. Un « ## En clair » suivi de trois mots passe au vert. Aucun
    instrument ici ne sait juger si un externe comprendrait — c'est un jugement humain.
  · Le reste du format (meta/format-fiche-v2.md, en attente de validation de l'auteur).
  · Les fichiers hors corpus de rappel : tools/, vision/, sessions/, MEMORY.md.

  python3 tests/en_clair_obligatoire.py            (récit)
  python3 tests/en_clair_obligatoire.py --check    (verdict seul, pour le commit)
"""
import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_corpus as bc  # noqa: E402

DETTE = os.path.join(ICI, "en_clair_dette.txt")

# Le motif de l'extracteur, à la lettre — cf. hooks/graph_export.py:EN_CLAIR
EN_CLAIR = re.compile(r"^##[ \t]+En clair[ \t]*$", re.M)
DECORE = re.compile(r"^##[ \t]+En clair[ \t]+\S", re.M)
NOM = re.compile(r"^name:", re.M)


def lire_dette():
    """Les chemins relatifs exemptés, commentaires et lignes vides ignorés."""
    if not os.path.exists(DETTE):
        return set()
    lignes = open(DETTE, encoding="utf-8").read().splitlines()
    return {l.strip() for l in lignes if l.strip() and not l.startswith("#")}


def mesurer():
    dette = lire_dette()
    sans, decores, sortis, fantomes = [], [], [], []
    vus = set()

    for rel, chemin in bc.indexable(BRAIN):
        try:
            texte = open(chemin, encoding="utf-8").read()
        except OSError:
            continue
        if not NOM.search(texte[:600]):
            continue  # pas une fiche : en_clair.py refuse déjà ces fichiers
        vus.add(rel)
        a_bloc = bool(EN_CLAIR.search(texte))
        if a_bloc and rel in dette:
            sortis.append(rel)
        elif not a_bloc and rel not in dette:
            (decores if DECORE.search(texte) else sans).append(rel)

    fantomes = sorted(dette - vus)
    return dette, sans, decores, sortis, fantomes, len(vus)


def main():
    check = "--check" in sys.argv
    dette, sans, decores, sortis, fantomes, total = mesurer()
    echec = sans or decores or sortis or fantomes

    if not check:
        faits = total - len(dette)
        print(f"Corpus de rappel : {total} fiches · {faits} portent « ## En clair » "
              f"({round(100 * faits / max(1, total))} %) · dette déclarée : {len(dette)}")

    if not echec:
        if not check:
            print("✅ toute fiche hors dette porte son bloc, et la dette est à jour.")
        return 0

    print("")
    print("❌ banc en échec : tests/en_clair_obligatoire.py")

    if sans:
        print(f"\n  {len(sans)} fiche(s) sans bloc « ## En clair » et hors dette :")
        for r in sorted(sans)[:12]:
            print(f"    · {r}")
        if len(sans) > 12:
            print(f"    … et {len(sans) - 12} autres")
        print("  Écrire le bloc (3 à 5 phrases, zéro jargon, ce qui s'est passé et pourquoi")
        print("  ça compte), puis : python3 tools/en_clair.py blocs.json")

    if decores:
        print(f"\n  {len(decores)} fiche(s) avec un titre DÉCORÉ, invisible pour l'afficheur :")
        for r in sorted(decores):
            print(f"    · {r}")
        print("  Le titre doit être exactement « ## En clair ». Le commentaire descend")
        print("  dans le texte du bloc.")

    if sortis:
        print(f"\n  {len(sortis)} fiche(s) ont reçu leur bloc mais restent dans la dette :")
        for r in sorted(sortis)[:12]:
            print(f"    · {r}")
        print(f"  Les retirer de tests/en_clair_dette.txt — la dette ne fait que fondre.")

    if fantomes:
        print(f"\n  {len(fantomes)} entrée(s) de la dette ne désignent plus aucune fiche "
              f"du corpus :")
        for r in fantomes:
            print(f"    · {r}")
        print("  Fiche renommée, déplacée ou supprimée : corriger tests/en_clair_dette.txt.")

    return 1


if __name__ == "__main__":
    sys.exit(main())
