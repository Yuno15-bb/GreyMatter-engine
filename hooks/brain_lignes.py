#!/usr/bin/env python3
"""brain_lignes — `brain recall --lines`: return the passages that answer, not whole notes.

Opt-in. Without `--lines`, `brain recall` does not change.

WHAT IT RETURNS
    The first 3 notes of the usual ranking, name and path, no description. For the 1st,
    and for the 2nd if its score is at least 90% of the 1st's, the SECTIONS (a Markdown
    heading and its lines) that best answer the question, with their line numbers in the
    file — enough to open the note at the right place if the passage is not enough.
    Budget: 1,400 tokens (bytes ÷ 2.2), 80% for the 1st note, 20% for the 2nd.

HOW THE SECTIONS ARE CHOSEN
    Each section is scored by BM25 (k1 = 1.2, b = 0.75, mean length 60 indexed words)
    on the words of the question, with the engine's IDFs. It is taken whole as long as it fits
    in the budget; the first one that no longer fits is cut down to its best lines (± 2
    neighbours, without leaving the section), preceded by its heading.

WHY THESE SETTINGS — measured on 17/09 (in the author's bench notes, not shipped)
    Tuned on 40 questions from the 15/09 bench, frozen, then played ONCE on the other 40.
    Criterion set before the design: return the answer at least as often as "list +
    reading the 1st note", for at most half of its tokens per correct answer.
    On the control half: 27/40 against 24/40, 1,796 tokens per correct answer against 4,216.
    The prototype and its discarded variants live in the same bench. This module must return
    exactly the same output as the frozen prototype — the bench checks it.

WHAT IS NOT MEASURED
    Will a session that does not find the answer in the passages go and open the note? The bench
    counts the answer present in the returned text; it does not play the session.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # CODE_ROOT, legitimate
from brain_racine import brain_root

# The trunk the passages are read from, never the folder this code sits in: once installed,
# the engine and the trunk are two different trees, and `path` is relative to the trunk.
BRAIN = brain_root(__file__)
OCTETS_PAR_JETON = 2.2

REGLAGES = {
    "k": 3,               # notes named
    "n_fiches": 2,        # notes whose passages are returned
    "rho": 0.9,           # the 2nd gets passages only if score ≥ rho × score of the 1st
    "budget": 1400,       # tokens for all the passages
    "parts": (0.8, 0.2),  # share of the budget per rank
    "fenetre": 2,         # neighbours returned around a line, in a section that is too big
}


def _corps(raw):
    """(line number in the file, text) for each line after the frontmatter."""
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
    """[(1st line, last line, [texts])] — the note's sections that answer q."""
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
        # section too big: its best lines, within the remaining budget
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
            if js[0] not in pris:            # the section heading, to place the lines
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
    """The text returned for `res`, the output of BM25.rank()."""
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
