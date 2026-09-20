#!/usr/bin/env python3
"""vision_hors_corpus.py — les documents SOURCES restent-ils hors du rappel ?

L'INVARIANT :

    Aucun fichier de `vision/` n'entre dans le corpus de rappel (BM25 + embeddings),
    ni dans le compteur de fiches de `brain_doctor`.

POURQUOI IL EXISTE (2026-08-19) :

    `vision/` accueille des DOCUMENTS SOURCES : de longs récits qui expliquent pourquoi
    le système existe (le MASTER C Brain/GMatter, ~32 Ko). Ils ne sont pas des fiches
    de savoir. Un seul d'entre eux touche tout le vocabulaire du projet : indexé, il
    remonterait sur presque chaque requête et écraserait la fiche précise cherchée.
    C'est exactement ce qui avait été MESURÉ le 2026-08-14 pour `archive/` — un journal
    archivé ressortait en 1re position devant la fiche courante.

    L'exclusion n'est donc pas une préférence de rangement : c'est une condition pour
    que le rappel reste utilisable.

POURQUOI CE TEST PORTE SON PROPRE SABOTAGE :

    Une exclusion déclarée dans un `SKIP_DIRS` ne rougit jamais toute seule : si
    quelqu'un retire la ligne, le corpus grossit en silence et rien ne le dit. Le test
    vérifie donc AUSSI que, privé de la ligne, le document REDEVIENDRAIT indexé. Un
    contrôle qui ne peut pas virer au rouge ne protège de rien.
    cf. [[chaine-de-preuve-mesure-baseline-sabotage]]
"""
import os, sys

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
sys.path.insert(0, HOOKS)

import brain_corpus                                     # noqa: E402
import brain_doctor                                     # noqa: E402

BRAIN = brain_corpus.BRAIN
VISION = os.path.join(BRAIN, "vision")


def main():
    ennuis = []
    print("🔭 vision/ — documents sources hors rappel\n")

    # --- 0. la zone existe-t-elle, et que contient-elle ? ---
    if not os.path.isdir(VISION):
        print("  vision/ absent — rien à vérifier (zone pas encore créée)")
        return 0
    docs = sorted(f for f in os.listdir(VISION) if f.endswith(".md"))
    print(f"  documents sources          {len(docs)}")
    for d in docs:
        print(f"     · {d}")

    # --- 1. la règle générique : tout chemin vision/… est écarté ---
    sonde = os.path.join("vision", "sonde-inexistante.md")
    if not brain_corpus.skip(sonde):
        ennuis.append("brain_corpus.skip() n'écarte pas les chemins vision/")

    # --- 2. les documents RÉELS sont absents du corpus indexable ---
    indexes = {rel for rel, _ in brain_corpus.indexable()}
    fuites = sorted(r for r in indexes if r.split(os.sep)[0] == "vision")
    print(f"\n  corpus de rappel           {len(indexes)} documents")
    if fuites:
        ennuis.append(f"{len(fuites)} document(s) de vision/ dans le corpus de rappel")
        for f in fuites[:5]:
            print(f"     ⚠ {f}")
    else:
        print("  dont vision/               0 ✅")

    # --- 3. doctor ne les compte pas comme des fiches ---
    vues = {os.path.relpath(p, BRAIN) for p in brain_doctor.md_files()}
    fuites_d = sorted(r for r in vues if r.split(os.sep)[0] == "vision")
    print(f"\n  fiches vues par doctor     {len(vues)}")
    if fuites_d:
        ennuis.append(f"{len(fuites_d)} document(s) de vision/ comptés comme fiches par doctor")
        for f in fuites_d[:5]:
            print(f"     ⚠ {f}")
    else:
        print("  dont vision/               0 ✅")

    # --- 4. CONTRE-ÉPREUVE : sans la ligne, le document redevient-il indexé ? ---
    #     Sans ce bloc, le test resterait vert le jour où `vision/` disparaîtrait du
    #     SKIP_DIRS mais où le dossier serait vide — il ne prouverait rien du tout.
    print("\n  contre-épreuve (sabotage) :")
    if not docs:
        print("     ⚠ aucun document dans vision/ — sabotage non concluant")
        ennuis.append("vision/ vide : la contre-épreuve ne peut pas s'exécuter")
    else:
        garde = set(brain_corpus.SKIP_DIRS)
        try:
            brain_corpus.SKIP_DIRS.discard("vision")
            sans = {rel for rel, _ in brain_corpus.indexable()}
            revenus = sorted(r for r in sans if r.split(os.sep)[0] == "vision")
        finally:
            brain_corpus.SKIP_DIRS.clear()
            brain_corpus.SKIP_DIRS.update(garde)
        if len(revenus) != len(docs):
            ennuis.append(
                f"sabotage non concluant : sans la ligne, {len(revenus)} document(s) "
                f"reviennent au lieu de {len(docs)} — l'exclusion ne vient peut-être "
                f"pas de SKIP_DIRS, donc ce test ne surveille pas ce qu'il croit")
            print(f"     ❌ {len(revenus)} revenu(s) sur {len(docs)} attendu(s)")
        else:
            print(f"     ✅ sans la ligne, les {len(revenus)} document(s) redeviennent "
                  f"indexés — le contrôle peut virer au ROUGE")
        # l'exclusion doit être rétablie à l'identique
        if brain_corpus.SKIP_DIRS != garde:
            ennuis.append("SKIP_DIRS non restauré après sabotage")

    if ennuis:
        print("\n❌ les documents sources ne sont plus isolés du rappel :")
        for e in ennuis:
            print(f"     {e}")
        print("\n   Un document source indexé écrase les fiches précises sur presque")
        print("   chaque requête. Rétablir \"vision\" dans hooks/brain_corpus.py:SKIP_DIRS")
        print("   et hooks/brain_doctor.py:SKIP_DIRS.")
        return 1

    print("\n✅ vision/ est une zone source : versionnée, pointée par la carte, hors rappel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
