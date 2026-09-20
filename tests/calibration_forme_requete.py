#!/usr/bin/env python3
"""
calibration_forme_requete.py — A8.8 : l'instrument mesure-t-il ce qu'il annonce ?

Avant de servir à une décision, `hooks/forme_requete.py` est confronté à des requêtes dont
on SAIT d'avance la forme. Un instrument qui ne sait pas distinguer un titre court d'une
question longue ne peut pas trancher entre les deux distributions d'A8.7.

N'ÉCRIT RIEN : ni dans state/, ni dans le journal de production. Les requêtes vivent ici,
dans tests/, hors du corpus indexé (verrouillé par tests/pas_de_fuite_evaluation.py).

  python3 tests/calibration_forme_requete.py
"""
import os, sys
ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br
from forme_requete import mesurer

CAS = [
    ("titre court",        "claude brain",                          dict(classe="1-2", exaequo=">=3")),
    ("titre court 2",      "jardinage regles",                      dict(classe="1-2", exaequo=">=1")),
    ("question naturelle", "comment le rappel decide-t-il quelles fiches remonter pour un prompt",
                                                                    dict(classe=">10", exaequo="1")),
    ("requete longue",     "je voudrais comprendre pourquoi une commande peut sortir en code zero "
                           "tout en n ayant rien affiche du tout et en abimant l etat qu elle devait montrer",
                                                                    dict(classe=">10", exaequo="1")),
    ("ecart franc",        "openpyxl images empilees cellule A1",   dict(classe="3-5", exaequo="1")),
    ("hors sujet",         "recette de la tarte aux pommes alsacienne",
                                                                    dict(classe="6-10", exaequo="?")),
]

moteur = br.BM25(br.load_corpus())
import forme_requete as FR
print(f"corpus {len(moteur.docs)} fiches · grille de tolérances {[f'{t:.0%}' for t in FR.TOLERANCES_EXAEQUO]}\n")
print(f"{'cas':22}{'classe':>9}{'tok':>5}{'s1':>8}{'s2':>8}{'écart':>9}   ex æquo 1%/2%/5%/10%")
print("-" * 80)
lignes = []
for nom, q, attendu in CAS:
    f = mesurer(br.tokenize(q), moteur.classer(q, 10), k=10)
    lignes.append((nom, f, attendu))
    er = f"{f['ecart_rel']:.1%}" if f["ecart_rel"] is not None else "—"
    s1 = f"{f['s1']:.2f}" if f["s1"] is not None else "—"
    s2 = f"{f['s2']:.2f}" if f["s2"] is not None else "—"
    ex = "/".join(str(f["exaequo"][f"{t:.0%}"]) for t in FR.TOLERANCES_EXAEQUO)
    print(f"{nom:22}{f['classe_longueur']:>9}{f['n_tokens']:5d}{s1:>8}{s2:>8}{er:>9}   {ex}")

print("\n── CE QUE L'INSTRUMENT DOIT SAVOIR FAIRE ───────────────────────────────────")
courtes = [f for n, f, a in lignes if f["classe_longueur"] == "1-2"]
longues = [f for n, f, a in lignes if f["classe_longueur"] == ">10"]
ok = True
if courtes and longues:
    ex_c = max(f["exaequo"]["5%"] for f in courtes); ex_l = max(f["exaequo"]["5%"] for f in longues)
    e_c = min(f["ecart_rel"] for f in courtes if f["ecart_rel"] is not None)
    e_l = min(f["ecart_rel"] for f in longues if f["ecart_rel"] is not None)
    print(f"  ex æquo à 5 % — courtes max {ex_c}  vs  longues max {ex_l}   "
          f"{'✅ séparé' if ex_c > ex_l else '⛔ NON SÉPARÉ'}")
    print(f"  écart relatif — courtes min {e_c:.1%}  vs  longues min {e_l:.1%}   "
          f"{'✅ séparé' if e_c < e_l else '⛔ NON SÉPARÉ'}")
    ok = ex_c > ex_l and e_c < e_l
print(f"\n  → l'instrument {'DISTINGUE' if ok else 'NE DISTINGUE PAS'} un titre court d'une "
      f"question longue —\n    c'est exactement la question laissée ouverte par A8.7.")

# ── contrôle de non-divulgation : rien du texte ne doit survivre ────────────
print("\n── CONTRÔLE DE NON-DIVULGATION ─────────────────────────────────────────────")
import json
f = mesurer(br.tokenize(CAS[0][1]), moteur.classer(CAS[0][1], 10), k=10)
brut = json.dumps(f, ensure_ascii=False)
fuite = [t for t in br.tokenize(CAS[0][1]) if t and t in brut]
print(f"  champs enregistrés : {sorted(f)}")
print(f"  tokens de la requête retrouvés dans la sortie : {fuite if fuite else 'aucun'}   "
      f"{'⛔ FUITE' if fuite else '✅'}")
print(f"  types : {sorted({type(v).__name__ for v in f.values()})}  — "
      f"{'✅ que des nombres et un libellé de classe' if not fuite else '⛔'}")
sys.exit(0 if ok and not fuite else 1)
