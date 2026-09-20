#!/usr/bin/env python3
"""
banc_a87_contre_epreuve.py — A8.7 : que COÛTERAIT le retrait du bonus d'utilité ?

A8.6 a montré ce que le bonus rapporte : rien de démontré, et −0,125 de P@1. Avant d'en
conclure qu'il faut le retirer, il faut la contre-épreuve : **le retrait fait-il perdre une
capacité qu'ADR-0003 avait réellement apportée ?**

⚠️ RÈGLE DE MESURE (l'auteur, 2026-08-20) : la simple PRÉSENCE d'une fiche à historique dans le
top-k n'est PAS un bénéfice. La question est « obtient-on une meilleure réponse ? », pas
« voit-on davantage de fiches déjà consultées ? ».

Quatre mesures, α = 0,2 (production) contre α = 0 (retrait) :
  1. FIDÉLITÉ      — reproduire l'instrument ORIGINAL d'ADR-0003 (part du top-3 occupée par
                     de l'historique). Si l'effet qu'elle décrit n'existe plus, on ne mesure
                     pas la même chose qu'elle.
  2. JUSTESSE      — P@1 / P@3 / MRR sur les 40 cas étiquetés, avec ET sans le créneau
                     d'exploration d'ADR-0004, puis le détail cas par cas et sa DIRECTION.
  3. DISPONIBILITÉ — une fiche à historique devient-elle INTROUVABLE sans le bonus ?
  4. CONTRÔLE POSITIF construit en A8 (3 fiches réellement utiles, interrogées par leur
                     titre). ⚠️ Ce contrôle est de MOI, pas d'ADR-0003 — voir le rapport.

Lecture seule. Ne modifie ni brain_recall.py, ni config/, ni state/, ni _baseline, ni une fiche.

  python3 tests/banc_a87_contre_epreuve.py
"""
import json, math, os, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br

UTIL = json.load(open(os.path.join(BRAIN, "state", "recall-utilite.json"), encoding="utf-8"))
hits = lambda p: UTIL.get(p, {}).get("hit", 0)
sugg = lambda p: UTIL.get(p, {}).get("sugg", 0)
CFG_EX = br.config()["exploration"]

docs = br.load_corpus(); moteur = br.BM25(docs)
par_stem = {}
for d in docs: par_stem.setdefault(os.path.basename(d["path"])[:-3], d["path"])
titre = {d["path"]: (d.get("title") or d["name"]).replace("-", " ") for d in docs}

def bruts(q):
    tk = br.tokenize(q); o = []
    for i, d in enumerate(moteur.docs):
        s = sum(moteur._contrib(i, t) for t in tk)
        if s > 0: o.append((s, d["path"]))
    o.sort(key=lambda x: -x[0]); return o

def classer(o, alpha, k=5, exploration=False):
    aj = sorted(((s * (1 + alpha * math.log(1 + hits(p))), p) for s, p in o), key=lambda x: -x[0])
    if not exploration: return aj[:k]
    n_ex = k // int(CFG_EX["denominateur"]); seuil = CFG_EX["seuil_peu_proposee"]
    ret = aj[:k - n_ex]; deja = {p for _, p in ret}
    for r in [x for x in aj[k - n_ex:] if x[1] not in deja and sugg(x[1]) < seuil][:n_ex]:
        ret.append(r); deja.add(r[1])
    for r in aj[k - n_ex:]:
        if len(ret) >= k: break
        if r[1] not in deja: ret.append(r); deja.add(r[1])
    return ret

# ── les 40 cas étiquetés ────────────────────────────────────────────────────
etiq = []
for c in json.load(open(os.path.join(ICI, "golden_recall.json"), encoding="utf-8"))["cas"]:
    etiq.append((c["id"], c["query"], set(c["attendu"])))
for i, c in enumerate(json.load(open(os.path.join(ICI, "banc-retrieval", "cas.json"), encoding="utf-8"))):
    if c["t"] is None: continue
    st = c["t"] if isinstance(c["t"], list) else [c["t"]]
    ci = {par_stem[s] for s in st if s in par_stem}
    if ci: etiq.append((f"r{i:02d}-{st[0][:18]}", c["q"], ci))
print(f"corpus {len(docs)} fiches · {len(etiq)} cas étiquetés · "
      f"{sum(1 for d in docs if hits(d['path']))} fiches porteuses d'historique\n")

