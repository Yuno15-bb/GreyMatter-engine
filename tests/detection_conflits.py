#!/usr/bin/env python3
"""detection_conflits.py — le BANC de la détection de relation entre deux connaissances.

CE QU'IL MESURE. La question qui précède le résolveur d'autorité : ces deux affirmations
sont-elles en conflit, et de quel genre ? Six classes (cf. `taxonomie` dans
tests/fixtures_detection.json), pas deux.

⚠️ CE FICHIER N'EST PAS UN DÉTECTEUR. C'est un banc et ses BASELINES. Aucune ligne d'ici
n'est branchée sur le rappel, et l'ADR-0010 tient : le résolveur reste hors production, et
la détection n'y entre pas non plus. Ce qui est construit ici, c'est l'instrument capable
de prouver qu'un détecteur est MAUVAIS — avant d'en écrire un.

POURQUOI DES BASELINES QU'ON SAIT MAUVAISES. Sans le chiffre de ce que le lexical sait
faire tout seul, on ne pourra jamais dire ce qu'un mécanisme coûteux a réellement apporté.
Une baseline n'est pas une proposition : c'est une unité de mesure.

Lancer :
  python3 tests/detection_conflits.py                  # les baselines, sur le jeu étiqueté
  python3 tests/detection_conflits.py --check          # barrière : structure du jeu + pièges réels
  python3 tests/detection_conflits.py --corpus-reel    # taux de fausse alarme sur le VRAI tronc
  python3 tests/detection_conflits.py --embeddings     # baseline sémantique (venv model2vec)
  python3 tests/detection_conflits.py --sabotages      # rejoue tous les sabotages du banc

SABOTAGES (chacun doit faire rougir au moins un cas qui ne dépend QUE du chemin saboté) :
  --sans-scope           le domaine d'application est ignoré
  --sans-temporalite     les dates sont ignorées
  --sans-marqueur        les marqueurs de remplacement sont ignorés
  --force-contradiction  UNRESOLVED est transformé en CONTRADICTION
  --recouvrement-seul    « similarité élevée = contradiction », la fausse équation
"""
import argparse
import json
import os
import random
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
FIXTURES = os.path.join(ICI, "fixtures_detection.json")
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
import brain_recall as br  # noqa: E402

CLASSES = ("CONTRADICTION", "SUPERSESSION", "SCOPE_DIFFERENCE",
           "TEMPORAL_DIFFERENCE", "COMPATIBLE", "UNRESOLVED")

# ── seuils de la baseline. Ce sont des CHOIX, pas des vérités ; ils sont ici pour être
# lus et contestés. Aucun n'a été réglé en regardant les étiquettes attendues : les régler
# sur le jeu reviendrait à mesurer son propre réglage.
SEUIL_SUJET = 0.12        # en dessous : les deux textes ne parlent pas de la même chose
SEUIL_SIMILARITE = 0.35   # utilisé UNIQUEMENT par la fausse équation (--recouvrement-seul)
ECART_TEMPOREL_JOURS = 21 # au-delà : deux constats datés ne décrivent plus le même instant

# Marqueurs de négation. Liste GÉNÉRIQUE du français, volontairement pas une liste
# d'antonymes : une table d'antonymes écrite en regardant le jeu de test mesurerait sa
# propre écriture, pas la difficulté du problème.
NEGATIONS = {"ne", "pas", "jamais", "aucun", "aucune", "sans", "non", "ni", "rien",
             "interdit", "interdite", "refuse", "cesse", "plus"}


def toks(texte):
    return set(br.tokenize(texte or ""))


def recouvrement(a, b):
    """Jaccard sur les racines — la MÊME tokenisation que le rappel, délibérément.

    Mesurer le recouvrement avec un autre tokeniseur que celui du moteur produirait un
    chiffre qui ne décrit aucun système réel. cf. [[un-detecteur-partage-par-concept]]
    """
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _nombres(texte):
    """Les valeurs numériques d'un texte, virgule décimale française comprise."""
    return set(re.findall(r"\d+(?:[.,]\d+)?", texte or ""))


