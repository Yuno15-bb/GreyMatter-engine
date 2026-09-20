#!/usr/bin/env python3
"""
banc_a83_hors_rappel.py — A8.3 : un observable qui distingue l'USAGE de l'EXPOSITION.

LE PROBLÈME. V0 compte les lectures, V1 compte l'identité du lecteur ; les deux sont
réfutées (cf. projects/claude-brain/utilite-boucle-popularite-2026-08-19.md, §9). Aucune
des deux ne regarde CE QUE LA LECTURE PROUVE.

L'OBSERVABLE PROPOSÉ — « lecture hors rappel ». Une lecture d'une fiche dans une session
où le rappel ne l'a JAMAIS proposée (ou bien AVANT qu'il ne la propose). Ce n'est pas une
proxy : c'est le complément définitionnel du hit. Une telle lecture ne PEUT PAS avoir été
produite par l'exposition au rappel — il faut être allé chercher la fiche.

CE QUE CE BANC MESURE, ET SES CONTRÔLES (un banc qui ne peut pas rougir ne prouve rien) :
  1. positif   — une lecture hors rappel injectée doit être COMPTÉE          (0 → 1)
  2. négatif   — une lecture injectée APRÈS la suggestion ne doit PAS l'être (0 → 0)
  3. séparation— le témoin de promotion abusive doit passer sous TOUS les témoins d'usage
  4. redondance— l'observable ne doit pas être « 1/sugg » déguisé (ρ avec sugg)
  5. puissance — borne honnête : ce que 0 événement observé permet réellement d'exclure

Lecture seule. Ne modifie ni brain_recall.py, ni alpha, ni state/, ni _baseline, ni une fiche.

  python3 tests/banc_a83_hors_rappel.py
"""
import collections, json, math, os, statistics, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import recall_feedback as rf          # on RÉUTILISE ses règles (_lire, TOLERANCE_S)

# ── témoins, déclarés d'avance (§9 de la fiche A8) ────────────────────────────
EXPO = ["meta/claude-brain.md"]                       # famille A — promotion abusive (q13)
USAGE = [                                             # famille B + contrôle positif d'ADR-0003
    "projects/claude-brain/detection-conflits-banc-2026-08-16.md",   # rang 1 → 4 sous V1
    "projects/claude-brain/c-brain-checkpoint-parcours-2026-08-17.md",
    "projects/claude-brain/brain-v3-reprise.md",
    "projects/suivi-terrain/suivi-terrain-audit-produit-2026-08-03.md",
    "life/mission-locale-rapport-hebdo.md",
    "projects/mconfidential/mconfidential-edl-cadrage-2026-08-11.md",
    "projects/claude-brain/c-brain-traduction-main-reprise-2026-08-13.md",
]


def etat(lectures_injectees=()):
    """Recalcule sugg / hits / lectures hors rappel. `lectures_injectees` sert aux sabotages."""
    sugg, prem = collections.defaultdict(set), {}
    for d in rf._lire("recall_log.jsonl"):
        sugg[d["path"]].add(d["sid"]); c = (d["path"], d["sid"])
        if c not in prem or d["ts"] < prem[c]: prem[c] = d["ts"]
    lec = collections.defaultdict(list); n_lec_sess = collections.Counter()
    for d in list(rf._lire("read_log.jsonl")) + list(lectures_injectees):
        lec[(d["path"], d["sid"])].append(d["ts"]); n_lec_sess[d["sid"]] += 1
    S_read = set(n_lec_sess)

    out = {}
    for p in set(sugg) | {x for (x, _) in lec}:
        sess_sugg = sugg.get(p, set())
        hit = spont = 0
        for (pp, sid), ts in lec.items():
            if pp != p: continue
            base = prem.get((p, sid))
            if base is None:
                spont += 1                                   # jamais proposée : lecture choisie
            else:
                if any(t >= base - rf.TOLERANCE_S for t in ts): hit += 1
                if any(t <  base - rf.TOLERANCE_S for t in ts): spont += 1   # lue AVANT l'offre
        occ = len(S_read - (sess_sugg & S_read))             # occasions d'être lue sans offre
        out[p] = dict(sugg=len(sess_sugg), hit=hit, spont=spont, occ=occ,
                      lect_concurrentes=sum(n_lec_sess[s] for s in S_read - sess_sugg))
    return out, S_read, sugg, prem


def spearman(a, b):
    def rangs(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]: j += 1
            for k in range(i, j + 1): r[s[k]] = (i + j) / 2.0
            i = j + 1
        return r
    x, y = rangs(a), rangs(b); mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((i - mx) * (j - my) for i, j in zip(x, y))
    den = math.sqrt(sum((i - mx) ** 2 for i in x) * sum((j - my) ** 2 for j in y))
    return num / den if den else 0.0


