#!/usr/bin/env python3
"""
banc_a86_departage.py — A8.6 · ÉTAPE 2 : l'historique sait-il DÉPARTAGER deux réponses
déjà légitimes ? C'est la dernière fonction d'ADR-0003 jamais mesurée.

Trois fonctions possibles de l'historique, et leur état :
  A. CORRECTION   faire remonter une fiche que BM25 rate      → A8.5 : impossible (14/14 à 0 hit)
  B. RENVERSEMENT passer devant une meilleure réponse          → A8.5 : nuisible (−5 contre 0)
  C. DÉPARTAGE    choisir entre deux réponses légitimes        → ICI

Les cas viennent de tests/a86_classe2.json, gelé et commité AVANT que ce script n'existe.
Lecture seule : ne modifie ni brain_recall.py, ni alpha, ni state/, ni _baseline, ni une fiche.

  python3 tests/banc_a86_departage.py
"""
import collections, datetime, json, math, os, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br
import recall_feedback as rf

GEL = json.load(open(os.path.join(ICI, "a86_classe2.json"), encoding="utf-8"))
UTIL = json.load(open(os.path.join(BRAIN, "state", "recall-utilite.json"), encoding="utf-8"))
hits = lambda p: UTIL.get(p, {}).get("hit", 0)

docs = br.load_corpus(); moteur = br.BM25(docs)
par_stem = {}
for d in docs: par_stem.setdefault(os.path.basename(d["path"])[:-3], d["path"])
cas_q = {}
for c in json.load(open(os.path.join(ICI, "golden_recall.json"), encoding="utf-8"))["cas"]:
    cas_q[c["id"]] = c["query"]
for i, c in enumerate(json.load(open(os.path.join(ICI, "banc-retrieval", "cas.json"), encoding="utf-8"))):
    if c["t"] is None: continue
    st = c["t"] if isinstance(c["t"], list) else [c["t"]]
    cas_q[f"r{i:02d}-{st[0][:20]}"] = c["q"]        # id UNIQUE : la troncature à 24 collisionnait
        # index sans ambiguïté : la requête d'une paire est celle dont les CIBLES sont cette paire
par_paire = {}
for c in json.load(open(os.path.join(ICI, "golden_recall.json"), encoding="utf-8"))["cas"]:
    if len(c["attendu"]) == 2: par_paire[frozenset(c["attendu"])] = c["query"]
for c in json.load(open(os.path.join(ICI, "banc-retrieval", "cas.json"), encoding="utf-8")):
    if isinstance(c["t"], list) and len(c["t"]) == 2:
        ci = frozenset(par_stem[s] for s in c["t"] if s in par_stem)
        if len(ci) == 2: par_paire[ci] = c["q"]

def bm25(q):
    tk = br.tokenize(q); o = []
    for i, d in enumerate(moteur.docs):
        s = sum(moteur._contrib(i, t) for t in tk)
        if s > 0: o.append((s, d["path"]))
    o.sort(key=lambda x: -x[0]); return o

# ── QUESTION 1 · le départage est-il seulement POSSIBLE ? ───────────────────
print("── Q1 · Dans la classe 2, les deux réponses ont-elles un historique DIFFÉRENT ? ──\n")
print(f"{'':4}{'hits A':>7}{'hits B':>8}   paire")
departageables = 0
for n in GEL["noyau"]:
    a, b = n["paire"]
    ha, hb = hits(a), hits(b)
    if ha != hb: departageables += 1
    marq = "→ départageable" if ha != hb else ("(les deux à 0)" if ha == hb == 0 else "(égalité)")
    print(f"    {ha:7d}{hb:8d}   {os.path.basename(a)[:32]:34} ↔ {os.path.basename(b)[:32]:34} {marq}")
print(f"\n   paires que l'historique peut départager : {departageables}/{len(GEL['noyau'])}")

# ── QUESTION 2 · à quelle fréquence le départage est-il ATTEIGNABLE, sur les 40 cas ? ──
print("\n── Q2 · Sur les 40 cas étiquetés : combien de candidats du top-3 ont un historique ? ──\n")
rep = collections.Counter()
vus=set()
for cid, q in cas_q.items():
    if q in vus: continue          # les alias ne doivent pas compter deux fois
    vus.add(q)
    r = bm25(q)[:3]
    rep[sum(1 for _, p in r if hits(p) > 0)] += 1
tot = sum(rep.values())
for k in sorted(rep):
    quoi = {0: "le bonus ne fait RIEN",
            1: "le bonus ne peut que RENVERSER (fonction B)",
            2: "départage possible (fonction C)",
            3: "départage possible (fonction C)"}[k]
    print(f"   {k} fiche(s) du top-3 avec historique : {rep[k]:2d}/{tot}  ({100*rep[k]/tot:4.1f} %)   {quoi}")