def _jours(a, b):
    """Écart en jours entre deux dates ISO, ou None si l'une manque."""
    from datetime import date
    if not a or not b:
        return None
    try:
        da = date(*[int(x) for x in a.split("-")])
        db = date(*[int(x) for x in b.split("-")])
    except Exception:
        return None
    return abs((da - db).days)


def _marqueur(cote_a, cote_b):
    """Quelqu'un a-t-il posé un marqueur de succession ? C'est le seul signal VOLONTAIRE."""
    for c in (cote_a, cote_b):
        if c.get("superseded") or c.get("remplace") or c.get("redirectsTo"):
            return True
    return False


def _opposition_lexicale(a, b):
    """La moitié SÉMANTIQUE, faite avec les moyens du bord — c'est ici que ça casse.

    Deux signaux seulement, tous deux de surface :
      • asymétrie de négation — un côté nie beaucoup plus que l'autre ;
      • divergence numérique — mêmes mots, chiffres différents.
    Aucun des deux ne lit le SENS. C'est exactement ce que la mesure doit chiffrer.
    """
    ta, tb = toks(a), toks(b)
    mots_a = set(re.findall(r"[a-zà-ÿ]+", (a or "").lower()))
    mots_b = set(re.findall(r"[a-zà-ÿ]+", (b or "").lower()))
    neg_a, neg_b = len(mots_a & NEGATIONS), len(mots_b & NEGATIONS)
    asym_negation = abs(neg_a - neg_b) >= 2

    na, nb = _nombres(a), _nombres(b)
    divergence_num = bool(na and nb and na != nb and (ta & tb))
    return asym_negation or divergence_num


# ─────────────────────────────────────────────────────── les baselines

def b0_tout_conflit(cas, **_):
    """PLANCHER. Tout est une contradiction. Rappel parfait, précision catastrophique."""
    return "CONTRADICTION"


def b1_recouvrement_seul(cas, **_):
    """LA FAUSSE ÉQUATION : « similarité élevée = contradiction ».

    C'est la première idée de tout le monde, et c'est celle que le jeu de test existe pour
    tuer. Elle est mesurée ici, comme baseline ET comme sabotage — le même code, parce que
    c'est la même erreur vue deux fois.
    """
    return ("CONTRADICTION" if recouvrement(cas["A"]["texte"], cas["B"]["texte"])
            >= SEUIL_SIMILARITE else "COMPATIBLE")


def b2_lexical_et_metadonnees(cas, sans_scope=False, sans_temporalite=False,
                              sans_marqueur=False, force_contradiction=False):
    """LA MEILLEURE BASELINE DÉTERMINISTE HONNÊTE.

    Elle sépare franchement les deux moitiés du problème :
      • la moitié MÉTADONNÉE (marqueur, portée, date) est structurée, donc décidable ;
      • la moitié SÉMANTIQUE (« ces deux phrases s'excluent-elles ? ») ne l'est pas, et
        `_opposition_lexicale` en est le substitut de surface.
    L'écart entre les deux moitiés est le résultat que ce banc doit produire.

    L'ordre suit la précédence déclarée dans le jeu de test. Il n'est pas négociable au
    coup par coup : une précédence qu'on réarrange par cas est un réglage déguisé.
    """
    A, B = cas["A"], cas["B"]
    ta, tb = A["texte"], B["texte"]

    # 0. parle-t-on seulement de la même chose ?
    if recouvrement(ta, tb) < SEUIL_SUJET:
        return "COMPATIBLE"

    # 1. information insuffisante pour classer : ni portée ni date d'aucun côté
    sans_portee = not A.get("domaine") and not B.get("domaine")
    sans_date = not A.get("at") and not B.get("at")
    if sans_portee and sans_date:
        return "CONTRADICTION" if force_contradiction else "UNRESOLVED"

    # 2. marqueur de remplacement — le seul signal posé volontairement par un humain
    if not sans_marqueur and _marqueur(A, B):
        return "SUPERSESSION"

    # 3. portées disjointes
    if not sans_scope:
        da, db = A.get("domaine"), B.get("domaine")
        if da and db and da != db:
            return "SCOPE_DIFFERENCE"

    # 4. périodes distinctes
    if not sans_temporalite:
        ecart = _jours(A.get("at"), B.get("at"))
        if ecart is not None and ecart > ECART_TEMPOREL_JOURS:
            return "TEMPORAL_DIFFERENCE"

    # 5. incompatibilité, pour autant qu'un signal de surface la trahisse
    if _opposition_lexicale(ta, tb):
        return "CONTRADICTION"
    return "COMPATIBLE"


