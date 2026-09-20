#!/usr/bin/env python3
"""
banc_a8_hits_agents.py — les hits d'AGENTS portent-ils une information utile ?

V1 (hits humains seuls) supprime 55 % du signal d'utilité. Avant toute décision, il faut
savoir si ces 55 % sont du bruit ou s'ils contiennent du signal.

Reproduit le calcul d'ADR-0003 (via recall_feedback), puis classe chaque hit d'agent selon
ce que l'agent a FAIT après la lecture, d'après son transcript. Lecture seule.
"""
import collections, json, os, pathlib, sys
ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import recall_feedback as rf

PROJ = pathlib.Path.home()/".claude/projects"
AGENTS_DIR = PROJ/"-Users-mac-claude-brain"
sid_kind, sid_file = {}, {}
for d in PROJ.iterdir():
    if not d.is_dir(): continue
    k = "agent" if d.name == AGENTS_DIR.name else ("humain" if d.name == "-Users-mac" else "autre")
    for f in d.glob("*.jsonl"): sid_kind[f.stem] = k; sid_file[f.stem] = f

sugg, prem = collections.defaultdict(set), {}
for d in rf._lire("recall_log.jsonl"):
    sugg[d["path"]].add(d["sid"]); c = (d["path"], d["sid"])
    if c not in prem or d["ts"] < prem[c]: prem[c] = d["ts"]
lec = collections.defaultdict(list)
for d in rf._lire("read_log.jsonl"): lec[(d["path"], d["sid"])].append(d["ts"])

hits_agents = []
for ch, sids in sugg.items():
    for sid in sids:
        ts = [t for t in lec.get((ch, sid), ()) if t >= prem[(ch, sid)] - rf.TOLERANCE_S]
        if ts and sid_kind.get(sid) == "agent":
            hits_agents.append((ch, sid, min(ts)))

def analyser_session(sid, chemin, ts_lecture):
    """Que fait l'agent APRÈS avoir lu la fiche ? Observables du transcript."""
    f = sid_file.get(sid)
    if not f or not f.exists(): return "indéterminable", "transcript absent"
    nom = pathlib.Path(chemin).stem
    ecritures_apres = 0; mention_apres = 0; vu_lecture = False
    try:
        for line in f.open(encoding="utf-8", errors="replace"):
            if '"Edit"' in line or '"Write"' in line or '"NotebookEdit"' in line:
                if vu_lecture: ecritures_apres += 1
            if nom in line:
                if vu_lecture: mention_apres += 1
                else: vu_lecture = True
    except Exception as e:
        return "indéterminable", f"lecture impossible ({e.__class__.__name__})"
    if not vu_lecture: return "indéterminable", "fiche non retrouvée dans le transcript"
    if ecritures_apres and mention_apres: return "action utile", f"{ecritures_apres} écriture(s), {mention_apres} mention(s) après"
    if ecritures_apres: return "écriture sans lien établi", f"{ecritures_apres} écriture(s), 0 mention après"
    if mention_apres: return "contexte seul", f"0 écriture, {mention_apres} mention(s) après"
    return "sans conséquence", "ni écriture ni mention après la lecture"

print(f"HITS D'AGENTS À CLASSER : {len(hits_agents)}\n")
classes = collections.Counter(); detail = collections.defaultdict(list)
for ch, sid, ts in hits_agents:
    c, pourquoi = analyser_session(sid, ch, ts)
    classes[c] += 1; detail[c].append((ch, sid[:8], pourquoi))
for c, n in classes.most_common():
    print(f"  {c:28} {n:3d}   {100*n/len(hits_agents):5.1f} %")
print()
for c in ("action utile", "écriture sans lien établi"):
    if detail[c]:
        print(f"── {c} (3 premiers)")
        for ch, sid, w in detail[c][:3]: print(f"     {sid}  {w:36} {ch}")

# ─── CONTRÔLE POSITIF DÉCISIF ─────────────────────────────────────────────────
# La classification textuelle ci-dessus est une PROXY polluée (un nom générique comme
# "claude-brain" matche tout le transcript). L'observable qui ne ment pas : est-ce que
# supprimer les hits d'agents fait PERDRE un rang à une fiche qui le méritait ?
print("\n" + "="*76)
print("CONTRÔLE POSITIF — V1 détruit-elle du signal utile ?\n")
import math
sys.path.insert(0, os.path.join(BRAIN, "hooks")); import brain_recall as br
docs = br.load_corpus(); moteur = br.BM25(docs); cfg = br.config()["exploration"]
prov = {}
for ch, sids in sugg.items():
    h = a = 0
    for sid in sids:
        if any(t >= prem[(ch, sid)] - rf.TOLERANCE_S for t in lec.get((ch, sid), ())):
            k = sid_kind.get(sid); h += (k == "humain"); a += (k == "agent")
    prov[ch] = {"hit": h+a, "hit_h": h, "sugg": len(sids)}
V0 = lambda p: 1 + 0.2*math.log(1 + prov.get(p, {}).get("hit", 0))
V1 = lambda p: 1 + 0.2*math.log(1 + prov.get(p, {}).get("hit_h", 0))

def rang_de(path, query, fac, k=5):
    q = br.tokenize(query)
    aj = []
    for i, d in enumerate(moteur.docs):
        s = sum(moteur._contrib(i, t) for t in q)
        if s > 0: aj.append({"p": d["path"], "s": s*fac(d["path"])})
    aj.sort(key=lambda r: -r["s"])
    for i, r in enumerate(aj[:k], 1):
        if r["p"] == path: return i
    return None

# toutes les fiches qui PERDENT du bonus sous V1 (hits agents > 0)
perdantes = [p for p, v in prov.items() if v["hit"] > v["hit_h"]]
titre = {d["path"]: (d.get("title") or d["name"]).replace("-", " ") for d in docs}
pertes, stables, absentes = [], 0, 0
for p in perdantes:
    if p not in titre: absentes += 1; continue
    r0, r1 = rang_de(p, titre[p], V0), rang_de(p, titre[p], V1)
    if (r1 or 99) > (r0 or 99): pertes.append((p, r0, r1))
    else: stables += 1
print(f"  fiches perdant du bonus sous V1 : {len(perdantes)}")
print(f"    rang INCHANGÉ ou meilleur     : {stables}")
print(f"    rang DÉGRADÉ                  : {len(pertes)}")
print(f"    hors corpus (non testable)    : {absentes}")
for p, r0, r1 in pertes[:8]:
    print(f"       rang {r0} → {r1}   {p}")
print(f"\n  → {'⛔ V1 DÉTRUIT DU SIGNAL' if pertes else '✅ aucune fiche ne perd son rang : les hits agents ne portent aucun signal détectable ici'}")
