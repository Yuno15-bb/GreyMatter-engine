#!/usr/bin/env python3
"""
provenance_fiches.py — la provenance appliquée aux VRAIES fiches (ADR-0009).

CE QU'IL FAIT, ET SURTOUT CE QU'IL NE FAIT PAS. Il applique le protocole au flux vivant,
et **uniquement aux fiches nouvelles**. Les 472 fiches historiques restent intactes :

  • une fiche qui NE DÉCLARE PAS de provenance est laissée en paix. Elle est `unknown` de
    fait — pas d'autorité, pertinence intacte. C'est le comportement voulu.
  • une fiche qui DÉCLARE une provenance doit la déclarer correctement, où qu'elle soit.
  • une fiche AJOUTÉE dans le commit courant doit en déclarer une.
  • une fiche AJOUTÉE qui PRÉTEND connaître son origine (kind ≠ unknown) doit porter
    l'extrait exact qui la fonde — c'est E1, « pas d'extrait, pas de fait », posé dans
    agents/distillateur.md le 2026-09-18.

E1, ET POURQUOI IL S'ARRÊTE À `unknown`. Une fiche qui déclare `kind: unknown` dit qu'elle
ne sait pas d'où elle vient : elle n'a rien à citer, et lui réclamer un extrait la
pousserait à en inventer un. L'exigence ne tombe donc que sur les fiches qui REVENDIQUENT
une source. Appui mesuré : le memory tool d'Anthropic refuse un `str_replace` dont la
chaîne ne correspond pas au caractère près — une reformulation ne se vérifie pas, un
extrait si. Et l'audit Mem0 (issue 4573, 10 134 entrées) montre qu'un fait halluciné une
fois se ré-extrait ensuite indéfiniment : l'extrait est ce qui casse cette boucle.

Pourquoi pas de rattrapage sur l'existant : il n'existe aucune correspondance mécanique
fiable pour reconstruire l'origine d'une fiche de juin. `metadata.type` dit le GENRE
(136 feedback, 107 project, 74 reference…), `born_from` dit le PROJET. Ni l'un ni l'autre
ne dit la SOURCE. Une provenance fausse est pire qu'une provenance absente : on lui ferait
confiance. Même raison que fraicheur_fiches.py, qui a refusé d'inscrire le mtime dans
312 fiches pour zéro information nouvelle.

I7 SUR DISQUE. `derived_from` est résolu contre les vraies fiches du tronc : le kind du
parent est lu sur le parent, pas déclaré par l'enfant. C'est ce qui rend le blanchiment
détectable ailleurs que dans une fixture.

Lancer :
  python3 tests/provenance_fiches.py              # état du tronc, informatif
  python3 tests/provenance_fiches.py --check      # barrière : les déclarations doivent être valides
  python3 tests/provenance_fiches.py --nouvelles  # + provenance ET extrait sur les fiches AJOUTÉES
"""
import argparse
import glob
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
# BRAIN_HOME comme partout ailleurs dans le dépôt (brain_recall, brain_utility, le banc de
# valeur) : c'est ce qui permet d'éprouver ce contrôle sur un tronc JOUET, hors du vrai,
# plutôt que de créer de fausses fiches dans le tronc vivant pour le tester.
BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.dirname(ICI))
sys.path.insert(0, ICI)
from provenance_invariants import controler, kind_effectif, _lire_bloc  # noqa: E402

ZONES = ("projects", "lessons", "meta", "life")


def frontmatter(chemin):
    try:
        raw = open(chemin, encoding="utf-8").read()
    except OSError:
        return ""
    m = re.match(r"^---\n(.*?)\n---", raw, re.S)
    return m.group(1) if m else ""


def fiches():
    out = {}
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if rel.split(os.sep)[0] in ZONES:
            out[os.path.basename(rel)[:-3]] = (rel, frontmatter(p))
    return out


def ajoutees():
    """Fiches AJOUTÉES dans le commit courant — la frontière du flux vivant."""
    try:
        s = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
                           cwd=BRAIN, capture_output=True, text=True).stdout
    except Exception:
        return set()
    return {l for l in s.split("\n")
            if l.endswith(".md") and l.split("/")[0] in ZONES}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--nouvelles", action="store_true",
                    help="exige aussi une provenance sur les fiches ajoutées au commit")
    a = ap.parse_args()

    toutes = fiches()
    neuves = ajoutees()
    kinds = {n: kind_effectif(_lire_bloc(fm, "provenance") or {})
             for n, (_, fm) in toutes.items()}

    declarent, fautives, manquantes, sans_extrait = [], [], [], []
    for nom, (rel, fm) in sorted(toutes.items()):
        prov = _lire_bloc(fm, "provenance")
        if not prov:
            if a.nouvelles and rel in neuves:
                manquantes.append(rel)
            continue
        declarent.append(rel)
        # I7 : le kind du parent se lit SUR LE PARENT. Une fiche ne décide pas de
        # l'origine dont elle descend.
        parent = None
        dfrom = prov.get("derived_from")
        if dfrom:
            cible = dfrom[0] if isinstance(dfrom, list) else dfrom
            parent = kinds.get(cible)
        fautes = controler(fm, parent)
        if fautes:
            fautives.append((rel, fautes))
        # E1 — l'extrait n'est exigé que des fiches NEUVES qui revendiquent une origine.
        # `unknown` en est dispensé : il n'a rien à citer (voir l'en-tête).
        if (a.nouvelles and rel in neuves and prov.get("kind") != "unknown"
                and not str(prov.get("extrait") or "").strip()):
            sans_extrait.append(rel)

    print(f"Provenance sur le tronc — {len(toutes)} fiches\n")
    print(f"  déclarent une provenance : {len(declarent)}")
    print(f"  sans provenance (unknown de fait, intactes) : {len(toutes) - len(declarent)}")
    if neuves:
        print(f"  ajoutées dans ce commit : {len(neuves)}")

    if fautives:
        print(f"\n❌ {len(fautives)} fiche(s) déclarent une provenance invalide :")
        for rel, f in fautives[:10]:
            print(f"     {rel}\n        ↳ {f[0]}")
    if manquantes:
        print(f"\n❌ {len(manquantes)} fiche(s) ajoutée(s) sans provenance :")
        for rel in manquantes[:10]:
            print(f"     {rel}")
        print("\n   Une fiche nouvelle déclare son origine. Si elle est inconnue,")
        print("   écris-la : `provenance:\\n  kind: unknown`. Ne suppose jamais.")

    if sans_extrait:
        print(f"\n❌ {len(sans_extrait)} fiche(s) ajoutée(s) sans extrait (E1) :")
        for rel in sans_extrait[:10]:
            print(f"     {rel}")
        print("\n   Une fiche qui nomme sa source en recopie la phrase, mot pour mot :")
        print("   `provenance:\\n  extrait: \"la phrase exacte\"`. Si tu ne peux pas la")
        print("   coller, tu n'écris pas le fait — ou tu déclares `kind: unknown`.")

    if a.check and (fautives or manquantes or sans_extrait):
        return 1
    if a.check:
        print("\n✅ aucune provenance déclarée n'est invalide")
    return 0


if __name__ == "__main__":
    sys.exit(main())
