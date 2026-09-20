#!/usr/bin/env python3
"""
contamination_requetes.py — une fiche INDEXÉE ne doit pas recopier une requête d'évaluation.

L'INVARIANT (complète pas_de_fuite_evaluation.py) :

    pas_de_fuite_evaluation.py protège les LIEUX : tests/ et tools/ hors du corpus.
    Il ne voit PAS une fiche de savoir légitime, dans projects/ ou lessons/, qui recopie
    littéralement la question d'un cas du golden set ou du banc retrieval.

L'INCIDENT QUI L'A PRODUIT (2026-08-19) :

    La fiche documentant la régression q13 citait sa requête mot pour mot.
    Elle est devenue le rang 1 de q13 (17.55), poussant la cible de la 2e à la 3e place ;
    P@3 est tombé de 0.87 à 0.80. La documentation d'une régression a créé une régression.

CE QUI N'EST PAS UNE CONTAMINATION :
  - la fiche CIBLE du cas : elle a le droit de contenir les mots de sa propre question ;
  - un wikilink [[nom-de-la-cible]] : c'est une référence, pas une reproduction ;
  - du code inline `...` ou un chemin `x/y.md` : même raison.

Lancer :
  python3 tests/contamination_requetes.py            # rapport
  python3 tests/contamination_requetes.py --check    # barrière, sort 1 si contamination
  python3 tests/contamination_requetes.py --sabotage # contre-épreuve : le test sait-il rougir ?
"""
import argparse, json, os, pathlib, re, sys

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br

ZONES_EVAL = ("tests", "tools")     # déjà couvertes par pas_de_fuite_evaluation.py
N_MOTS = 6                          # fragment jugé discriminant

def nettoyer(s):
    s = re.sub(r"\[\[[^\]]+\]\]", " ", s)       # wikilinks : référence, pas reproduction
    s = re.sub(r"`[^`]*`", " ", s)              # code inline
    s = re.sub(r"[\w./-]+\.md\b", " ", s)       # chemins de fiches
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def cas_et_cibles(docs):
    par_nom = {}
    for d in docs: par_nom.setdefault(d["name"], set()).add(d["path"])
    cas = []
    g = json.load(open(os.path.join(ICI, "golden_recall.json")))
    for c in g["cas"]:
        cas.append((c["id"], c["query"], set(c["attendu"])))
    for c in json.load(open(os.path.join(ICI, "banc-retrieval/cas.json"))):
        cibles = c["t"] if isinstance(c["t"], list) else [c["t"]]
        s = set()
        for nom in cibles: s |= par_nom.get(nom, set())
        cas.append((c["c"][:24], c["q"], s))
    return cas

def analyser(extra_textes=None):
    docs = br.load_corpus()
    cas = cas_et_cibles(docs)
    textes = {}
    for d in docs:
        f = pathlib.Path(d["path"])
        if f.exists(): textes[d["path"]] = nettoyer(f.read_text(encoding="utf-8", errors="replace"))
    if extra_textes: textes.update({k: nettoyer(v) for k, v in extra_textes.items()})

    contam, legitimes, courtes = [], [], []
    for cid, q, cibles in cas:
        mots = nettoyer(q).split()
        if len(mots) < N_MOTS:
            courtes.append(cid); continue           # fragment trop court = faux positifs
        frags = [" ".join(mots[i:i+N_MOTS]) for i in range(len(mots)-N_MOTS+1)]
        for p, t in textes.items():
            if p.split(os.sep)[0] in ZONES_EVAL: continue
            if any(f in t for f in frags):
                (legitimes if p in cibles else contam).append((cid, p))
    return sorted(set(contam)), sorted(set(legitimes)), sorted(set(courtes)), len(textes)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sabotage", action="store_true")
    a = ap.parse_args()

    if a.sabotage:
        # SABOTAGE : injecter une requête dans une fiche indexée HORS zone d'évaluation.
        g = json.load(open(os.path.join(ICI, "golden_recall.json")))
        q = next(c["query"] for c in g["cas"] if c["id"] == "q13-timeline-bm25")
        faux = {"lessons/__sabotage_contamination__.md": f"# faux\n\n{q}\n"}
        av, *_ = analyser()
        ap_, *_ = analyser(extra_textes=faux)
        injecte = [x for x in ap_ if "__sabotage__" in x[1] or "sabotage" in x[1]]
        print(f"contamination avant sabotage : {len(av)}")
        print(f"contamination après          : {len(ap_)}")
        ok = len(ap_) > len(av) and injecte
        print(f"\n{'✅ LE TEST SAIT ROUGIR' if ok else '⛔ SABOTAGE NON DÉTECTÉ — le test ne protège de rien'}")
        return 0 if ok else 1

    contam, legit, courtes, n = analyser()
    print(f"Contamination des requêtes d'évaluation — {n} fiches indexées, "
          f"fragments de {N_MOTS} mots\n")
    print(f"  ✅ occurrences LÉGITIMES (la fiche est la cible du cas) : {len(legit)}")
    for cid, p in legit: print(f"       {cid:26} {p}")
    print(f"\n  ⚠️  CONTAMINATIONS (fiche indexée ≠ cible, hors zones d'évaluation) : {len(contam)}")
    for cid, p in contam: print(f"       {cid:26} {p}")
    if courtes:
        print(f"\n  (non testés — requête de moins de {N_MOTS} mots : {', '.join(courtes)})")
    if a.check and contam:
        print("\n❌ une fiche indexée recopie une requête d'évaluation — elle fausse le banc qu'elle décrit")
        return 1
    print("\n✅ aucune contamination" if not contam else "")
    return 0

if __name__ == "__main__":
    sys.exit(main())
