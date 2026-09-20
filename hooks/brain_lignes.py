#!/usr/bin/env python3
"""brain_lignes — `brain recall --lignes` : rendre les passages qui répondent, pas des fiches entières.

Opt-in. Sans `--lignes`, `brain recall` ne change pas.

CE QUE ÇA REND
    Les 3 premières fiches du classement habituel, nom et chemin, sans description. Pour la 1re,
    et pour la 2e si son score vaut au moins 90 % de celui de la 1re, les SECTIONS (un titre
    Markdown et ses lignes) qui répondent le mieux à la question, avec leurs numéros de ligne
    dans le fichier — de quoi ouvrir la fiche au bon endroit si le passage ne suffit pas.
    Budget : 1 400 jetons (octets ÷ 2,2), 80 % pour la 1re fiche, 20 % pour la 2e.

COMMENT LES SECTIONS SONT CHOISIES
    Chaque section est notée par BM25 (k1 = 1,2, b = 0,75, longueur moyenne 60 mots indexés)
    sur les mots de la question, avec les IDF du moteur. On la prend entière tant qu'elle tient
    dans le budget ; la première qui ne tient plus est réduite à ses meilleures lignes (± 2
    voisines, sans sortir de la section), précédées de son titre.

POURQUOI CES RÉGLAGES — mesuré le 17/09 (tools/CHANTIER-RECALL-SOBRE-2026-09-16.md, §7 et §9)
    Réglés sur 40 questions du banc du 15/09, gelés, puis joués UNE fois sur les 40 autres.
    Critère posé avant la conception : rendre la réponse au moins aussi souvent que « liste +
    lecture de la 1re fiche », pour au plus la moitié de ses jetons par réponse juste.
    Sur la moitié contrôle : 27/40 contre 24/40, 1 796 jetons par réponse juste contre 4 216.
    Le prototype et ses variantes écartées : tools/recall-sobre/lignes.py. Ce module doit rendre
    exactement la même sortie que le prototype gelé — tools/recall-sobre/mesure.py le vérifie.

CE QUI N'EST PAS MESURÉ
    Une session qui ne trouve pas la réponse dans les passages va-t-elle ouvrir la fiche ? Le banc
    compte la réponse présente dans le texte rendu ; il ne joue pas la session.
"""
import os
import re

BRAIN = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OCTETS_PAR_JETON = 2.2

REGLAGES = {
    "k": 3,               # fiches nommées
    "n_fiches": 2,        # fiches dont on rend des passages
    "rho": 0.9,           # la 2e n'a des passages que si score ≥ rho × score de la 1re
    "budget": 1400,       # jetons pour l'ensemble des passages
    "parts": (0.8, 0.2),  # part du budget par rang
    "fenetre": 2,         # voisines rendues autour d'une ligne, dans une section trop grosse
}


def _corps(raw):
    """(numéro de ligne dans le fichier, texte) pour chaque ligne après le frontmatter."""
    lignes = raw.split("\n")
    debut = 0
    if lignes and lignes[0] == "---":
        for i in range(1, len(lignes)):
            if lignes[i] == "---":
                debut = i + 1
                break
    return [(i + 1, lignes[i]) for i in range(debut, len(lignes))]


def _jetons(texte):
    return len(texte.encode("utf-8")) / OCTETS_PAR_JETON


def _note(moteur, tokenize, texte, qset):
    k1, b, moy = 1.2, 0.75, 60.0
    toks = tokenize(texte)
    n = len(toks) or 1
    note = 0.0
    for t in qset:
        f = toks.count(t)
        if f:
            note += moteur.idf.get(t, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * n / moy))
    return note


def passages(moteur, tokenize, q, path, budget, fenetre):
    """[(1re ligne, dernière ligne, [textes])] — les sections de la fiche qui répondent à q."""
    corps = _corps(open(os.path.join(BRAIN, path), encoding="utf-8").read())
    qset = set(tokenize(q))
    groupes, n = {}, 0
    for j, (_, l) in enumerate(corps):
        if re.match(r"^#{1,6} ", l):
            n += 1
        groupes.setdefault(n, []).append(j)
    notes = []
    for s, js in groupes.items():
        texte = "\n".join(corps[j][1] for j in js)
        if texte.strip():
            score = _note(moteur, tokenize, texte, qset)
            if score > 0:
                notes.append((-score, s))
    pris, cout = set(), 0.0
    for _, s in sorted(notes):
        js = [j for j in groupes[s] if corps[j][1].strip()]
        ajout = sum(_jetons(corps[j][1]) + 1 for j in js)
        if cout + ajout <= budget:
            pris.update(js)
            cout += ajout
            continue
        # section trop grosse : ses meilleures lignes, dans le budget restant
        if budget - cout < 40:
            break
        sous = [(-sum(moteur.idf.get(t, 0) for t in set(tokenize(corps[j][1])) & qset), j) for j in js]
        for sc, j in sorted(sous):
            if sc == 0:
                break
            vois = [x for x in range(j - fenetre, j + fenetre + 1) if x in js and x not in pris]
            a = sum(_jetons(corps[x][1]) + 1 for x in vois)
            if cout + a > budget:
                continue
            pris.update(vois)
            cout += a
            if js[0] not in pris:            # le titre de la section, pour situer les lignes
                pris.add(js[0])
                cout += _jetons(corps[js[0]][1]) + 1
        break
    plages, courante = [], []
    for x in sorted(pris):
        if courante and x != courante[-1] + 1:
            plages.append(courante)
            courante = []
        courante.append(x)
    if courante:
        plages.append(courante)
    return [(corps[p[0]][0], corps[p[-1]][0], [corps[x][1] for x in p]) for p in plages]


def rendre(moteur, tokenize, q, res, **reglages):
    """Le texte rendu pour `res`, la sortie de BM25.classer()."""
    r = dict(REGLAGES, **reglages)
    out = []
    for rang, x in enumerate(res[:r["k"]]):
        d = x["doc"]
        out.append(f"{rang + 1}. {d['name']} ({d['path']})")
        if rang < r["n_fiches"] and (rang == 0 or x["score"] >= r["rho"] * res[0]["score"]):
            part = r["parts"][rang] if rang < len(r["parts"]) else r["parts"][-1]
            for a, b, textes in passages(moteur, tokenize, q, d["path"], r["budget"] * part, r["fenetre"]):
                out.append(f"   L{a}-{b}:" if a != b else f"   L{a}:")
                out.extend(f"   {t.strip()}" for t in textes)
    return "\n".join(out) + "\n"
