#!/usr/bin/env python3
"""
banc_a8_utilite.py — SIMULATION HORS PRODUCTION des variantes du signal d'utilité (A8).

Ne modifie RIEN : ni brain_recall.py, ni state/, ni _baseline, ni une fiche.
Rejoue le classement en réutilisant le BM25 du moteur (`_contrib`) et sa logique
d'exploration, en ne remplaçant QUE le calcul du facteur d'utilité.

⚠️ DEPUIS M5 (installé le 2026-09-19, ADR-0018), LA PRODUCTION N'APPLIQUE PLUS
AUCUN FACTEUR : le score servi est le score lexical seul, et l'usage n'est plus
qu'une annotation. Ce banc est donc devenu un CONTREFACTUEL — « qu'arriverait-il
si on remettait un bonus, et sous quelle formule ». La colonne `V0` s'appelait
« actuelle (témoin) » : c'était vrai avant M5, et faux après. Un banc qui annonce
un état de production périmé est le même défaut que la carte qui annonçait un
sens qu'elle n'avait pas (C bis A7) — corrigé ici le 2026-09-19 en ajoutant la
variante que la production implémente vraiment, et en la plaçant EN TÊTE comme
référence de comparaison.

Le garde-fou vivant, lui, est `tests/utilite_hors_rang.py` : il joue de VRAIES
requêtes sur le moteur de production, fausse les compteurs, et vérifie que
l'ordre servi ne bouge pas — avec sa contre-épreuve, qui montre que l'ancienne
règle, elle, en aurait bougé 24 sur 24.

  python3 tests/banc_a8_utilite.py
"""
import collections, json, math, os, pathlib, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br
import recall_feedback as rf

# ─── provenance des hits, par fiche ───────────────────────────────────────────
def provenance():
    proj = pathlib.Path.home()/".claude/projects"
    kind = {}
    for d in proj.iterdir():
        if not d.is_dir(): continue
        k = "agent" if d.name == "-Users-mac-claude-brain" else ("humain" if d.name == "-Users-mac" else "autre")
        for f in d.glob("*.jsonl"): kind[f.stem] = k
    sugg, prem = collections.defaultdict(set), {}
    for d in rf._lire("recall_log.jsonl"):
        sugg[d["path"]].add(d["sid"]); c = (d["path"], d["sid"])
        if c not in prem or d["ts"] < prem[c]: prem[c] = d["ts"]
    lec = collections.defaultdict(list)
    for d in rf._lire("read_log.jsonl"): lec[(d["path"], d["sid"])].append(d["ts"])
    # ⚠️ L'ORIGINE SE DÉDUIT D'UN FICHIER QUI PEUT NE PLUS EXISTER. `kind` est bâti en
    # listant les transcripts encore sur le disque ; une session archivée ou effacée n'y
    # est plus, et `kind.get(sid)` rend None. L'ancienne version faisait alors `h += False`
    # et `a += False` : le hit disparaissait des DEUX colonnes ET du total, sans un mot,
    # alors que la même session comptait toujours dans `sugg`. Mesuré le 2026-09-19 :
    # 4777 suggestions sur 7195 et 1447 lectures sur 2473 viennent de sessions inconnues,
    # soit les DEUX TIERS de l'historique. Le « 1 seul hit humain » qu'on lisait était donc
    # un artefact de comptage, pas un fait d'usage. Un troisième seau, `hit_i`, les garde
    # visibles : ne pas savoir qui a lu n'est pas la même chose que personne n'a lu.
    out = {}
    for ch, sids in sugg.items():
        h = a = i = 0
        for sid in sids:
            if any(t >= prem[(ch, sid)] - rf.TOLERANCE_S for t in lec.get((ch, sid), ())):
                k = kind.get(sid)
                h += (k == "humain"); a += (k == "agent"); i += (k is None)
        out[ch] = {"hit": h + a + i, "hit_h": h, "hit_a": a, "hit_i": i, "sugg": len(sids)}
    return out