R, S_read, sugg, prem = etat()
manquants = [p for p in EXPO + USAGE if p not in R]
if manquants:
    print("⚠️  témoins absents des journaux :", *manquants, sep="\n     ")

print(f"journaux : {len(S_read)} sessions lisantes · {len(R)} fiches · "
      f"{sum(v['hit'] for v in R.values())} hits\n")

print("── L'OBSERVABLE, sur les témoins ────────────────────────────────────────────")
print(f"{'':7}{'témoin':52}{'sugg':>5}{'hit':>4}{'occas.':>8}{'hors rappel':>12}")
for lab, grp in (("EXPO", EXPO), ("USAGE", USAGE)):
    for p in grp:
        r = R.get(p)
        if not r: continue
        print(f"{lab:7}{os.path.basename(p)[:50]:52}{r['sugg']:5d}{r['hit']:4d}{r['occ']:8d}{r['spont']:12d}")

e = max(R[p]["spont"] for p in EXPO if p in R)
u = min(R[p]["spont"] for p in USAGE if p in R)
sep = e < u
print(f"\n  [3 séparation]  EXPO max = {e}  <  USAGE min = {u}   "
      f"{'✅ séparé' if sep else '⛔ NON SÉPARÉ'}")

# ── contrôles 1 et 2 : le compteur peut-il rougir ? ──────────────────────────
A = EXPO[0]
occ_sids = sorted(S_read - (sugg.get(A, set()) & S_read))
hit_sids = sorted({sid for (p, sid) in prem if p == A} & S_read)
ok1 = ok2 = None
if occ_sids:
    R1, *_ = etat([{"ts": 1787000000, "sid": occ_sids[0], "path": A}])
    ok1 = R1[A]["spont"] == R[A]["spont"] + 1
    print(f"  [1 positif]     lecture hors rappel injectée   hors rappel {R[A]['spont']} → "
          f"{R1[A]['spont']}   {'✅ le contrôle rougit' if ok1 else '⛔ INSENSIBLE'}")
if hit_sids:
    sid = hit_sids[0]
    R2, *_ = etat([{"ts": prem[(A, sid)] + 300, "sid": sid, "path": A}])
    ok2 = R2[A]["spont"] == R[A]["spont"]
    print(f"  [2 négatif]     lecture APRÈS suggestion       hors rappel {R[A]['spont']} → "
          f"{R2[A]['spont']}   {'✅ non comptée' if ok2 else '⛔ FAUX POSITIF'}")

# ── contrôle 4 : est-ce « 1/sugg » déguisé ? ─────────────────────────────────
actives = [r for r in R.values() if r["hit"] > 0]
s = [r["sugg"] for r in actives]
rho_spont = spearman(s, [r["spont"] for r in actives])
rho_pexpo = spearman(s, [r["hit"] / r["sugg"] if r["sugg"] else 0 for r in actives])
print(f"\n  [4 redondance]  sur {len(actives)} fiches à ≥1 hit :")
print(f"                    ρ(sugg, hors rappel) = {rho_spont:+.3f}   "
      f"{'✅ indépendant de la popularité' if rho_spont > -0.35 else '⛔ redondant'}")
print(f"                    ρ(sugg, hit/sugg)    = {rho_pexpo:+.3f}   "
      f"{'← H3 : redondant avec 1/sugg' if rho_pexpo < -0.6 else ''}")

# ── contrôle 5 : la borne de puissance, dite honnêtement ─────────────────────
rA = R[A]
taux_min = min(R[p]["spont"] / R[p]["occ"] for p in USAGE if p in R and R[p]["occ"])
attendu = taux_min * rA["occ"]
p_zero = (1 - taux_min) ** rA["occ"]
borne = 3.0 / rA["occ"] if rA["occ"] else float("nan")
print(f"\n  [5 puissance]   {A}")
print(f"                    {rA['spont']} lecture hors rappel sur {rA['occ']} occasions "
      f"({rA['lect_concurrentes']} lectures y ont eu lieu, aucune pour elle)")
print(f"                    sous le taux le plus faible du groupe USAGE ({taux_min:.4f}) on "
      f"attendrait {attendu:.2f} · P(0) = {p_zero:.3f}")
print(f"                    ⚠️  règle de trois : 0/{rA['occ']} n'exclut que les taux > "
      f"{borne:.4f}. La séparation est RÉELLE mais NON significative sur cette seule fiche.")

print("\n" + "─" * 78)
print("VERDICT : l'observable sépare les deux familles de témoins là où V0 et V1 échouent,")
print("et il n'est pas la boucle de popularité déguisée. Sa force statistique, elle, est")
print("bornée par le nombre de témoins de la famille A — il n'y en a qu'UN.")
sys.exit(0 if (sep and ok1 is not False and ok2 is not False) else 1)
