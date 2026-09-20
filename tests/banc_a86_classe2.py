#!/usr/bin/env python3
"""
banc_a86_classe2.py — A8.6 · ÉTAPE 1 : construire une VRAIE classe 2, en aveugle.

A8.5 a montré que l'historique ne corrige pas (14/14 des cibles ratées ont 0 hit) et qu'il
renverse à perte (−5 contre 0). Reste UNE fonction jamais mesurée : **départager plusieurs
réponses déjà légitimes**. C'est le seul terrain où ADR-0003 pourrait avoir un sens.

CE SCRIPT NE LIT JAMAIS L'HISTORIQUE. Ni hits, ni suggestions, ni read_log. Sa sortie est
gelée et commitée avant l'étape 2. Deux sources, toutes deux aveugles aux compteurs :

  NOYAU     — cas déjà annotés par un humain comme ayant DEUX fiches légitimes :
              3 cas « C7 deux fiches legitimes » du banc retrieval + 2 cas golden
              multi-cibles. Annotations faites pour d'autres raisons, avant ce chantier.
  ÉTENDU    — TENTÉ PUIS ABANDONNÉ. L'idée était d'élargir avec les cas où le rang 1 de BM25
              n'est pas la cible annotée mais lui est SÉMANTIQUEMENT ÉQUIVALENT (cosinus des
              embeddings). Le contrôle l'a disqualifiée : sur 20 000 paires TIRÉES AU HASARD,
              la médiane des cosinus est 0,871, et le seuil calibré sur les annotations (0,876)
              n'est que le 57e percentile du hasard — 43 % des paires quelconques le dépassent.
              Deux des quatre paires annotées sont aux percentiles 57 et 69, donc indiscernables
              du bruit. Ce modèle statique ne mesure pas l'équivalence sur ce corpus.
              Instrument alternatif essayé (Jaccard titre+description) : meilleur — hasard méd
              0,000 / q99 0,087, annotations aux percentiles 80 à 99,8 — mais il ne retrouve
              que 3 des 4 paires. Aucun instrument automatique ne reproduit l'annotation humaine.

CONSÉQUENCE : la classe 2 ne peut PAS être élargie automatiquement. Elle reste aux paires
annotées. C'est peu, et ce sera dit comme tel plutôt que comblé par un instrument qui ment.

  ~/.c-brain/trunk/.venv/bin/python tests/banc_a86_classe2.py
"""
import json, os, sys
import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br

docs = br.load_corpus(); moteur = br.BM25(docs)
par_stem = {}
for d in docs: par_stem.setdefault(os.path.basename(d["path"])[:-3], d["path"])

# ── embeddings : contenu seul, aucun historique ─────────────────────────────
emb = np.load(os.path.join(BRAIN, "state", "embeddings.npz"))["v"]
meta = json.load(open(os.path.join(BRAIN, "state", "embeddings.json"), encoding="utf-8"))
chemins = [m["path"] for m in meta]      # embeddings.json : liste de {path,name,desc,hash}
if len(chemins) != len(emb):
    print(f"⚠️  {len(chemins)} chemins pour {len(emb)} vecteurs — index désaligné"); sys.exit(1)
idx = {p: i for i, p in enumerate(chemins)}
N = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
def cos(a, b):
    if a not in idx or b not in idx: return None
    return float(N[idx[a]] @ N[idx[b]])

# ── les cas étiquetés ───────────────────────────────────────────────────────
cas = []
for c in json.load(open(os.path.join(ICI, "golden_recall.json"), encoding="utf-8"))["cas"]:
    cas.append((c["id"], "golden", c["query"], list(c["attendu"])))
for c in json.load(open(os.path.join(ICI, "banc-retrieval", "cas.json"), encoding="utf-8")):
    if c["t"] is None: continue
    st = c["t"] if isinstance(c["t"], list) else [c["t"]]
    ci = [par_stem[s] for s in st if s in par_stem]
    if ci: cas.append((st[0][:24], c["c"], c["q"], ci))

def classement(q):
    tk = br.tokenize(q); o = []
    for i, d in enumerate(moteur.docs):
        s = sum(moteur._contrib(i, t) for t in tk)
        if s > 0: o.append((s, d["path"]))
    o.sort(key=lambda x: -x[0]); return o

# ── NOYAU : les paires déjà annotées ────────────────────────────────────────
noyau = []
for cid, fam, q, cibles in cas:
    if len(cibles) < 2: continue
    c = cos(cibles[0], cibles[1])
    noyau.append(dict(id=cid, source=fam, requete_id=cid, paire=cibles[:2], cosinus=c))
print(f"── NOYAU · paires annotées indépendamment : {len(noyau)} ──")
for n in noyau:
    print(f"   cos {n['cosinus']:.3f}   {n['source'][:26]:28} "
          f"{os.path.basename(n['paire'][0])[:34]} ↔ {os.path.basename(n['paire'][1])[:34]}")
seuils = [n["cosinus"] for n in noyau if n["cosinus"] is not None]
THETA = min(seuils)
print(f"\n   θ = cosinus le plus bas des paires ANNOTÉES = {THETA:.3f}  (calibré sur "
      f"l'annotation, pas sur le résultat)")

# ── ÉTENDU : la « classe 3 » qui n'en est peut-être pas une ─────────────────
etendu, vraies_erreurs = [], []
for cid, fam, q, cibles in cas:
    r = classement(q)
    if len(r) < 2: continue
    p1 = r[0][1]
    if p1 in cibles: continue                       # BM25 a raison : hors sujet ici
    meilleure = next((p for _, p in r if p in cibles), None)
    if meilleure is None: continue
    c = cos(p1, meilleure)
    if False:  # classe étendue DISQUALIFIÉE (cf. en-tête)
        etendu.append(dict(id=cid, source=fam, requete_id=cid, paire=[p1, meilleure], cosinus=c))
    else:
        vraies_erreurs.append((cid, c))
print(f"\n── ÉTENDU · rang 1 ≠ cible mais SÉMANTIQUEMENT ÉQUIVALENT (cos ≥ {THETA:.3f}) : "
      f"{len(etendu)} ──")
for e in etendu:
    print(f"   cos {e['cosinus']:.3f}   {e['id'][:24]:26} "
          f"{os.path.basename(e['paire'][0])[:32]} ↔ {os.path.basename(e['paire'][1])[:32]}")
print(f"\n── vraies erreurs de BM25 restantes (cos < θ) : {len(vraies_erreurs)} ──")
for cid, c in vraies_erreurs[:10]:
    print(f"   cos {c if c is None else f'{c:.3f}'}   {cid}")

sortie = dict(protocole="selection AVEUGLE — aucun hit, aucune suggestion, aucun read_log consulte",
              theta=THETA, noyau=noyau, etendu=etendu,
              vraies_erreurs=[c for c, _ in vraies_erreurs])
chemin = os.path.join(ICI, "a86_classe2.json")
json.dump(sortie, open(chemin, "w"), ensure_ascii=False, indent=1)
print(f"\n→ gelé dans {os.path.relpath(chemin, BRAIN)} — à commiter AVANT l'étape 2.")
