#!/usr/bin/env python3
"""corpus_partage.py — les deux moteurs de rappel voient-ils le MÊME corpus ?

L'INVARIANT :

    La définition du corpus indexable est écrite UNE fois (hooks/brain_corpus.py).
    Aucun moteur n'en garde de copie locale.

L'INCIDENT QUI L'A PRODUIT (2026-08-15, découvert le 2026-08-16) :

    brain_recall (BM25)        393 documents
    brain_embed  (embeddings)  458 documents
    écart : les 65 fiches de skills/, entrées dans le tronc le 15/08

`brain_embed.py` portait le commentaire « IMPORTANT : MÊME corpus que brain_recall ». Le
commentaire était faux depuis un jour, et rien ne pouvait le dire : **une parité affirmée
en prose ne rougit jamais**. Toute comparaison BM25 / embeddings aurait mesuré deux corpus
différents en croyant comparer deux méthodes de récupération — y compris le duel en
aveugle de l'ADR-0001, tranché AVANT la divergence.

POURQUOI LE CONTRÔLE EST STATIQUE. Vérifier l'égalité des deux listes en les important
toutes les deux serait TAUTOLOGIQUE depuis qu'elles viennent du même module : le test
passerait au vert en comparant un objet à lui-même, et resterait vert le jour où quelqu'un
réécrit une liste locale ailleurs. Ce qu'on surveille, c'est donc le geste qui a produit
l'incident : **la réapparition d'une définition locale**. cf.
[[une-assertion-tautologique-ne-peut-pas-rougir]] · [[un-detecteur-partage-par-concept]]

Lancer :
  python3 tests/corpus_partage.py
  python3 tests/corpus_partage.py --check      # barrière (statique, instantanée)
  python3 tests/corpus_partage.py --complet    # + comparaison RÉELLE des deux moteurs (venv)
"""
import argparse
import ast
import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
HOOKS = os.path.join(BRAIN, "hooks")
sys.path.insert(0, HOOKS)

import brain_corpus  # noqa: E402

# Les moteurs qui doivent CONSOMMER la définition, jamais l'écrire.
MOTEURS = ("brain_recall.py", "brain_embed.py")
SOURCE = "brain_corpus"
NOMS = ("SKIP_DIRS", "SKIP_PREFIX", "SKIP_FILES")


def analyser(fichier):
    """(définitions locales trouvées, importe-t-il la source ?)"""
    chemin = os.path.join(HOOKS, fichier)
    arbre = ast.parse(open(chemin, encoding="utf-8").read(), filename=chemin)

    locales, importe = [], False
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and noeud.module == SOURCE:
            importe = True
        if isinstance(noeud, ast.Import):
            for a in noeud.names:
                if a.name == SOURCE:
                    importe = True
        # Une AFFECTATION à l'un de ces noms est une copie locale. Un `from … import X`
        # ne produit pas de nœud Assign : les deux cas se distinguent proprement.
        if isinstance(noeud, (ast.Assign, ast.AnnAssign)):
            cibles = noeud.targets if isinstance(noeud, ast.Assign) else [noeud.target]
            for c in cibles:
                if isinstance(c, ast.Name) and c.id in NOMS:
                    locales.append((c.id, noeud.lineno))
    return locales, importe


def comparaison_reelle():
    """L'observable : ce que chaque moteur indexe VRAIMENT, chacun dans son interpréteur.

    brain_embed vit dans le venv (numpy + model2vec) ; brain_recall tourne sous le python
    du système. On ne peut donc pas les charger dans le même processus — et c'est justement
    pour ça que leurs corpus avaient pu diverger sans que personne ne les mette côte à côte.
    """
    import brain_recall as br
    a = {d["path"] for d in br.load_corpus()}

    venv = os.path.join(BRAIN, ".venv", "bin", "python")
    if not os.path.exists(venv):
        return a, None, "venv absent"
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import brain_embed as be\n"
        "print('\\n'.join(sorted(rel for rel, *_ in be.fiches())))\n" % HOOKS
    )
    try:
        out = subprocess.run([venv, "-c", code], capture_output=True, text=True, timeout=180)
    except Exception as e:                       # noqa: BLE001
        return a, None, f"échec du sous-processus : {e}"
    if out.returncode != 0:
        return a, None, (out.stderr or "").strip().splitlines()[-1:] or "erreur"
    return a, {l for l in out.stdout.split("\n") if l.strip()}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--complet", action="store_true",
                    help="compare RÉELLEMENT les deux moteurs (charge le venv, ~2 s)")
    a = ap.parse_args()

    print(f"Corpus partagé — source unique : hooks/{SOURCE}.py "
          f"({len(brain_corpus.indexable())} documents)\n")

    ennuis = []
    for m in MOTEURS:
        locales, importe = analyser(m)
        if locales:
            ennuis.append(f"{m} redéfinit localement " +
                          ", ".join(f"{n} (ligne {l})" for n, l in locales))
        if not importe:
            ennuis.append(f"{m} n'importe pas {SOURCE}")
        etat = "❌ copie locale" if locales else ("✅ importe la source" if importe
                                                 else "❌ n'importe rien")
        print(f"  hooks/{m:20} {etat}")

    if a.complet:
        print()
        bm25, vec, souci = comparaison_reelle()
        if souci:
            print(f"  ⚠️  comparaison réelle impossible : {souci}")
        else:
            seul_a, seul_b = sorted(bm25 - vec), sorted(vec - bm25)
            print(f"  brain_recall (BM25)        {len(bm25)} documents")
            print(f"  brain_embed  (embeddings)  {len(vec)} documents")
            if seul_a or seul_b:
                ennuis.append(f"corpus divergents : {len(seul_a)} document(s) vus du seul "
                              f"BM25, {len(seul_b)} du seul moteur d'embeddings")
                for p in (seul_a + seul_b)[:8]:
                    print(f"     ≠ {p}")
            else:
                print("  écart                      0 document ✅")

    if ennuis:
        print("\n❌ la définition du corpus n'est plus unique :")
        for e in ennuis:
            print(f"     {e}")
        print(f"\n   Un moteur qui s'écrit sa propre liste divergera — c'est arrivé le")
        print(f"   2026-08-15, 65 documents d'écart, invisible pendant un jour.")
        print(f"   Importer depuis hooks/{SOURCE}.py, ne pas recopier.")
        return 1

    print("\n✅ un seul corpus, défini une seule fois, consommé par les deux moteurs")
    if not a.complet:
        print("   (--complet pour comparer en plus les deux moteurs à l'exécution)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
