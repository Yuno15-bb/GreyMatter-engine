#!/usr/bin/env python3
"""
banc_a84_selection.py — A8.4 · ÉTAPE 1 : sélectionner EN AVEUGLE de nouveaux témoins
de promotion abusive (famille A).

PROTOCOLE IMPOSÉ (l'auteur, 2026-08-20) : les cas sont choisis AVANT de regarder leur nombre
de lectures hors rappel, jamais pendant. Sans quoi on choisit les témoins qui confirment
l'hypothèse. Ce script est donc AVEUGLE PAR CONSTRUCTION : il ne lit jamais read_log.jsonl
autrement qu'à travers le compteur `hit` déjà utilisé par la production, et n'a aucune
notion de « lecture hors rappel ». Sa sortie est gelée et commitée avant l'étape 2.

DÉFINITION D'UNE PROMOTION ABUSIVE, sans jeu de données à inventer :
  requête   = le titre de la fiche T (une fiche est la meilleure réponse à son propre titre)
  condition = T est 1re sur le BM25 seul, et perd le rang 1 au profit de F
              UNIQUEMENT à cause du facteur d'utilité de F.
  franchise = l'écart lexical BM25(T) − BM25(F) doit dépasser MARGE_MIN, pour ne pas
              rejouer l'erreur de q13/q17 (témoins à 0,23 % et 0,11 % : l'issue y tient au
              tie-break, pas à la qualité).

BIAIS CONNU, ET IL EST CONSERVATEUR : les F sélectionnés ont beaucoup de hits, donc
beaucoup de suggestions, et ρ(sugg, hors rappel) = +0,36 — la sélection favorise donc des
fiches qui ont PLUS de lectures hors rappel. Si l'hypothèse survit, ce sera contre ce biais.

  python3 tests/banc_a84_selection.py            (écrit tests/a84_temoins.json)
"""
import collections, json, math, os, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br
import recall_feedback as rf

MARGE_MIN = 0.05          # 5 % d'écart lexical : franc, pas un tie-break
ALPHA = 0.2               # celui de la production (ADR-0003), non modifié

# ── le compteur d'utilité de la PRODUCTION, rien d'autre ─────────────────────
UTIL = json.load(open(os.path.join(BRAIN, "state", "recall-utilite.json"), encoding="utf-8"))
def hits(p):  return UTIL.get(p, {}).get("hit", 0)
def sugg(p):  return UTIL.get(p, {}).get("sugg", 0)
def facteur(p): return 1 + ALPHA * math.log(1 + hits(p))

docs = br.load_corpus(); moteur = br.BM25(docs)
titre = {d["path"]: (d.get("title") or d["name"]).replace("-", " ") for d in docs}
print(f"corpus {len(docs)} fiches · {sum(1 for d in docs if hits(d['path']))} avec ≥1 hit\n")

cas = []
for d in docs:
    T = d["path"]
    q = br.tokenize(titre[T])
    if len(q) < 2: continue
    bruts = []
    for i, dd in enumerate(moteur.docs):
        s = sum(moteur._contrib(i, t) for t in q)
        if s > 0: bruts.append((s, dd["path"]))
    if not bruts: continue
    bruts.sort(key=lambda x: -x[0])
    if bruts[0][1] != T: continue                       # T n'est pas la meilleure réponse lexicale
    bm_T = bruts[0][0]
    avec = sorted(((s * facteur(p), s, p) for s, p in bruts), key=lambda x: -x[0])
    if avec[0][2] == T: continue                        # rien n'a été inversé
    sc_F, bm_F, F = avec[0]
    if hits(F) == 0: continue                           # inversion non due au bonus
    marge = (bm_T - bm_F) / bm_T
    if marge < MARGE_MIN: continue                      # trop serré : tie-break, pas qualité
    cas.append(dict(victime=T, promue=F, bm25_victime=round(bm_T, 2), bm25_promue=round(bm_F, 2),
                    marge_lexicale=round(marge, 4), hit_promue=hits(F), sugg_promue=sugg(F),
                    facteur_promue=round(facteur(F), 4)))

cas.sort(key=lambda c: -c["marge_lexicale"])
famille_A = sorted({c["promue"] for c in cas})
print(f"── PROMOTIONS ABUSIVES FRANCHES (marge lexicale ≥ {MARGE_MIN:.0%}) : {len(cas)} cas ──\n")
print(f"{'marge':>7} {'bm25 T':>7} {'bm25 F':>7} {'hit F':>6} {'sugg F':>7}   fiche PROMUE  ←  victime")
for c in cas[:25]:
    print(f"{c['marge_lexicale']:7.1%} {c['bm25_victime']:7.2f} {c['bm25_promue']:7.2f} "
          f"{c['hit_promue']:6d} {c['sugg_promue']:7d}   {os.path.basename(c['promue'])[:40]:42} ← "
          f"{os.path.basename(c['victime'])[:34]}")
if len(cas) > 25: print(f"   … {len(cas)-25} de plus")

# ── groupe de CONTRÔLE APPARIÉ sur le nombre de hits ─────────────────────────
# Sinon « la famille A a peu de lectures hors rappel » pourrait n'être qu'une propriété
# de toutes les fiches à fort nombre de hits.
besoin = collections.Counter(hits(p) for p in famille_A)
candidats = collections.defaultdict(list)
for d in docs:
    p = d["path"]
    if p in famille_A or hits(p) == 0: continue
    candidats[hits(p)].append(p)
controle = []
for h, n in sorted(besoin.items()):
    dispo = sorted(candidats.get(h, []))
    controle += dispo[:max(n, 3)]
print(f"\n── FAMILLE A retenue : {len(famille_A)} fiches distinctes ──")
for p in famille_A: print(f"   hit={hits(p):3d} sugg={sugg(p):4d}   {p}")
print(f"\n── CONTRÔLE APPARIÉ (même nombre de hits, aucune promotion abusive) : {len(controle)} ──")
for p in controle[:12]: print(f"   hit={hits(p):3d} sugg={sugg(p):4d}   {p}")
if len(controle) > 12: print(f"   … {len(controle)-12} de plus")

sortie = dict(protocole="selection AVEUGLE — aucune lecture hors rappel consultee",
              marge_min=MARGE_MIN, alpha=ALPHA, corpus=len(docs),
              famille_A=famille_A, controle_apparie=controle, cas=cas)
chemin = os.path.join(ICI, "a84_temoins.json")
json.dump(sortie, open(chemin, "w"), ensure_ascii=False, indent=1)
print(f"\n→ gelé dans {os.path.relpath(chemin, BRAIN)} — à commiter AVANT l'étape 2.")