BASELINES = {
    "B0 tout-conflit": b0_tout_conflit,
    "B1 recouvrement-seul": b1_recouvrement_seul,
    "B2 lexical+métadonnées": b2_lexical_et_metadonnees,
}


# ─────────────────────────────────────────────────────── mesure

def mesurer(cas_tous, predire, **kw):
    res = [(c, predire(c, **kw)) for c in cas_tous]
    n = len(res)
    justes = sum(1 for c, v in res if v == c["attendu"])

    vrais_conflits = [(c, v) for c, v in res if c["attendu"] == "CONTRADICTION"]
    dits_conflits = [(c, v) for c, v in res if v == "CONTRADICTION"]
    non_conflits = [(c, v) for c, v in res if c["attendu"] != "CONTRADICTION"]

    tp = sum(1 for c, v in dits_conflits if c["attendu"] == "CONTRADICTION")
    prec = tp / len(dits_conflits) if dits_conflits else 0.0
    rapp = tp / len(vrais_conflits) if vrais_conflits else 0.0
    faux = sum(1 for c, v in non_conflits if v == "CONTRADICTION")
    return {
        "res": res, "n": n,
        "classification_accuracy": justes / n,
        "conflict_precision": prec,
        "conflict_recall": rapp,
        "false_conflict_rate": faux / len(non_conflits) if non_conflits else 0.0,
        "unresolved_rate": sum(1 for _, v in res if v == "UNRESOLVED") / n,
    }


def _ligne_metriques(nom, m):
    return (f"  {nom:26} acc {m['classification_accuracy']:.2f}"
            f"  ·  P {m['conflict_precision']:.2f}"
            f"  R {m['conflict_recall']:.2f}"
            f"  ·  FAUSSE ALARME {m['false_conflict_rate']:.2f}"
            f"  ·  unres {m['unresolved_rate']:.2f}")


# ─────────────────────────────────────────────────────── contrôles du JEU lui-même