# ── 1 · FIDÉLITÉ : l'instrument ORIGINAL d'ADR-0003 ─────────────────────────
print("── 1 · FIDÉLITÉ — l'instrument d'ADR-0003 : part du top-3 occupée par de l'historique ──\n")
for alpha in (0.0, 0.2, 0.5, 1.0):
    n = tot = 0
    for _, q, _ in etiq:
        top = classer(bruts(q), alpha, k=3)
        n += sum(1 for _, p in top if hits(p) > 0); tot += len(top)
    print(f"   alpha = {alpha:<4} → {n:3d}/{tot}  ({100*n/tot:4.1f} %)")
print("\n   ADR-0003 mesurait 3/30 à alpha=0 et 8/30 à alpha=0,2 sur 10 requêtes.")
print("   L'effet qu'elle décrit EXISTE toujours — mais il mesure la PRÉSENCE, pas la justesse.")

# ── 2 · JUSTESSE ────────────────────────────────────────────────────────────
def justesse(alpha, exploration):
    p1 = p3 = 0; rr = 0.0
    for _, q, cibles in etiq:
        top = classer(bruts(q), alpha, k=5, exploration=exploration)
        if not top: continue
        if top[0][1] in cibles: p1 += 1
        if any(p in cibles for _, p in top[:3]): p3 += 1
        for i, (_, p) in enumerate(top, 1):
            if p in cibles: rr += 1 / i; break
    n = len(etiq); return p1 / n, p3 / n, rr / n

print("\n── 2 · JUSTESSE — obtient-on une MEILLEURE RÉPONSE ? ───────────────────────\n")
print(f"{'':38}{'P@1':>8}{'P@3':>8}{'MRR':>8}")
for ex in (False, True):
    lab = "avec créneau d'exploration" if ex else "facteur d'utilité seul"
    a = justesse(0.2, ex); b = justesse(0.0, ex)
    print(f"   {lab:35}")
    print(f"     alpha = 0,2 (production)          {a[0]:8.3f}{a[1]:8.3f}{a[2]:8.3f}")
    print(f"     alpha = 0   (retrait)             {b[0]:8.3f}{b[1]:8.3f}{b[2]:8.3f}"
          f"   ΔP@1 {b[0]-a[0]:+.3f}  ΔMRR {b[2]-a[2]:+.3f}")

print("\n   Détail cas par cas — que change EXACTEMENT le retrait ?\n")
gagne, perd, neutre = [], [], []
for cid, q, cibles in etiq:
    o = bruts(q)
    t02, t00 = classer(o, 0.2, k=5), classer(o, 0.0, k=5)
    if not t02 or not t00: continue
    b02, b00 = t02[0][1] in cibles, t00[0][1] in cibles
    if b00 and not b02: gagne.append((cid, os.path.basename(t02[0][1]), os.path.basename(t00[0][1])))
    elif b02 and not b00: perd.append((cid, os.path.basename(t02[0][1]), os.path.basename(t00[0][1])))
    elif t02[0][1] != t00[0][1]: neutre.append(cid)
print(f"   rang 1 devenu JUSTE grâce au retrait  : {len(gagne)}")
for cid, av, ap in gagne: print(f"       {cid[:26]:28} {av[:34]:36} → {ap[:34]}")
print(f"   rang 1 devenu FAUX à cause du retrait  : {len(perd)}")
for cid, av, ap in perd: print(f"       {cid[:26]:28} {av[:34]:36} → {ap[:34]}")
print(f"   rang 1 changé sans effet sur la justesse : {len(neutre)}")

# ── 3 · DISPONIBILITÉ ───────────────────────────────────────────────────────
print("\n── 3 · DISPONIBILITÉ — une fiche à historique devient-elle INTROUVABLE ? ───\n")
porteuses = [d["path"] for d in docs if hits(d["path"]) > 0]
def rang(p, alpha):
    for i, (_, x) in enumerate(classer(bruts(titre[p]), alpha, k=20), 1):
        if x == p: return i
    return 999
sorties, chutes = [], []
for p in porteuses:
    r02, r00 = rang(p, 0.2), rang(p, 0.0)
    if r02 <= 5 < r00: sorties.append((p, r02, r00))
    elif r00 > r02: chutes.append((p, r02, r00))