PROV = provenance()
def P(path, champ, defaut=0): return PROV.get(path, {}).get(champ, defaut)

# ─── les six variantes : path -> facteur multiplicatif ────────────────────────
A = 0.2
def V0(p):  return 1 + A * math.log(1 + P(p, "hit"))                    # témoin, production
def V1(p):  return 1 + A * math.log(1 + P(p, "hit_h"))                  # hits humains seuls
def V2(p):  return 1 + 0.05 * math.log(1 + P(p, "hit"))                 # alpha réduit 0.2 -> 0.05
def V3(p):                                                              # normalisé par sugg
    h, s = P(p, "hit"), P(p, "sugg")
    return 1 + A * math.log(1 + h) * (h / s if s else 0)
def V4(p):                                                              # provenance + normalisation
    h, s = P(p, "hit_h"), P(p, "sugg")
    return 1 + A * math.log(1 + h) * (h / s if s else 0)
def V5(p):  return min(V0(p), 1.10)                                     # bonus plafonné à +10 %
def M5(p):  return 1.0                                                  # ce que la PRODUCTION fait depuis le 19/09
# M5 EN TÊTE : c'est la référence réelle. Les colonnes « mieux / pire » se lisent
# contre ce que le produit sert aujourd'hui, pas contre une règle retirée.
VARIANTES = [("M5 production (aucun)", M5), ("V0 ancienne règle", V0), ("V1 hits humains", V1),
             ("V2 alpha 0.05", V2), ("V3 normalisé /sugg", V3), ("V4 humain+normalisé", V4),
             ("V5 plafond +10%", V5)]
REFERENCE = VARIANTES[0][0]

# ─── rejouer le classement, logique du moteur, facteur remplacé ───────────────
docs = br.load_corpus(); moteur = br.BM25(docs)
cfg_ex = br.config()["exploration"]

def bm25_bruts(query):
    q = br.tokenize(query); out = []
    for i, d in enumerate(moteur.docs):
        s = sum(moteur._contrib(i, t) for t in q)
        if s > 0: out.append((s, d))
    return out

def classement(bruts, fac, k=5):
    aj = [{"path": d["path"], "bm25": s, "score": s * fac(d["path"])} for s, d in bruts]
    aj.sort(key=lambda r: r["score"], reverse=True)
    n_ex = k // int(cfg_ex["denominateur"]); seuil = cfg_ex["seuil_peu_proposee"]
    ret = aj[:k - n_ex]; deja = {r["path"] for r in ret}
    for r in [x for x in aj[k - n_ex:] if x["path"] not in deja and P(x["path"], "sugg") < seuil][:n_ex]:
        ret.append(r); deja.add(r["path"])
    for r in aj[k - n_ex:]:
        if len(ret) >= k: break
        if r["path"] not in deja: ret.append(r); deja.add(r["path"])
    return ret[:k], aj

def rang(ret, cibles):
    for i, r in enumerate(ret, 1):
        if r["path"] in cibles: return i
    return None

# ─── les cas ──────────────────────────────────────────────────────────────────
g = json.load(open(os.path.join(ICI, "golden_recall.json")))
CAS = [{"id": c["id"], "q": c["query"], "t": set(c["attendu"]), "src": "golden"} for c in g["cas"]]
for c in json.load(open(os.path.join(ICI, "banc-retrieval/cas.json"))):
    t = {p["path"] for p in docs if p["name"] == c["t"]}
    if t: CAS.append({"id": c["c"][:22], "q": c["q"], "t": t, "src": "retrieval"})

BRUTS = {c["id"]: bm25_bruts(c["q"]) for c in CAS}

# ─── cas FRAGILES : issue décidée par une quasi-égalité ───────────────────────
print(f"BANC A8 — {len(CAS)} cas ({sum(1 for c in CAS if c['src']=='golden')} golden + "
      f"{sum(1 for c in CAS if c['src']=='retrieval')} retrieval) · corpus {len(docs)} docs\n")
