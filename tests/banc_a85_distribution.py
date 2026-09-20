#!/usr/bin/env python3
"""
banc_a85_distribution.py — A8.5 : la GÉOGRAPHIE du problème, avant tout réglage.

QUESTION (l'auteur, 2026-08-20) : quelle amplitude maximale la mémoire d'usage peut-elle avoir
pour départager des réponses PROCHES, sans avoir la puissance de renverser une différence de
pertinence SUBSTANTIELLE ?

CE QUI SERAIT UNE FAUTE : mesurer l'écart rang1↔rang2 global et protéger systématiquement le
premier lexical. Ce serait supposer que BM25 est la vérité. On stratifie donc par ce que les
CIBLES ÉTIQUETÉES disent, pas par ce que BM25 propose :

  classe 1  BM25 A RAISON        rang 1 ∈ cibles, rang 2 ∉ cibles
            → l'écart mesuré est un BUDGET DE PROTECTION : un bonus ne doit PAS pouvoir l'effacer.
  classe 2  INTERCHANGEABLES     rang 1 ∈ cibles ET rang 2 ∈ cibles
            → zone d'incertitude : un bonus qui agit ici ne casse rien.
  classe 3  BM25 SE TROMPE       rang 1 ∉ cibles
            → l'écart jusqu'à la meilleure cible est un BUDGET DE RÉPARATION : un bonus
              utile devrait pouvoir l'effacer.

LA QUESTION DEVIENT ALORS EXACTEMENT DÉCIDABLE : existe-t-il une amplitude inférieure aux
budgets de protection ET supérieure aux budgets de réparation ? Si les deux distributions se
recouvrent, aucune amplitude ne marche — et c'est un résultat d'architecture, pas de réglage.

Lecture seule. Ne modifie ni brain_recall.py, ni alpha, ni state/, ni _baseline, ni une fiche.

  python3 tests/banc_a85_distribution.py
"""
import json, math, os, statistics, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br

docs = br.load_corpus(); moteur = br.BM25(docs)
par_stem = {}
for d in docs: par_stem.setdefault(os.path.basename(d["path"])[:-3], d["path"])

# ── les 45 cas étiquetés : golden (15) + banc retrieval (30) ─────────────────
cas = []
for c in json.load(open(os.path.join(ICI, "golden_recall.json"), encoding="utf-8"))["cas"]:
    cas.append((c["id"], "golden", c["query"], set(c["attendu"])))
sans_cible = 0
for c in json.load(open(os.path.join(ICI, "banc-retrieval", "cas.json"), encoding="utf-8")):
    t_ = c["t"]
    if t_ is None:                       # cas « rien ne doit remonter » : hors sujet ici
        sans_cible += 1; continue
    stems = t_ if isinstance(t_, list) else [t_]     # C7 : deux fiches légitimes
    cibles = {par_stem[s] for s in stems if s in par_stem}
    if cibles: cas.append((stems[0][:22], c["c"], c["q"], cibles))

def classement(q):
    toks = br.tokenize(q); out = []
    for i, d in enumerate(moteur.docs):
        s = sum(moteur._contrib(i, t) for t in toks)
        if s > 0: out.append((s, d["path"]))
    out.sort(key=lambda x: -x[0]); return out

C1, C2, C3, perdus = [], [], [], []
for cid, fam, q, cibles in cas:
    r = classement(q)
    if len(r) < 2: continue
    (s1, p1), (s2, p2) = r[0], r[1]
    if p1 in cibles and p2 in cibles:
        C2.append((cid, fam, (s1 - s2) / s1))
    elif p1 in cibles:
        C1.append((cid, fam, (s1 - s2) / s1))
    else:
        meilleure = next(((s, p) for s, p in r if p in cibles), None)
        if meilleure is None: perdus.append((cid, fam)); continue
        C3.append((cid, fam, (s1 - meilleure[0]) / s1))

def resume(nom, L, sens):
    if not L: print(f"  {nom:44} — aucun cas"); return None
    v = sorted(x[2] for x in L)
    q = lambda p: v[min(len(v) - 1, int(p * len(v)))]
    print(f"  {nom:44} n={len(v):2d}  min {v[0]:6.1%}  q25 {q(.25):6.1%}  "
          f"méd {statistics.median(v):6.1%}  q75 {q(.75):6.1%}  max {v[-1]:6.1%}   {sens}")
    return v

