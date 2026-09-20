#!/usr/bin/env python3
"""forme_requete — caractériser une requête SANS conserver son texte (chantier A8.8).

POURQUOI. A8.7 a montré que le bonus d'utilité gagne sur les requêtes très courtes (un titre
de deux mots produit des paquets d'ex æquo où le lexical n'a plus rien à dire) et perd sur les
questions (où l'écart lexical est franc). Impossible de trancher : `recall_log.jsonl`
n'enregistre QUE les fiches proposées, jamais la forme de la demande. On ne sait donc pas
laquelle des deux distributions ressemble à l'usage réel.

CE QUI EST ENREGISTRÉ — des nombres, et rien d'autre :
  n_tokens · n_uniques · classe_longueur · s1 · s2 · ecart_abs · ecart_rel · k
  exaequo : {"1%": n, "2%": n, "5%": n, "10%": n} — une grille, pas un seuil choisi d'avance

CE QUI NE L'EST JAMAIS. Aucun texte brut, aucun fragment lexical, aucun token, aucun hash —
même non réversible. La raison n'est pas seulement la confidentialité : le Brain a déjà
détruit un de ses propres témoins en recopiant une requête d'évaluation dans une fiche
(cf. utilite-boucle-popularite-2026-08-19, § « Pourquoi cette fiche ne cite pas la question »).
Un journal qui contiendrait le texte des requêtes serait la même faute, en pire.

⚠️ CE QUE ÇA LAISSE FUIR QUAND MÊME, et il faut le dire : les scores `s1`/`s2` sont ceux du
corpus. Quelqu'un qui possède le corpus peut, pour un score donné, restreindre l'ensemble des
requêtes possibles. Ce n'est pas une reconstruction du texte, mais ce n'est pas zéro non plus.
"""

# GRILLE de tolérances, pas un seuil unique. La calibration du 2026-08-20 a montré qu'un
# seuil unique à 2 % ratait le cas même qui motive la mesure : la requête « claude brain »
# a ses quatre premiers candidats étalés sur ~3 %, donc comptés comme NON ex æquo. Choisir
# le seuil maintenant reviendrait à décider d'avance ce qu'on cherche à mesurer — c'est la
# faute que le chantier A8.4 a déjà attrapée une fois (grille entière, jamais un seuil trié).
TOLERANCES_EXAEQUO = (0.01, 0.02, 0.05, 0.10)

_CLASSES = ((2, "1-2"), (5, "3-5"), (10, "6-10"), (float("inf"), ">10"))


def classe_longueur(n):
    for borne, nom in _CLASSES:
        if n <= borne: return nom
    return ">10"


def mesurer(tokens, records, k=10):
    """tokens : la liste déjà tokenisée (jamais conservée). records : sortie de
    BM25.classer(), dont on ne lit que les scores. Retourne un dict de NOMBRES."""
    n = len(tokens)
    out = {"n_tokens": n, "n_uniques": len(set(tokens)), "classe_longueur": classe_longueur(n),
           "k": k}

    # écart LEXICAL pur : on retrie sur bm25, sans le facteur d'utilité ni l'exploration,
    # sinon on mesurerait l'effet qu'on cherche justement à instruire.
    lex = sorted((r.get("bm25", 0.0) for r in records), reverse=True)[:k]
    if not lex: return {**out, "s1": None, "s2": None, "ecart_abs": None,
                        "ecart_rel": None, "exaequo": {f"{t:.0%}": 0 for t in TOLERANCES_EXAEQUO}}
    s1 = lex[0]; s2 = lex[1] if len(lex) > 1 else None
    out["s1"] = round(s1, 3)
    out["s2"] = round(s2, 3) if s2 is not None else None
    out["ecart_abs"] = round(s1 - s2, 3) if s2 is not None else None
    out["ecart_rel"] = round((s1 - s2) / s1, 4) if s2 is not None and s1 else None
    out["exaequo"] = {f"{tol:.0%}": sum(1 for s in lex if s1 and s >= s1 * (1 - tol))
                      for tol in TOLERANCES_EXAEQUO}
    return out