print("── CAS FRAGILES (écart rang1↔rang2 < 1 % sous V0) — une variation de P@1 n'y prouve rien")
fragiles = set()
for c in CAS:
    ret, _ = classement(BRUTS[c["id"]], V0)
    if len(ret) >= 2 and ret[0]["score"] > 0:
        ecart = (ret[0]["score"] - ret[1]["score"]) / ret[0]["score"]
        if ecart < 0.01:
            fragiles.add(c["id"]); print(f"   {c['id']:24} écart {100*ecart:5.2f} %  ({ret[0]['score']:.2f} vs {ret[1]['score']:.2f})")
print(f"   → {len(fragiles)} cas fragiles sur {len(CAS)}\n")

# ─── contrôle positif : l'historique DOIT rester payant ───────────────────────
SEUIL_H, SEUIL_TAUX = 3, 0.20
UTILES = [p for p in PROV if PROV[p]["hit_h"] >= SEUIL_H and PROV[p]["sugg"] and PROV[p]["hit"]/PROV[p]["sugg"] >= SEUIL_TAUX]
print(f"── CONTRÔLE POSITIF — {len(UTILES)} fiche(s) réellement utiles (hits humains >= {SEUIL_H} ET taux >= {SEUIL_TAUX:.0%})")
for p in UTILES: print(f"   {PROV[p]['hit_h']}h/{PROV[p]['hit']}hits sur {PROV[p]['sugg']} sugg  {p}")
if not UTILES:
    # UN CONTRÔLE SANS MATIÈRE N'EST PAS UN CONTRÔLE QUI PASSE. Il imprimait six
    # lignes vides et la phrase « une variante qui fait sortir une de ces fiches
    # est rejetée » — sur zéro fiche, donc rien n'était rejetable. Il dit
    # désormais POURQUOI il est vide, avec le chiffre qui le montre.
    max_h = max((v["hit_h"] for v in PROV.values()), default=0)
    tot_h = sum(v["hit_h"] for v in PROV.values())
    tot_a = sum(v["hit_a"] for v in PROV.values())
    tot_i = sum(v["hit_i"] for v in PROV.values())
    print(f"   ⚠️  CONTRÔLE SANS MATIÈRE — aucune fiche n'atteint le seuil : le maximum de hits")
    print(f"       humains sur tout le corpus est {max_h}, pour {tot_h} hit(s) humain(s) au total,")
    print(f"       {tot_a} venus d'agents et {tot_i} d'ORIGINE INCONNUE, sur {len(PROV)} fiches suivies.")
    print(f"       Ce dernier chiffre est le vrai obstacle : l'origine se déduit d'un transcript")
    print(f"       encore présent sur le disque, et il a disparu pour les deux tiers de")
    print(f"       l'historique. On ne peut donc PAS trancher « une lecture d'agent vaut-elle une")
    print(f"       consultation humaine » avec cet instrument. Ce n'est PAS un contrôle réussi.")
print()