print(f"   fiches porteuses d'historique testées par leur propre titre : {len(porteuses)}")
print(f"     SORTENT du top-5 sans le bonus : {len(sorties)}")
for p, a, b in sorties[:10]: print(f"        rang {a} → {b}   {p}")
print(f"     reculent sans sortir du top-5  : {len(chutes)}")
for p, a, b in chutes[:6]: print(f"        rang {a} → {b}   {os.path.basename(p)}")

# ── 4 · CONTRÔLE POSITIF construit en A8 ────────────────────────────────────
print("\n── 4 · CONTRÔLE POSITIF (construit en A8, PAS par ADR-0003) ────────────────\n")
CP = ["life/mission-locale-rapport-hebdo.md",
      "projects/mconfidential/mconfidential-edl-cadrage-2026-08-11.md",
      "projects/claude-brain/c-brain-traduction-main-reprise-2026-08-13.md"]
rouge = False
for p in CP:
    if p not in titre: print(f"   absente du corpus : {p}"); continue
    r02, r00 = rang(p, 0.2), rang(p, 0.0)
    ok = r00 <= r02 or r00 == 1
    rouge |= not ok
    print(f"   rang {r02} → {r00}   {'✅' if ok else '⛔ PERD SON RANG'}   {os.path.basename(p)}")
print(f"\n   → contrôle positif sous retrait : {'⛔ ROUGE' if rouge else '✅ VERT'}")

# ── 5 · CARACTÉRISER la capacité perdue : où le bonus agit-il réellement ? ──
print("\n── 5 · OÙ le bonus agit-il ? écart lexical rang1↔cible au moment où il tranche ──\n")
def ecart_au_point_de_bascule(p):
    o = bruts(titre[p])
    if not o: return None
    smax = o[0][0]; s = dict((x[1], x[0]) for x in o).get(p)
    return None if s is None else (smax - s) / smax

for lab, grp in (("fiches SORTIES du top-5 sans le bonus", [x[0] for x in sorties]),
                 ("fiches qui reculent sans sortir", [x[0] for x in chutes])):
    e = [ecart_au_point_de_bascule(p) for p in grp]
    e = [x for x in e if x is not None]
    if e:
        print(f"   {lab:44} n={len(e):2d}  écart lexical méd {sorted(e)[len(e)//2]:6.1%}  "
              f"[{min(e):.1%} – {max(e):.1%}]")
print("\n   → à comparer aux 5 rangs 1 que le bonus CASSE sur les cas étiquetés,")
print("     dont les écarts lexicaux vont de 5,3 % à 26,2 % (A8.4/A8.5).")

# ── 6 · la capacité perdue survit-elle à un TIE-BREAK strict ? ──────────────
print("\n── 6 · La capacité perdue est-elle récupérable SANS le bonus multiplicatif ? ──")
print("   (caractérisation, PAS une proposition de V6)\n")
def tb(o, eps):
    if not o: return o
    smax = o[0][0]
    proche = sorted([x for x in o if x[0] >= smax*(1-eps)], key=lambda x: (-hits(x[1]), -x[0]))
    return proche + [x for x in o if x[0] < smax*(1-eps)]
def justesse_tb(eps):
    p1 = 0
    for _, q, cibles in etiq:
        t = tb(bruts(q), eps)
        if t and t[0][1] in cibles: p1 += 1
    return p1/len(etiq)
def rang_tb(p, eps):
    for i, (_, x) in enumerate(tb(bruts(titre[p]), eps)[:20], 1):
        if x == p: return i
    return 999
print(f"{'':22}{'P@1 étiqueté':>14}{'sorties top-5':>15}{'contrôle positif':>19}")
r_ref = {p: rang(p, 0.2) for p in porteuses}
for eps in (0.0, 0.02, 0.05, 0.10):
    s = sum(1 for p in porteuses if r_ref[p] <= 5 < rang_tb(p, eps))
    cp = sum(1 for p in CP if p in titre and rang_tb(p, eps) <= rang(p, 0.2))
    print(f"   tie-break eps={eps:<5.0%}{justesse_tb(eps):14.3f}{s:15d}{f'{cp}/3 tenus':>19}")
print(f"   {'alpha=0,2 (production)':19}{justesse(0.2, False)[0]:14.3f}{0:15d}{'3/3 tenus':>19}")
print(f"   {'alpha=0 (retrait sec)':19}{justesse(0.0, False)[0]:14.3f}{len(sorties):15d}{'1/3 tenus':>19}")