def controler_jeu(cas_tous):
    """Le jeu de test est-il ce qu'il prétend être ?

    Un piège auto-proclamé qui n'en est pas un est un piège décoratif : il rassure sans
    rien éprouver. On vérifie donc l'étiquette `piege` contre le recouvrement MESURÉ.
    """
    ennuis = []
    ids = [c["id"] for c in cas_tous]
    if len(set(ids)) != len(ids):
        ennuis.append("des identifiants sont en double")

    for c in cas_tous:
        if c["attendu"] not in CLASSES:
            ennuis.append(f"{c['id']} : classe hors vocabulaire ({c['attendu']})")
        for cote in ("A", "B"):
            if not (c.get(cote) or {}).get("texte"):
                ennuis.append(f"{c['id']} : côté {cote} sans texte")
        if not c.get("pourquoi"):
            ennuis.append(f"{c['id']} : sans justification écrite")

    # Bandes ABSOLUES, pas une médiane. Une médiane est un seuil qui bouge : la moitié des
    # cas est sous elle par construction, donc étiqueter plus de la moitié du jeu
    # « recouvrement-fort » échouerait quoi qu'on écrive — le contrôle punirait la taille du
    # jeu, pas la qualité des étiquettes. Les bandes ci-dessous sont fixes et publiées dans
    # le jeu lui-même ; un cas entre les deux ne porte AUCUNE étiquette de piège.
    BANDE_FORT, BANDE_FAIBLE = 0.35, 0.05
    recs = {c["id"]: recouvrement(c["A"]["texte"], c["B"]["texte"]) for c in cas_tous}
    med = sorted(recs.values())[len(recs) // 2]
    for c in cas_tous:
        r = recs[c["id"]]
        if c.get("piege") == "recouvrement-fort" and r < BANDE_FORT:
            ennuis.append(f"{c['id']} : annoncé « recouvrement-fort » mais mesuré "
                          f"{r:.2f} < {BANDE_FORT} — piège décoratif")
        if c.get("piege") == "recouvrement-faible" and r > BANDE_FAIBLE:
            ennuis.append(f"{c['id']} : annoncé « recouvrement-faible » mais mesuré "
                          f"{r:.2f} > {BANDE_FAIBLE} — piège décoratif")

    # Les deux familles doivent rester SÉPARÉES : sans séparation, l'étiquette ne porte
    # aucune information et le jeu ne démontre plus que le recouvrement n'est pas le signal.
    forts = [recs[c["id"]] for c in cas_tous if c.get("piege") == "recouvrement-fort"]
    faibles = [recs[c["id"]] for c in cas_tous if c.get("piege") == "recouvrement-faible"]
    if forts and faibles and min(forts) <= max(faibles):
        ennuis.append(f"bandes qui se chevauchent : min(fort)={min(forts):.2f} ≤ "
                      f"max(faible)={max(faibles):.2f} — l'étiquette ne trie plus rien")

    # Chaque classe doit être représentée, sinon la mesure est aveugle sur elle.
    for cl in CLASSES:
        if not any(c["attendu"] == cl for c in cas_tous):
            ennuis.append(f"aucun cas de classe {cl} — la mesure serait aveugle dessus")

    # Les sentinelles nommées dans le point de reprise ne doivent pas disparaître.
    sentinelles = [c["id"] for c in cas_tous if c.get("sentinelle")]
    if len(sentinelles) < 8:
        ennuis.append(f"seulement {len(sentinelles)} sentinelles — le jeu s'est affaibli")
    return ennuis, recs, med


# ─────────────────────────────────────────────────────── sabotages

SABOTAGES = {
    "--sans-scope": {"sans_scope": True},
    "--sans-temporalite": {"sans_temporalite": True},
    "--sans-marqueur": {"sans_marqueur": True},
    "--force-contradiction": {"force_contradiction": True},
}


def rejouer_sabotages(cas_tous):
    """Chaque sabotage doit faire BASCULER au moins un cas. Sinon le jeu n'isole pas ce
    chemin — et c'est le JEU qu'on renforce, jamais le mécanisme."""
    base = {c["id"]: v for c, v in mesurer(cas_tous, b2_lexical_et_metadonnees)["res"]}
    m0 = mesurer(cas_tous, b2_lexical_et_metadonnees)
    print("Sabotages du banc — référence B2 :")
    print(_ligne_metriques("(sans sabotage)", m0), "\n")

    muets = []
    for drapeau, kw in SABOTAGES.items():
        m = mesurer(cas_tous, b2_lexical_et_metadonnees, **kw)
        bascules = [(c["id"], base[c["id"]], v) for c, v in m["res"] if base[c["id"]] != v]
        etat = "🔴 rougit" if bascules else "⚠️  MUET"
        print(f"  {drapeau:24} {etat}   "
              f"acc {m0['classification_accuracy']:.2f} → {m['classification_accuracy']:.2f}"
              f"  ·  fausse alarme {m0['false_conflict_rate']:.2f} → "
              f"{m['false_conflict_rate']:.2f}")
        for cid, avant, apres in bascules[:4]:
            print(f"      {cid:52} {avant} → {apres}")
        if not bascules:
            muets.append(drapeau)
        print()

    m = mesurer(cas_tous, b1_recouvrement_seul)
    bascules = sum(1 for c, v in m["res"] if base[c["id"]] != v)
    print(f"  {'--recouvrement-seul':24} {'🔴 rougit' if bascules else '⚠️  MUET'}   "
          f"acc {m0['classification_accuracy']:.2f} → {m['classification_accuracy']:.2f}"
          f"  ·  fausse alarme {m0['false_conflict_rate']:.2f} → "
          f"{m['false_conflict_rate']:.2f}   ({bascules} cas basculent)")
    if not bascules:
        muets.append("--recouvrement-seul")
    return muets


# ─────────────────────────────────────────────────────── contrôle sur le VRAI tronc

def corpus_reel(n_paires=2000, graine=20260817):
    """Taux de FAUSSE ALARME en conditions réelles, sans étiquetage.

    L'astuce qui rend ce contrôle gratuit : sur des paires tirées au hasard dans le tronc,
    la contradiction est un événement RARE. Un détecteur qui en déclare beaucoup se trahit
    tout seul — aucune étiquette n'est nécessaire pour le savoir.

    ⚠️ LIMITE À NE PAS OUBLIER : l'unité comparée ici est la DESCRIPTION d'une fiche, pas
    une affirmation isolée. Une fiche de 200 lignes porte des dizaines d'affirmations ; la
    contradiction vit entre affirmations, pas entre documents. Ce chiffre mesure donc le
    meilleur cas, celui où chaque fiche est réduite à sa phrase la plus nette.
    """
    docs = [d for d in br.load_corpus() if d.get("desc")]
    rnd = random.Random(graine)
    paires = set()
    while len(paires) < n_paires and len(paires) < len(docs) * (len(docs) - 1) // 2:
        i, j = rnd.randrange(len(docs)), rnd.randrange(len(docs))
        if i != j:
            paires.add((min(i, j), max(i, j)))

    def domaine(path):
        parts = path.split(os.sep)
        return os.sep.join(parts[:2]) if len(parts) > 2 else parts[0]

    compte = {c: 0 for c in CLASSES}
    exemples = []
    for i, j in paires:
        a, b = docs[i], docs[j]
        cas = {
            "A": {"texte": a["desc"], "domaine": domaine(a["path"]), "at": None,
                  "remplace": a.get("remplace"), "redirectsTo": a.get("redirige_vers")},
            "B": {"texte": b["desc"], "domaine": domaine(b["path"]), "at": None,
                  "remplace": b.get("remplace"), "redirectsTo": b.get("redirige_vers")},
        }
        v = b2_lexical_et_metadonnees(cas)
        compte[v] += 1
        if v == "CONTRADICTION" and len(exemples) < 6:
            exemples.append((a["name"], b["name"]))
    return compte, len(paires), exemples, len(docs)


def fenetre_rappel(k=5):
    """LE contrôle qui décide de la faisabilité — et le seul réaliste.

    Le tirage au hasard (--corpus-reel) mesure une population où la contradiction est
    absente par construction : deux fiches prises au hasard ne parlent de rien de commun,
    et le détecteur les écarte à la première étape sans jamais atteindre son raisonnement.
    Un taux de fausse alarme mesuré là-dessus FLATTE le détecteur — c'est un examen dont
    99,8 % des copies sont blanches.

    La fenêtre réelle est le TOP-K du rappel : des fiches déjà sélectionnées pour leur
    proximité au sujet. Elles sont lexicalement proches par définition, donc chaque paire
    atteint l'étape sémantique. C'est là que se produisent les fausses alarmes, et c'est
    la seule population sur laquelle la question « peut-on brancher ça ? » a un sens.
    """
    golden = json.load(open(os.path.join(ICI, "golden_recall.json"), encoding="utf-8"))
    docs = br.load_corpus()
    moteur = br.BM25(docs)

    def domaine(path):
        parts = path.split(os.sep)
        return os.sep.join(parts[:2]) if len(parts) > 2 else parts[0]

    compte = {c: 0 for c in CLASSES}
    n_paires = 0
    atteignent_semantique = 0
    exemples = []
    for cas_q in golden["cas"]:
        top = [d for _, d in moteur.search(cas_q["query"], k=k, feedback=False)]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a, b = top[i], top[j]
                if not (a.get("desc") and b.get("desc")):
                    continue
                paire = {
                    "A": {"texte": a["desc"], "domaine": domaine(a["path"]), "at": None,
                          "remplace": a.get("remplace"), "redirectsTo": a.get("redirige_vers")},
                    "B": {"texte": b["desc"], "domaine": domaine(b["path"]), "at": None,
                          "remplace": b.get("remplace"), "redirectsTo": b.get("redirige_vers")},
                }
                if recouvrement(a["desc"], b["desc"]) >= SEUIL_SUJET:
                    atteignent_semantique += 1
                v = b2_lexical_et_metadonnees(paire)
                compte[v] += 1
                n_paires += 1
                if v == "CONTRADICTION" and len(exemples) < 8:
                    exemples.append((cas_q["id"], a["name"], b["name"]))
    return compte, n_paires, atteignent_semantique, exemples, len(golden["cas"])


# ─────────────────────────────────────────────────────── entrée

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sabotages", action="store_true")
    ap.add_argument("--corpus-reel", action="store_true")
    ap.add_argument("--fenetre-rappel", action="store_true")
    ap.add_argument("--embeddings", action="store_true")
    ap.add_argument("--detail", action="store_true", help="le verdict cas par cas")
    for d in SABOTAGES:
        ap.add_argument(d, action="store_true")
    ap.add_argument("--recouvrement-seul", action="store_true")
    a = ap.parse_args()

    jeu = json.load(open(FIXTURES, encoding="utf-8"))
    cas_tous = jeu["cas"]
    ennuis, recs, med = controler_jeu(cas_tous)

    if a.sabotages:
        muets = rejouer_sabotages(cas_tous)
        if muets:
            print(f"\n❌ sabotage(s) MUET(S) : {', '.join(muets)}")
            print("   Le jeu n'isole pas ce chemin. On renforce le JEU, jamais le mécanisme.")
            return 1
        print("\n✅ tous les sabotages rougissent sur au moins un cas")
        return 0

    if a.corpus_reel:
        compte, n, exemples, n_docs = corpus_reel()
        print(f"Corpus RÉEL — {n} paires tirées au hasard parmi {n_docs} fiches "
              f"({n_docs * (n_docs - 1) // 2} paires possibles)\n")
        for cl in CLASSES:
            print(f"  {cl:22} {compte[cl]:6}   {compte[cl] / n:6.1%}")
        taux = compte["CONTRADICTION"] / n
        print(f"\n  taux de fausse alarme ≈ {taux:.1%}   "
              f"(la contradiction est RARE entre deux fiches tirées au hasard)")
        if exemples:
            print("\n  Exemples déclarés en contradiction — à lire, ils ne le sont pas :")
            for x, y in exemples:
                print(f"     {x}\n       ↔ {y}")
        print(f"\n  Projection sur le tronc entier : {int(taux * n_docs * (n_docs - 1) / 2)} "
              f"« conflits » annoncés sur {n_docs * (n_docs - 1) // 2} paires.")
        return 0

    if a.fenetre_rappel:
        for k in (5, 10):
            compte, n, semantique, exemples, n_req = fenetre_rappel(k)
            taux = compte["CONTRADICTION"] / n if n else 0
            print(f"Fenêtre TOP-{k} du rappel — {n_req} requêtes réelles, "
                  f"{n} paires ({k * (k - 1) // 2} par requête)\n")
            for cl in CLASSES:
                if compte[cl]:
                    print(f"  {cl:22} {compte[cl]:5}   {compte[cl] / n:6.1%}")
            print(f"\n  paires atteignant l'étape sémantique : {semantique}/{n} "
                  f"({semantique / n:.0%})   ← contre ~0 % en tirage au hasard")
            print(f"  taux de fausse alarme                : {taux:.1%}")
            print(f"  → à {k * (k - 1) // 2} paires par prompt, "
                  f"{taux * k * (k - 1) / 2:.2f} faux conflit(s) annoncé(s) par prompt\n")
            if exemples and k == 5:
                print("  Exemples déclarés en contradiction — aucun ne l'est :")
                for q, x, y in exemples[:5]:
                    print(f"     [{q}] {x}\n              ↔ {y}")
                print()
        return 0

    if a.embeddings:
        return baseline_embeddings(cas_tous)

    # sabotage isolé demandé en ligne de commande
    kw = {}
    for d, k in SABOTAGES.items():
        if getattr(a, d.lstrip("-").replace("-", "_")):
            kw.update(k)

    print(f"Détection de relation — {len(cas_tous)} cas étiquetés, "
          f"{len(CLASSES)} classes, recouvrement médian {med:.2f}\n")

    if a.recouvrement_seul:
        m = mesurer(cas_tous, b1_recouvrement_seul)
        print(_ligne_metriques("B1 recouvrement-seul ⚠️", m))
        return 0

    resultats = {}
    for nom, fn in BASELINES.items():
        m = mesurer(cas_tous, fn, **(kw if fn is b2_lexical_et_metadonnees else {}))
        resultats[nom] = m
        print(_ligne_metriques(nom + (" ⚠️ SABOTÉ" if kw and fn is
                                      b2_lexical_et_metadonnees else ""), m))

    m2 = resultats["B2 lexical+métadonnées"]
    if a.detail:
        print("\n  Cas par cas (B2) — ⭐ = sentinelle :")
        for c, v in m2["res"]:
            ok = "✅" if v == c["attendu"] else "❌"
            etoile = "⭐" if c.get("sentinelle") else "  "
            print(f"   {ok}{etoile} {c['id']:52} {c['attendu']:20} → {v}")

    # Ce que la baseline rate, par classe : le vrai résultat de ce banc.
    print("\n  Ce que B2 rate, par classe attendue :")
    for cl in CLASSES:
        de_la_classe = [(c, v) for c, v in m2["res"] if c["attendu"] == cl]
        if not de_la_classe:
            continue
        rates = [(c, v) for c, v in de_la_classe if v != cl]
        print(f"    {cl:22} {len(de_la_classe) - len(rates)}/{len(de_la_classe)} juste"
              + (f"   — rate : {', '.join(c['id'].split('-')[0] for c, _ in rates)}"
                 if rates else ""))

    sent = [(c, v) for c, v in m2["res"] if c.get("sentinelle")]
    justes_sent = sum(1 for c, v in sent if v == c["attendu"])
    print(f"\n  Sentinelles : {justes_sent}/{len(sent)} justes "
          f"— ce sont les cas que le jeu existe pour poser.")

    if ennuis:
        print("\n❌ le JEU DE TEST est en défaut :")
        for e in ennuis:
            print(f"     {e}")
        return 1

    if a.check:
        print("\n✅ jeu de détection structurellement sain "
              f"({len(cas_tous)} cas, {len(CLASSES)} classes, "
              f"{sum(1 for c in cas_tous if c.get('sentinelle'))} sentinelles, "
              "pièges vérifiés contre le recouvrement mesuré)")
        print("   ⚠️ AUCUN détecteur n'est branché : ce banc mesure des baselines.")
    return 0


def baseline_embeddings(cas_tous):
    """B3 — la similarité SÉMANTIQUE comme signal de contradiction.

    Cette baseline existe pour éteindre la suggestion la plus prévisible d'un audit
    (« mettez des embeddings »). Deux affirmations opposées sont sémantiquement TRÈS
    proches : la similarité mesure le fait qu'elles parlent de la même chose, jamais le
    fait qu'elles s'excluent. La mesure doit le montrer, plutôt que l'affirmer.
    """
    venv = os.path.join(BRAIN, ".venv", "bin", "python")
    if not os.path.exists(venv):
        print("⚠️  venv absent — baseline embeddings non mesurable ici.")
        return 0
    script = os.path.join(ICI, "_embed_pairs.py")
    if not os.path.exists(script):
        print(f"⚠️  {script} absent.")
        return 0
    os.execv(venv, [venv, script])


if __name__ == "__main__":
    sys.exit(main())