c_possible = sum(v for k, v in rep.items() if k >= 2)
print(f"\n   → fonction C atteignable sur {c_possible}/{tot} cas ({100*c_possible/tot:.1f} %)")

# ── QUESTION 3 · les trois classements, sur la classe 2 ─────────────────────
print("\n── Q3 · BM25 seul · V0 actuel · historique en TIE-BREAK seul ──────────────\n")
EPS = 0.02
def rang(o, p):
    for i, (_, x) in enumerate(o, 1):
        if x == p: return i
    return 999
def v0(o):
    return sorted(((s * (1 + 0.2 * math.log(1 + hits(p))), p) for s, p in o), key=lambda x: -x[0])
def tiebreak(o):
    if not o: return o
    smax = o[0][0]
    return sorted(o, key=lambda x: (-x[0] / smax if x[0] / smax < 1 - EPS else -1.0,
                                    -hits(x[1]) if x[0] / smax >= 1 - EPS else 0, -x[0]))
print(f"{'cas':26}{'BM25 seul':>18}{'V0 actuel':>18}{'tie-break':>18}   les deux dans le top-3 ?")
for n in GEL["noyau"]:
    a, b = n["paire"]; q = par_paire.get(frozenset((a, b)))
    if not q: print(f"{n['id'][:24]:26}   requête introuvable"); continue
    o = bm25(q)
    lignes = []
    for nom, cl in (("bm25", o), ("v0", v0(o)), ("tb", tiebreak(o))):
        ra, rb = rang(cl, a), rang(cl, b)
        lignes.append(f"{ra}/{rb}")
    top3 = all(max(rang(cl, a), rang(cl, b)) <= 3 for cl in (o, v0(o), tiebreak(o)))
    print(f"{n['id'][:24]:26}{lignes[0]:>18}{lignes[1]:>18}{lignes[2]:>18}   "
          f"{'oui partout' if top3 else 'NON'}")

print("\n── VERDICT ────────────────────────────────────────────────────────────────")
print(f"  classe 2 disponible : {len(GEL['noyau'])} paires annotées — la classe étendue a été")
print(f"  DISQUALIFIÉE par son propre contrôle (cf. en-tête de banc_a86_classe2.py).")

# ── QUESTION 4 · les trois classements sur les 40 cas : la justesse globale ──
print("\n── Q4 · BM25 seul vs V0 vs tie-break — justesse sur les 40 cas étiquetés ──\n")
etiq = []
for c in json.load(open(os.path.join(ICI, "golden_recall.json"), encoding="utf-8"))["cas"]:
    etiq.append((c["id"], c["query"], set(c["attendu"])))
for i, c in enumerate(json.load(open(os.path.join(ICI, "banc-retrieval", "cas.json"), encoding="utf-8"))):
    if c["t"] is None: continue
    st = c["t"] if isinstance(c["t"], list) else [c["t"]]
    ci = {par_stem[s] for s in st if s in par_stem}
    if ci: etiq.append((f"r{i:02d}", c["q"], ci))

def tb(o, eps):
    if not o: return o
    smax = o[0][0]
    proche = [x for x in o if x[0] >= smax * (1 - eps)]
    reste  = [x for x in o if x[0] <  smax * (1 - eps)]
    proche.sort(key=lambda x: (-hits(x[1]), -x[0]))
    return proche + reste

def score(fn):
    p1 = p3 = 0
    for cid, q, cibles in etiq:
        o = fn(bm25(q))
        if not o: continue
        if o[0][1] in cibles: p1 += 1
        if any(p in cibles for _, p in o[:3]): p3 += 1
    return p1 / len(etiq), p3 / len(etiq)

print(f"{'classement':34}{'P@1':>8}{'P@3':>8}")
b1, b3 = score(lambda o: o);      print(f"{'BM25 seul (témoin)':34}{b1:8.3f}{b3:8.3f}")
v1, v3 = score(v0);               print(f"{'V0 actuel (production)':34}{v1:8.3f}{v3:8.3f}   "
                                        f"{'⛔' if v1 < b1 else '='} P@1 {v1-b1:+.3f}")
for eps in (0.02, 0.05, 0.10, 0.20):
    t1, t3 = score(lambda o, e=eps: tb(o, e))
    n_fire = sum(1 for _, q, _ in etiq
                 if (lambda o: len([x for x in o if x[0] >= o[0][0]*(1-eps)]) > 1 if o else False)(bm25(q)))
    print(f"{'tie-break eps=' + f'{eps:.0%}':34}{t1:8.3f}{t3:8.3f}   P@1 {t1-b1:+.3f} · "
          f"s'active sur {n_fire}/{len(etiq)} cas")
