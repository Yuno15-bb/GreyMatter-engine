#!/usr/bin/env python3
"""
utilite_hors_rang.py — le banc qui interdit à l'usage de revenir dans le classement.

ADR-0018 a décidé le 2026-08-30 que le bonus d'utilité SORT du rang (mécanisme M5) ; il a
été installé le 2026-09-19. La décision ne tient que si quelque chose empêche le retour :
un multiplicateur remis « juste pour départager », un tri de présentation par nombre
d'ouvertures, un seuil d'affichage — chacun ramènerait l'usage dans l'ordre sans qu'on le
voie. C'est ce banc qui doit rougir ce jour-là.

CE QU'IL MESURE, et pourquoi pas autre chose
  Le contrôle écrit au §14.3 du candidat disait : « sur des requêtes sans ex æquo, la liste
  servie doit être identique à celle de BM25 seul ». Il partage son instrument avec
  l'action — c'est la faute de [[un-controle-qui-partage-l-instrument-de-l-action-ne-peut-pas-la-contredire]] :
  si le moteur reclasse, sa liste « BM25 seul » reclasse aussi.
  Donc on PERTURBE au lieu de comparer : on fabrique de faux compteurs qui donnent un gros
  historique aux fiches juste sous le top, et on exige que l'ordre servi NE BOUGE PAS.
  Une perturbation vient du dehors du moteur ; elle ne peut pas être absorbée par lui.

  · on ne touche QUE `hit`. `sugg` reste identique, parce que le quota d'exploration
    (ADR-0004, maintenu) le lit : le bouger ferait rougir le banc pour une raison légitime.

CONTRE-ÉPREUVE JOUÉE À CHAQUE FOIS, et le banc échoue si elle est muette
  Un banc dont la perturbation serait trop faible serait vert par impuissance. On rejoue
  donc l'ANCIENNE règle (bm25 × (1 + 0,2·ln(1+hits))) sur ces mêmes faux compteurs : elle
  DOIT déplacer des fiches. Si elle n'en déplace aucune, le banc se déclare inutilisable
  au lieu de s'annoncer vert.

  python3 tests/utilite_hors_rang.py            (récit)
  python3 tests/utilite_hors_rang.py --check    (verdict seul, pour le commit)
"""
import copy, json, math, os, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br

K = 5                      # la profondeur servie
N_REQUETES = 24            # échantillon déterministe, pris régulièrement dans le corpus
HITS_FAUX = 200            # gros historique : ×2,06 sous l'ancienne règle
ALPHA_HISTORIQUE = 0.2     # la valeur qu'avait la production avant le 2026-09-19


def requetes(docs):
    """Le titre d'une fiche : la requête dont on connaît la meilleure réponse sans étiquetage.

    Pris tous les N dans l'ordre des chemins — déterministe, et réparti sur tout le tronc
    plutôt que sur un dossier."""
    titres = sorted((d.get("title") or d["name"]).replace("-", " ") for d in docs)
    pas = max(1, len(titres) // N_REQUETES)
    return titres[::pas][:N_REQUETES]


def servie(moteur, q, util):
    br._UTILITE_CACHE = util
    return [(r["doc"]["path"], r["rang"]) for r in moteur.classer(q, k=K)]


def lexical(moteur, q, n):
    """L'ordre purement lexical et ses scores — feedback=False ne lit aucun compteur."""
    return moteur.classer(q, k=n, feedback=False)


def main():
    check = "--check" in sys.argv
    docs = br.load_corpus()
    moteur = br.BM25(docs)
    reel = copy.deepcopy(br._utilite() or {})

    deplaces, sensibles, sans_resultat = [], 0, 0
    for q in requetes(docs):
        base = lexical(moteur, q, K + 10)
        if len(base) <= K:
            sans_resultat += 1
            continue

        # ── les faux compteurs : rien en tête, beaucoup juste dessous ───────────
        faux = copy.deepcopy(reel)
        for i, r in enumerate(base):
            p = r["doc"]["path"]
            faux.setdefault(p, {"sugg": 0, "hit": 0})
            faux[p]["hit"] = 0 if i < K else HITS_FAUX

        avant = servie(moteur, q, reel)
        apres = servie(moteur, q, faux)
        if avant != apres:
            bouge = [p for (p, _), (p2, _) in zip(avant, apres) if p != p2]
            deplaces.append((q, len(bouge)))

        # ── contre-épreuve : l'ANCIENNE règle bouge-t-elle, elle ? ──────────────
        vieux = sorted(base, key=lambda r: -(r["bm25"] *
                       (1 + ALPHA_HISTORIQUE * math.log(1 + faux[r["doc"]["path"]]["hit"]))))
        if [r["doc"]["path"] for r in vieux[:K]] != [r["doc"]["path"] for r in base[:K]]:
            sensibles += 1

    br._UTILITE_CACHE = reel
    jouees = N_REQUETES - sans_resultat
    ok_invariant = not deplaces
    ok_sensible = sensibles > 0

    if not check:
        print(f"\n{jouees} requêtes jouées sur {N_REQUETES} · corpus {len(docs)} fiches\n")
        print(f"  compteurs faussés, ordre servi inchangé : "
              f"{jouees - len(deplaces)}/{jouees}")
        if deplaces:
            print("  ⛔ l'usage déplace encore des fiches :")
            for q, n in deplaces[:5]:
                print(f"       {n} place(s) changée(s) — « {q[:60]} »")
        print(f"  contre-épreuve, l'ancienne règle aurait bougé : {sensibles}/{jouees}")
        print()

    if not ok_sensible:
        print("⛔ banc INUTILISABLE : la perturbation ne déplace rien même sous "
              "l'ancienne règle — il serait vert par impuissance.")
        return 1
    if not ok_invariant:
        print(f"⛔ l'utilité est revenue dans le classement : {len(deplaces)} requêtes "
              f"sur {jouees} changent d'ordre quand on fausse les compteurs (ADR-0018, M5).")
        return 1
    print(f"✅ l'utilité reste hors du rang — {jouees} requêtes, ordre inchangé sous de faux "
          f"compteurs, et l'ancienne règle en aurait bougé {sensibles}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
