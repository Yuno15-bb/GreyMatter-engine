#!/usr/bin/env python3
"""
banc_a84_revelation.py — A8.4 · ÉTAPE 2 : révéler les lectures hors rappel des témoins
sélectionnés EN AVEUGLE à l'étape 1 (tests/a84_temoins.json, gelé et commité avant).

Aucun seuil n'est choisi après coup : la grille entière est rapportée. Si l'observable ne
tient qu'à un seuil trié sur le volet, il n'est pas prouvé — et ce script le dira.

Trois propriétés exigées avant de promouvoir l'observable (l'auteur, 2026-08-20) :
  1. séparation des témoins        — ici
  2. non-redondance avec la popularité — banc_a83_hors_rappel.py, ρ = +0,36
  3. utilité prédictive / causale  — validation prédictive P1→P2, encore faible

  python3 tests/banc_a84_revelation.py
"""
import collections, json, math, os, random, statistics, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import recall_feedback as rf

GEL = json.load(open(os.path.join(ICI, "a84_temoins.json"), encoding="utf-8"))

# ── l'observable A8.3, recalculé ici (mêmes règles que banc_a83) ─────────────
sugg, prem = collections.defaultdict(set), {}
for d in rf._lire("recall_log.jsonl"):
    sugg[d["path"]].add(d["sid"]); c = (d["path"], d["sid"])
    if c not in prem or d["ts"] < prem[c]: prem[c] = d["ts"]
lec = collections.defaultdict(list)
for d in rf._lire("read_log.jsonl"): lec[(d["path"], d["sid"])].append(d["ts"])
S_read = {sid for (_, sid) in lec}

def hors_rappel(p):
    n = 0
    for (pp, sid), ts in lec.items():
        if pp != p: continue
        b = prem.get((p, sid))
        if b is None or any(t < b - rf.TOLERANCE_S for t in ts): n += 1
    return n
def occasions(p): return len(S_read - (sugg.get(p, set()) & S_read))

CONTROLE = GEL["controle_apparie"]
def perm(a, b, n=20000):
    """différence de médianes, test de permutation — petit n, pas de loi supposée"""
    obs = statistics.median(b) - statistics.median(a)
    tout = a + b; rng = random.Random(20260820); c = 0
    for _ in range(n):
        rng.shuffle(tout)
        if statistics.median(tout[len(a):]) - statistics.median(tout[:len(a)]) >= obs: c += 1
    return obs, (c + 1) / (n + 1)

print("RÉVÉLATION — lectures hors rappel des fiches sélectionnées en aveugle\n")
print(f"{'seuil':>6} {'n famille A':>12} {'hors rappel A':>26} {'contrôle apparié':>22} {'p':>8}")
print("-" * 80)
lignes = []
for s in (0.05, 0.08, 0.10, 0.15, 0.20):
    fam = sorted({c["promue"] for c in GEL["cas"] if c["marge_lexicale"] >= s})
    if not fam: continue
    a = [hors_rappel(p) for p in fam]; b = [hors_rappel(p) for p in CONTROLE]
    _, p = perm(a, b)
    lignes.append((s, fam, a, b, p))
    print(f"{s:6.0%} {len(fam):12d}   méd {statistics.median(a):5.1f}  [{min(a)}–{max(a)}]"
          f"      méd {statistics.median(b):5.1f}  [{min(b)}–{max(b)}]   {p:8.4f}")

print("\n── Détail au seuil le plus permissif (toutes les fiches retenues) ──")
s, fam, a, b, p = lignes[0]
for pth in sorted(fam, key=lambda x: hors_rappel(x)):
    marge = max(c["marge_lexicale"] for c in GEL["cas"] if c["promue"] == pth)
    print(f"   hors rappel {hors_rappel(pth):3d} / {occasions(pth):3d} occas. · "
          f"marge max {marge:5.1%} · {os.path.basename(pth)[:46]}")

print("\n── VERDICT ─────────────────────────────────────────────────────────────")
zero = [p_ for p_ in fam if hors_rappel(p_) == 0]
print(f"  fiches à 0 lecture hors rappel dans la famille A : {len(zero)}/{len(fam)}")
for z in zero: print(f"       {z}")
sig = [s_ for s_, f_, a_, b_, p_ in lignes if p_ < 0.05]
print(f"  seuils où la famille A est significativement sous le contrôle : "
      f"{[f'{x:.0%}' for x in sig] if sig else 'AUCUN'}")
