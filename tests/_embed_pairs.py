#!/usr/bin/env python3
"""_embed_pairs.py — B3 : la similarité SÉMANTIQUE comme prétendu signal de contradiction.

Tourne DANS le venv (model2vec + numpy). Appelé par tests/detection_conflits.py --embeddings.

CE QU'IL EXISTE POUR MONTRER. « Mettez des embeddings » est la suggestion la plus
prévisible qu'un audit puisse faire sur ce chantier. Elle repose sur une confusion :
la similarité mesure que deux phrases PARLENT DE LA MÊME CHOSE, jamais qu'elles
s'EXCLUENT. Deux affirmations opposées sont les plus similaires qui soient — « on garde
BM25 » et « on abandonne BM25 » ne diffèrent que par un mot.

On ne l'affirme pas, on le mesure : si la similarité était le signal, les CONTRADICTION
du jeu se sépareraient des COMPATIBLE. Le chiffre publié ci-dessous est cet écart.
"""
import json
import os
import sys

import numpy as np
from model2vec import StaticModel

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))

MODEL = "minishlab/potion-base-8M"


def main():
    jeu = json.load(open(os.path.join(ICI, "fixtures_detection.json"), encoding="utf-8"))
    cas = jeu["cas"]
    m = StaticModel.from_pretrained(MODEL)

    va = m.encode([c["A"]["texte"] for c in cas])
    vb = m.encode([c["B"]["texte"] for c in cas])
    va = va / np.linalg.norm(va, axis=1, keepdims=True)
    vb = vb / np.linalg.norm(vb, axis=1, keepdims=True)
    sims = (va * vb).sum(axis=1)

    par_classe = {}
    for c, s in zip(cas, sims):
        par_classe.setdefault(c["attendu"], []).append((float(s), c["id"]))

    print(f"B3 — similarité sémantique (model2vec {MODEL})\n")
    print("  Similarité MOYENNE par classe attendue :\n")
    moyennes = {}
    for cl, vals in sorted(par_classe.items(), key=lambda kv: -np.mean([v for v, _ in kv[1]])):
        moy = float(np.mean([v for v, _ in vals]))
        moyennes[cl] = moy
        print(f"    {cl:22} {moy:.3f}   (n={len(vals)})")

    contra = moyennes.get("CONTRADICTION", 0)
    compat = moyennes.get("COMPATIBLE", 0)
    print(f"\n  Écart CONTRADICTION − COMPATIBLE : {contra - compat:+.3f}")
    print("  Si la similarité était le signal, cet écart serait franc et POSITIF.")

    # Le meilleur seuil possible, choisi APRÈS coup sur les étiquettes — donc une borne
    # SUPÉRIEURE optimiste que jamais aucun réglage honnête n'atteindrait en production.
    best, bs = 0.0, None
    ordre = sorted(set(float(s) for s in sims))
    for seuil in ordre:
        pred = ["CONTRADICTION" if s >= seuil else "COMPATIBLE" for s in sims]
        just = sum(1 for c, p in zip(cas, pred)
                   if (c["attendu"] == "CONTRADICTION") == (p == "CONTRADICTION"))
        if just / len(cas) > best:
            best, bs = just / len(cas), seuil
    trivial = 1 - sum(1 for c in cas if c["attendu"] == "CONTRADICTION") / len(cas)
    print(f"\n  Meilleur seuil possible (choisi SUR les étiquettes, donc triché) : "
          f"{bs:.3f} → {best:.0%} de bons verdicts conflit/pas-conflit")
    print(f"  Référence : tout déclarer COMPATIBLE en donne déjà {trivial:.0%}.")
    print(f"  Gain réel de la similarité sémantique : {best - trivial:+.0%}")

    # Les trois pièges à recouvrement faible : le sémantique les rattrape-t-il ?
    print("\n  Les 3 contradictions lexicalement invisibles (piège recouvrement-faible) :")
    for c, s in zip(cas, sims):
        if c.get("piege") == "recouvrement-faible":
            print(f"    {float(s):.3f}  {c['id']}")
    seuil_ref = np.mean([s for c, s in zip(cas, sims) if c["attendu"] == "COMPATIBLE"])
    print(f"    (moyenne des COMPATIBLE : {float(seuil_ref):.3f} — "
          "au-dessus ou en dessous ? c'est toute la question)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