print(f"corpus {len(docs)} fiches · {len(cas)} cas étiquetés · {len(perdus)} cible hors top · "
      f"{sans_cible} cas sans cible écartés\n")
print("── DISTRIBUTION DES ÉCARTS LEXICAUX, stratifiée par ce que les CIBLES disent ──\n")
vC1 = resume("classe 1 · BM25 a raison   (protection)", C1, "← un bonus ne doit PAS l'effacer")
vC2 = resume("classe 2 · interchangeables (zone libre)", C2, "← un bonus peut agir ici")
vC3 = resume("classe 3 · BM25 se trompe  (réparation)", C3, "← un bonus utile devrait l'effacer")

# ── portée réelle du bonus de production ────────────────────────────────────
UTIL = json.load(open(os.path.join(BRAIN, "state", "recall-utilite.json"), encoding="utf-8"))
hmax = max((v["hit"] for v in UTIL.values()), default=0)
portee = lambda h: 1 - 1 / (1 + 0.2 * math.log(1 + h))
print(f"\n── PORTÉE DU BONUS ACTUEL (alpha = 0,2) ────────────────────────────────────")
for h in (1, 2, 5, 10, hmax):
    print(f"   hit={h:3d} → efface jusqu'à {portee(h):6.1%} d'écart lexical"
          f"{'   ← maximum du corpus' if h == hmax else ''}")

print(f"\n── LA QUESTION DÉCIDABLE : les deux budgets se recouvrent-ils ? ─────────────")
if vC1 and vC3:
    for A in (portee(1), portee(2), portee(5), portee(hmax)):
        casse = sum(1 for x in vC1 if x <= A)          # protections que cette amplitude efface
        repare = sum(1 for x in vC3 if x <= A)         # réparations qu'elle rend possibles
        print(f"   amplitude {A:5.1%} → casse {casse:2d}/{len(vC1)} protections · "
              f"rend {repare:2d}/{len(vC3)} réparations possibles")
    sûr = [x for x in vC1]
    print(f"\n   plus petite protection observée : {min(vC1):.1%}")
    print(f"   plus petite réparation observée  : {min(vC3):.1%}")
    print(f"   → fenêtre utile {'INEXISTANTE' if min(vC3) >= min(vC1) else f'[{min(vC3):.1%} … {min(vC1):.1%}]'}"
          f"  (une amplitude doit être > réparation et < protection)")


# ── LE COMMERCE RÉELLEMENT PASSÉ, avec les hits qui existent vraiment ────────
# Ci-dessus, « casse » et « répare » sont des PORTÉES POTENTIELLES : elles supposent que le
# concurrent porte le bonus maximal. Ici on rejoue avec les compteurs réels de production.
def fac(p): return 1 + 0.2 * math.log(1 + UTIL.get(p, {}).get("hit", 0))

casse_reelle = repare_reelle = 0; det_c = []; det_r = []
for cid, fam, q, cibles in cas:
    r = classement(q)
    if len(r) < 2: continue
    avec = sorted(((s * fac(p), s, p) for s, p in r), key=lambda x: -x[0])
    nu_1, av_1 = r[0][1], avec[0][2]
    if nu_1 in cibles and av_1 not in cibles:
        casse_reelle += 1; det_c.append((cid, os.path.basename(av_1)))
    if nu_1 not in cibles and av_1 in cibles:
        repare_reelle += 1; det_r.append((cid, os.path.basename(av_1)))

print(f"\n── LE COMMERCE RÉELLEMENT PASSÉ (compteurs de production, alpha = 0,2) ──────")
print(f"   rangs 1 CASSÉS par le bonus  : {casse_reelle}/{len(C1)} cas où BM25 avait raison")
for cid, f in det_c: print(f"       {cid:24} → {f}")
print(f"   rangs 1 RÉPARÉS par le bonus : {repare_reelle}/{len(C3)} cas où BM25 se trompait")
for cid, f in det_r: print(f"       {cid:24} → {f}")
solde = repare_reelle - casse_reelle
print(f"\n   SOLDE : {solde:+d}  → le bonus d'utilité {'AIDE' if solde > 0 else 'COÛTE' if solde < 0 else 'est neutre'} "
      f"sur ce jeu étiqueté")