# ─── comparaison ──────────────────────────────────────────────────────────────
base = {}
print(f"{'variante':22} {'P@1':>6} {'P@3':>6} {'MRR':>6} {'q13':>5} {'q17':>5} {'mieux':>6} {'pire':>5} {'util.moy':>9}")
resultats = {}
for nom, fac in VARIANTES:
    rangs, p1 = {}, 0
    for c in CAS:
        ret, _ = classement(BRUTS[c["id"]], fac)
        rangs[c["id"]] = rang(ret, c["t"])
    n = len(CAS)
    p1 = sum(1 for r in rangs.values() if r == 1) / n
    p3 = sum(1 for r in rangs.values() if r and r <= 3) / n
    mrr = sum(1/r for r in rangs.values() if r) / n
    if not base: base = dict(rangs)
    mieux = sum(1 for k, v in rangs.items() if (v or 99) < (base[k] or 99))
    pire  = sum(1 for k, v in rangs.items() if (v or 99) > (base[k] or 99))
    umoy = sum(fac(p) for p in UTILES)/len(UTILES) if UTILES else None
    q13 = rangs.get("q13-timeline-bm25"); q17 = rangs.get("q17-ci-lint")
    resultats[nom] = (rangs, p1, p3, mrr, mieux, pire, umoy)
    # `nan` ne dit pas « pas mesurable », il dit « quelque chose a raté » : on écrit le tiret.
    print(f"{nom:22} {p1:6.3f} {p3:6.3f} {mrr:6.3f} {str(q13):>5} {str(q17):>5} {mieux:6d} {pire:5d}"
          f"{(f'{umoy:9.4f}' if umoy is not None else '        —')}")

print("\n── DÉTAIL DES RÉGRESSIONS (hors cas fragiles)")
for nom, (rangs, *_ ) in resultats.items():
    if nom == REFERENCE: continue
    reg = [k for k, v in rangs.items() if (v or 99) > (base[k] or 99) and k not in fragiles]
    gag = [k for k, v in rangs.items() if (v or 99) < (base[k] or 99) and k not in fragiles]
    print(f"   {nom:22} gagne {len(gag)} : {', '.join(gag[:4]) or '—'}")
    print(f"   {'':22} perd  {len(reg)} : {', '.join(reg[:4]) or '—'}")

# ─── métriques SÉPARÉES + contrôle positif par RANG RÉEL ──────────────────────
print("\n" + "="*78)
print("MÉTRIQUES SÉPARÉES (mélanger golden et retrieval écrase les deux)\n")
for src in ("golden", "retrieval"):
    sub = [c for c in CAS if c["src"] == src]
    print(f"── {src} ({len(sub)} cas)")
    print(f"   {'variante':22} {'P@1':>6} {'P@3':>6} {'MRR':>6}")
    for nom, fac in VARIANTES:
        rangs = {}
        for c in sub:
            ret, _ = classement(BRUTS[c["id"]], fac)
            rangs[c["id"]] = rang(ret, c["t"])
        n = len(sub)
        print(f"   {nom:22} {sum(1 for r in rangs.values() if r==1)/n:6.3f} "
              f"{sum(1 for r in rangs.values() if r and r<=3)/n:6.3f} "
              f"{sum(1/r for r in rangs.values() if r)/n:6.3f}")
    print()

print("="*78)
print("CONTRÔLE POSITIF PAR RANG RÉEL — une fiche utile doit RESTER trouvable\n")
# requête construite depuis le titre de chaque fiche utile : elle DOIT sortir 1re
def titre_de(path):
    for d in docs:
        if d["path"] == path:
            return (d.get("title") or d.get("name") or "").replace("-", " ")
    return ""
sondes = [(p, titre_de(p)) for p in UTILES]
if not sondes:
    print("   ⚠️  RIEN À CONTRÔLER — aucune fiche ne passe le seuil d'utilité réelle (voir plus haut).")
    print("       Ce bloc imprimait six lignes vides suivies d'une règle de rejet : un contrôle")
    print("       qui ne peut RIEN rejeter ne protège de rien. Il se tait désormais en le disant.")
    sys.exit(0)
print(f"   {'variante':22} " + " ".join(f"{p.split('/')[-1][:14]:>15}" for p, _ in sondes))
for nom, fac in VARIANTES:
    cols = []
    for p, q in sondes:
        ret, _ = classement(bm25_bruts(q), fac)
        r = rang(ret, {p})
        cols.append(f"{('rang '+str(r)) if r else 'ABSENT':>15}")
    print(f"   {nom:22} " + " ".join(cols))
print("\n   → une variante qui fait SORTIR une de ces fiches du top-5 est rejetée")
