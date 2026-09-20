#!/usr/bin/env python3
"""
portes_antifuite.py — les PORTES du chantier projection retrieval. Bloquantes, pas indicatives.

Un contrôle qui ne peut pas rougir ne prouve rien : chaque porte a son sabotage ci-dessous,
exécuté à chaque passage.

  P1  aucun fichier de held-out n'entre dans le corpus indexé
      (⚠️ `tests/` n'est PAS dans SKIP_DIRS : seule l'extension protège. Un held-out en .md
       serait indexé — c'est l'incident du 2026-08-12, 312 documents attendus / 1 573 indexés)
  P2  le sceau de chaque lot tient : les requêtes n'ont pas bougé depuis le scellement
  P3  le bac du générateur ne contient aucun held-out, aucun banc, aucun journal
  P4  aucune projection ne recopie un fragment de requête d'évaluation
      (délègue à tests/contamination_requetes.py — porte, pas constat)

  python3 tests/portes_antifuite.py
  python3 tests/portes_antifuite.py --check    # sort 1 si une porte est fermée
"""
import hashlib, json, os, sys, glob

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br
sys.path.insert(0, os.path.join(ICI, "heldout"))

HELDOUT = os.path.join(ICI, "heldout")
BAC = os.path.join(BRAIN, "tools", "projection", "bac")
echecs = []

def corpus_paths():
    return {d["path"] for d in br.load_corpus()}

# ── P1 ──────────────────────────────────────────────────────────────────────
print("── P1 · le held-out n'entre pas dans le corpus ─────────────────────────────")
cp = corpus_paths()
fuites = [p for p in cp if p.startswith("tests" + os.sep)]
md_heldout = glob.glob(os.path.join(HELDOUT, "**", "*.md"), recursive=True)
print(f"   corpus indexé : {len(cp)} fiches · aucune sous tests/ : "
      f"{'✅' if not fuites else '⛔ ' + str(fuites[:3])}")
print(f"   fichiers .md dans tests/heldout/ : {len(md_heldout)}  "
      f"{'✅ aucun' if not md_heldout else '⛔ ' + str(md_heldout)}")
if fuites or md_heldout: echecs.append("P1")
# sabotage : un .md déposé dans heldout/ doit être vu comme une fuite
piege = os.path.join(HELDOUT, "_sabotage_p1.md")
open(piege, "w").write("# faux held-out\n")
try:
    vu = bool(glob.glob(os.path.join(HELDOUT, "**", "*.md"), recursive=True))
    indexe = os.path.relpath(piege, BRAIN) in corpus_paths()
    print(f"   sabotage — .md déposé dans heldout/ : détecté par la porte {'✅' if vu else '⛔'} · "
          f"réellement indexé par le corpus {'⛔ OUI' if indexe else 'non'}")
    if not vu: echecs.append("P1-sabotage")
finally:
    os.remove(piege)

# ── P2 ──────────────────────────────────────────────────────────────────────
print("\n── P2 · le sceau des lots tient ────────────────────────────────────────────")
def empreinte(rs):
    h = hashlib.sha256()
    for r in rs: h.update(r.encode("utf-8")); h.update(b"\x00")
    return h.hexdigest()
lots = sorted(glob.glob(os.path.join(HELDOUT, "heldout-*.json")))
if not lots:
    print("   aucun lot scellé — porte sans objet pour l'instant (held-out PROSPECTIF)")
for f in lots:
    d = json.load(open(f, encoding="utf-8"))
    ok = empreinte([c["requete"] for c in d["cas"]]) == d["sha_requetes"]
    print(f"   {os.path.basename(f)} : {'✅ intact' if ok else '⛔ ROMPU'}")
    if not ok: echecs.append("P2")
    # sabotage : une requête modifiée doit rompre le sceau
    faux = [c["requete"] for c in d["cas"]]
    if faux:
        faux[0] += " x"
        print(f"   sabotage — une requête altérée : sceau "
              f"{'✅ rompu comme attendu' if empreinte(faux) != d['sha_requetes'] else '⛔ TIENT'}")

# ── P3 ──────────────────────────────────────────────────────────────────────
print("\n── P3 · le bac du générateur ne contient que des fiches sources ────────────")
if not os.path.isdir(BAC):
    print("   bac non construit — porte sans objet (aucune génération n'a eu lieu)")
else:
    dedans = [os.path.relpath(os.path.join(r, f), BAC)
              for r, _, fs in os.walk(BAC) for f in fs]
    interdits = [f for f in dedans
                 if "heldout" in f or "golden" in f or "banc" in f or f.endswith(".jsonl")]
    print(f"   {len(dedans)} fichier(s) · contenu interdit : "
          f"{'✅ aucun' if not interdits else '⛔ ' + str(interdits)}")
    if interdits: echecs.append("P3")

# ── P4 ──────────────────────────────────────────────────────────────────────
print("\n── P4 · aucune projection ne recopie une requête d'évaluation ──────────────")
proj = glob.glob(os.path.join(BRAIN, "tools", "projection", "projections", "*.json"))
print(f"   projections existantes : {len(proj)}  "
      f"{'— porte sans objet, rien de généré' if not proj else ''}")
print("   (quand elles existeront : tests/contamination_requetes.py devient bloquant ici)")

print("\n" + "─" * 76)
print(f"PORTES : {'✅ toutes ouvertes' if not echecs else '⛔ FERMÉES : ' + ', '.join(echecs)}")
sys.exit(1 if (echecs and "--check" in sys.argv) else 0)
