#!/usr/bin/env python3
"""
carte_divergence.py — D5.1 : le manifeste de curation dit-il encore la même chose que la carte ?

CE QU'IL MESURE. `MEMORY.md` est écrite à la main ; `tools/cartes/manifeste-carte.json` est
la curation dont D3 sait reprojeter la carte. Les deux dérivent en silence dès qu'on ajoute
une entrée à la carte sans toucher au manifeste. D4 l'avait vu avec UN pointeur et l'avait
noté comme une borne pour D5 ; personne ne l'a mesuré depuis.

⚠️ LE BUT DE D5.1 N'EST PAS DE REMETTRE LES ENTRÉES MANQUANTES DANS LE MANIFESTE. C'est de
construire l'instrument qui empêchera cette dérive de revenir SANS QUE PERSONNE NE LE VOIE.
Ce script ne synchronise rien, ne réécrit rien, ne propose aucun correctif automatique.

QUATRE ÉCARTS DISTINGUÉS :
  1. présent dans la carte, absent du manifeste   (la carte a avancé seule)
  2. présent dans le manifeste, absent de la carte (l'inverse — une entrée oubliée ou retirée)
  3. référence du manifeste vers une fiche introuvable (renommée, déplacée, supprimée)
  4. doublons dans le manifeste

DÉFINITION DE « SYNCHRONISÉ », relevée le 2026-08-20 (l'auteur) :

    mêmes membres + mêmes positions + mêmes niveaux + mêmes annotations + références valides

et NON « mêmes wikilinks ». D5.2 a montré pourquoi : le manifeste attribuait l'annotation de
D1 à D2 tout en étant parfaitement synchronisé en appartenance. **Un manifeste peut être juste
sur ses membres et faux sur leurs propriétés.** Comparer les ensembles ne pouvait pas le voir.

« Entrée » n'est plus « wikilink » : c'est la RÈGLE D'ENTRÉE gravée (tools/cartes/regle_entree.py) —
un lien inséré dans une phrase est une MENTION et ne compte pas. La version précédente de ce
fichier comptait les mentions, et rendait donc `claude-brain` (« Voir [[…]]. » en pied de page)
faussement divergent.

LECTURE SEULE sur MEMORY.md, le manifeste et les fiches. Les sabotages tournent sur des
COPIES isolées : muter le vrai index du Brain pour éprouver un détecteur le laisserait
corrompu si le processus mourait en route. Le SHA des vrais fichiers, relevé avant et après,
le prouve plutôt que de l'affirmer.

  python3 tests/carte_divergence.py             rapport
  python3 tests/carte_divergence.py --check     sort 1 s'il y a une divergence
"""
import hashlib, json, os, re, sys, shutil, tempfile, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "tools", "cartes"))
from regle_entree import lire as lire_regle

ICI = os.path.dirname(os.path.abspath(__file__)); BRAIN = os.path.dirname(ICI)
MEMORY = os.path.join(BRAIN, "MEMORY.md")
MANIFESTE = os.path.join(BRAIN, "tools", "cartes", "manifeste-carte.json")
# `skills` MANQUAIT ICI, et c'est tout le défaut des 24 « références mortes » :
# tools/cartes/reconcilier.py — l'autre consommateur de la même source — l'inclut
# depuis le 27/08. Le détecteur et le réconciliateur lisaient donc deux univers
# différents, et fabriquaient la divergence qu'ils prétendaient mesurer.
ZONES = ("projects", "lessons", "life", "meta", "planet", "agents", "skills")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def index_fiches(racine):
    """{slug: chemin} — la règle d'identité est IMPORTÉE, jamais recopiée.

    `basename[:-3]` est faux pour `skills/` : Claude Code impose `skills/<slug>/SKILL.md`,
    donc 24 fichiers s'appellent tous « SKILL » et l'identité vit dans le DOSSIER
    (décision l'auteur, 2026-08-27, écrite dans hooks/identite_fiche.py). Appliquer la règle
    générale ici déclarait les 24 skills « références mortes » alors qu'ils sont sur le
    disque — et le `setdefault` du parcours précédent les aurait de toute façon fondus en
    une seule identité « SKILL ».

    `reconcilier.py` importe déjà cette même fonction avec le même argument : deux
    instruments qui lisent la même source doivent la lire PAREIL, sinon ils fabriquent la
    divergence qu'ils mesurent. Les conflits (deux représentations concurrentes d'un même
    slug) sont RENDUS, pas tranchés ici."""
    sys.path.insert(0, os.path.join(BRAIN, "hooks"))
    from identite_fiche import scanner
    index, conflits, _ignores = scanner(racine, ZONES)
    index_fiches.conflits = conflits
    return {slug: os.path.join(racine, rel) for slug, rel in index.items()}


def analyser(memory_path, manifeste_path, racine):
    man = json.load(open(manifeste_path, encoding="utf-8"))
    entrees = man["entrees"]
    slugs = [e["fiche"] for e in entrees]
    par_man = {e["fiche"]: e for e in entrees}
    lus = [x for x in lire_regle(open(memory_path, encoding="utf-8").read())
           if x["classe"] == "entree"]
    par_carte = {x["fiche"]: x for x in lus}
    liens = set(par_carte)
    fiches = index_fiches(racine)
    compte = collections.Counter(slugs)
    communs = liens & set(slugs)
    ecart = lambda champ: sorted(s for s in communs
                                 if (par_man[s].get(champ) or "") != (par_carte[s].get(champ) or ""))
    return {
        "n_manifeste": len(entrees), "n_carte": len(liens),
        "carte_sans_manifeste": sorted(liens - set(slugs)),
        "manifeste_sans_carte": sorted(set(slugs) - liens),
        "positions_divergentes": sorted(s for s in communs
                                        if par_man[s].get("rang") != par_carte[s].get("rang")
                                        or (par_man[s].get("section") or "") != (par_carte[s].get("section") or "")),
        "niveaux_divergents": sorted(s for s in communs
                                     if par_man[s].get("niveau") != par_carte[s].get("niveau")),
        "annotations_divergentes": ecart("annotation"),
        "references_mortes": sorted(s for s in set(slugs) if s not in fiches),
        "doublons_manifeste": sorted(s for s, n in compte.items() if n > 1),
        **rangs_incoherents(entrees, par_carte),
        "budget_octets": man.get("budget_octets"),
        "taille_carte": os.path.getsize(memory_path),
    }


def rangs_incoherents(entrees, par_carte):
    """Deux contrôles de rang, et il a fallu les SÉPARER pour qu'aucun ne mente.

    ANGLE MORT FERMÉ LE 2026-08-28. Le manifeste portait 21 collisions de rang sur 41
    entrées — deux fiches se disant toutes deux « 1re de leur section » — et rien ici ne
    les voyait : `doublons_manifeste` compte des SLUGS répétés, jamais des RANGS répétés.
    Cause trouvée dans reconcilier.py : sous `--seulement`, la resynchronisation globale
    des rangs est volontairement désactivée pour éviter un débordement, si bien qu'un
    ajout prend son rang de la carte pendant que les autres gardent le leur.

    POURQUOI DEUX CONTRÔLES ET NON UN. « Les rangs forment 1..N » n'est PAS un invariant
    inconditionnel : le rang est la position dans la CARTE, et la carte contient des
    entrées que le manifeste ne déclare pas. Tant qu'il en manque une dans une section,
    les rangs y sont légitimement troués — exiger 1..N fabriquerait un rouge qui n'est
    la faute de personne. On distingue donc :

      · UNICITÉ — inconditionnelle. Deux entrées ne peuvent pas occuper une même place.
      · DOMAINE — seulement sur une section dont le manifeste couvre TOUTE la carte.

    Et l'un complète exactement l'autre : N entrées, rangs uniques, tous dans 1..N ⇒ c'est
    une permutation. Inutile de chercher les trous séparément, ils ne peuvent pas exister
    sans un doublon ou un rang hors domaine."""
    par_sec = collections.defaultdict(list)
    for e in entrees: par_sec[e.get("section") or ""].append(e)
    carte_par_sec = collections.defaultdict(set)
    for f, x in par_carte.items(): carte_par_sec[x.get("section") or ""].add(f)
    dupes, hors = [], []
    for sec, es in par_sec.items():
        n = collections.Counter(e.get("rang") for e in es)
        dupes += [e["fiche"] for e in es if e.get("rang") is None or n[e.get("rang")] > 1]
        couverte = not (carte_par_sec.get(sec, set()) - {e["fiche"] for e in es})
        if couverte:
            hors += [e["fiche"] for e in es
                     if not isinstance(e.get("rang"), int) or not (1 <= e["rang"] <= len(es))]
    return {"rangs_dupliques": sorted(set(dupes)),
            "rangs_hors_domaine": sorted(set(hors))}


def total(r):
    return sum(len(r[k]) for k in ("carte_sans_manifeste", "manifeste_sans_carte",
                                   "positions_divergentes", "niveaux_divergents",
                                   "annotations_divergentes",
                                   "references_mortes", "doublons_manifeste",
                                   "rangs_dupliques", "rangs_hors_domaine"))


# ── QUALIFIER UN ROUGE — ajouté le 2026-08-21 ────────────────────────────────
# LE DÉFAUT FERMÉ. Ce fichier imprimait « Ce rouge est ATTENDU au 2026-08-20 » sur
# N'IMPORTE QUEL rouge. Il transformait « une dette historique précise est connue »
# en « tout échec actuel est connu » — un rouge NEUF, jamais vu, héritait de la
# phrase rassurante d'une dette éteinte depuis. Même classe de faute que F1 : une
# exception bornée qui absorbe un écart nouveau. Constaté le 21/08 alors que HEAD
# était VERT et que la phrase s'imprimait quand même sur une dérive d'arbre de
# travail vieille de quelques minutes.
#
# L'INVARIANT :
#     Un rouge n'est ATTENDU que si son observable COURANT correspond exactement
#     à un témoin rouge EXPLICITEMENT ENREGISTRÉ.
#
# « q13 était rouge hier » n'est pas une preuve que q13 est rouge aujourd'hui —
# c'est le même énoncé que tools/temoins-bancs.json, appliqué à un autre banc.
#
# CE QUE LA QUALIFICATION NE FAIT PAS : elle n'ouvre aucune porte. `--check`
# refuse toujours sur la moindre divergence, témoin ou pas. Un rouge ATTENDU
# reste un rouge : le témoin l'EXPLIQUE, il ne l'EXCUSE pas. Élargir le gel
# serait une décision séparée, et elle ne se prend pas dans un correctif de
# message.

CATEGORIES = ("carte_sans_manifeste", "manifeste_sans_carte", "positions_divergentes",
              "niveaux_divergents", "annotations_divergentes", "references_mortes",
              "doublons_manifeste", "rangs_dupliques", "rangs_hors_domaine")


def observable(r):
    """L'observable d'un rouge : l'ENSEMBLE NOMMÉ de ses écarts, jamais leur nombre.

    Deux rouges de même total peuvent n'avoir aucun écart en commun. Comparer des
    compteurs laisserait un rouge neuf se faire passer pour l'ancien."""
    return {"%s:%s" % (cat, slug) for cat in CATEGORIES for slug in r.get(cat, ())}


def temoins_declares(chemin=None, banc="carte_divergence"):
    """Les écarts explicitement enregistrés pour ce banc. Registre absent ou muet
    → ensemble VIDE, donc tout rouge est NOUVEAU : le défaut penche du côté sûr."""
    chemin = chemin or os.path.join(BRAIN, "tools", "temoins-bancs.json")
    try:
        d = json.load(open(chemin, encoding="utf-8"))
        return set(d.get("temoins_par_banc", {}).get(banc, {}).get("ecarts", []))
    except Exception:
        return set()


def qualifier(courant, declares, mesure_fiable):
    """{statut, attendus, nouveaux, perimes}.

    statut : INCONNU  la mesure n'est pas digne de foi — on ne qualifie RIEN.
                      Une non-mesure n'est jamais un « rouge attendu ».
             NOUVEAU  au moins un écart courant n'est déclaré nulle part.
             ATTENDU  il y a du rouge, et chaque écart courant est déclaré.
             VERT     aucun écart courant.
    perimes : déclarés mais PLUS observés — le témoin a survécu à sa cause."""
    if not mesure_fiable:
        return {"statut": "INCONNU", "attendus": set(), "nouveaux": set(),
                "perimes": set(), "raison": "l'instrument n'a pas prouvé qu'il sait rougir"}
    nouveaux = courant - declares
    return {"statut": "NOUVEAU" if nouveaux else ("ATTENDU" if courant else "VERT"),
            "attendus": courant & declares, "nouveaux": nouveaux,
            "perimes": declares - courant, "raison": ""}


def rapport(r, titre="ÉTAT RÉEL"):
    print(f"── {titre} ──")
    print(f"   manifeste {r['n_manifeste']} entrées · carte {r['n_carte']} wikilinks distincts")
    for cle, lib in (("carte_sans_manifeste", "carte → manifeste MANQUANTS"),
                     ("manifeste_sans_carte", "manifeste → carte manquants"),
                     ("positions_divergentes", "POSITIONS divergentes (section/rang)"),
                     ("niveaux_divergents",   "NIVEAUX divergents (étoiles)"),
                     ("annotations_divergentes", "ANNOTATIONS divergentes"),
                     ("references_mortes",    "références MORTES (fiche introuvable)"),
                     ("doublons_manifeste",   "doublons dans le manifeste"),
                     ("rangs_dupliques",      "RANGS partagés par 2 entrées (même section)"),
                     ("rangs_hors_domaine",   "RANGS hors 1..N (section entièrement couverte)")):
        v = r[cle]
        print(f"   {lib:42} {len(v):3d}" + ("" if not v else ""))
        for x in v[:12]: print(f"        · {x}")
        if len(v) > 12: print(f"        … {len(v)-12} de plus")
    for slug, canon, concurrent, motif in getattr(index_fiches, "conflits", []) or []:
        print(f"   ⚠️  identité en conflit : {slug} — {concurrent} ({motif})")
    marge = r["budget_octets"] - r["taille_carte"]
    print(f"   budget : carte {r['taille_carte']} o / {r['budget_octets']} o — "
          f"marge {marge} o ({100*marge/r['budget_octets']:.1f} %)")
    print(f"   → divergence totale : {total(r)}")


# ── état réel, en lecture seule ─────────────────────────────────────────────
sha_avant = {p: sha(p) for p in (MEMORY, MANIFESTE)}
reel = analyser(MEMORY, MANIFESTE, BRAIN)
rapport(reel)

# ── sabotages, sur COPIES isolées ───────────────────────────────────────────
print("\n── SABOTAGES (sur copies ; les vrais fichiers ne sont jamais écrits) ──")
bac = tempfile.mkdtemp(prefix="d51-")
try:
    m_copie = os.path.join(bac, "MEMORY.md"); j_copie = os.path.join(bac, "manifeste.json")
    shutil.copy2(MEMORY, m_copie); shutil.copy2(MANIFESTE, j_copie)
    # racine factice : un fichier vide par slug du manifeste, dans une zone valide
    faux = os.path.join(bac, "racine"); os.makedirs(os.path.join(faux, "lessons"))
    man = json.load(open(j_copie, encoding="utf-8"))
    for e in man["entrees"]:
        open(os.path.join(faux, "lessons", e["fiche"] + ".md"), "w").close()
    base = analyser(m_copie, j_copie, faux)
    print(f"   référence : sur la racine factice, références mortes = {len(base['references_mortes'])}"
          f"  {'✅ 0' if not base['references_mortes'] else '⛔'}")

    # S1 — une entrée ajoutée à la carte, sans manifeste
    open(m_copie, "a", encoding="utf-8").write("\n- [[fiche-sabotage-s1-inexistante]]\n")
    s1 = analyser(m_copie, j_copie, faux)
    # COMPOSITION, PAS CARDINAL (corrigé le 2026-08-28, même classe d'erreur que S5).
    # `len(après) == len(avant) + 1` ne dit pas QUI est arrivé. Démontré par sabotage : un
    # instrument qui retire le vrai slug et en invente un autre garde le bon cardinal, et
    # S1 passait au VERT — le banc déclarait alors « sabotages ✅ » sur un instrument faux.
    # On exige donc l'ensemble exact des arrivées.
    neuf1 = set(s1["carte_sans_manifeste"]) - set(base["carte_sans_manifeste"])
    ok1 = neuf1 == {"fiche-sabotage-s1-inexistante"}
    print(f"   S1 entrée dans la carte sans manifeste : {len(base['carte_sans_manifeste'])} → "
          f"{len(s1['carte_sans_manifeste'])} · arrivée(s) {sorted(neuf1)}  "
          f"{'✅' if ok1 else '⛔ NON DÉTECTÉ'}")
    shutil.copy2(MEMORY, m_copie)

    # S2 — une entrée du manifeste absente de la carte
    man2 = json.load(open(j_copie, encoding="utf-8"))
    man2["entrees"].append({"fiche": "fiche-sabotage-s2", "section": "x", "rang": 999,
                            "niveau": 0, "annotation": "", "statut_attendu": None,
                            "date_statut": None})
    json.dump(man2, open(j_copie, "w", encoding="utf-8"), ensure_ascii=False)
    open(os.path.join(faux, "lessons", "fiche-sabotage-s2.md"), "w").close()
    s2 = analyser(m_copie, j_copie, faux)
    neuf2 = set(s2["manifeste_sans_carte"]) - set(base["manifeste_sans_carte"])
    ok2 = neuf2 == {"fiche-sabotage-s2"}          # composition, pas cardinal — cf. S1
    print(f"   S2 entrée du manifeste absente de la carte : {len(base['manifeste_sans_carte'])} → "
          f"{len(s2['manifeste_sans_carte'])} · arrivée(s) {sorted(neuf2)}  "
          f"{'✅' if ok2 else '⛔ NON DÉTECTÉ'}")
    shutil.copy2(MANIFESTE, j_copie); os.remove(os.path.join(faux, "lessons", "fiche-sabotage-s2.md"))

    # S3 — une fiche sélectionnée renommée/déplacée
    victime = man["entrees"][0]["fiche"]
    os.rename(os.path.join(faux, "lessons", victime + ".md"),
              os.path.join(faux, "lessons", victime + "-renommee.md"))
    s3 = analyser(m_copie, j_copie, faux)
    # COMPOSITION, PAS PRÉSENCE (corrigé le 2026-08-28, même classe que S1/S2/S5).
    # `victime in references_mortes` est satisfait par un instrument PARANOÏAQUE qui
    # déclare les 242 entrées mortes : la victime y est, puisque tout le monde y est.
    # Démontré — ce critère passait au VERT sur un tel instrument, et le banc annonçait
    # alors « sabotages ✅ » avant de rendre un verdict de 440 divergences.
    # On exige l'ensemble EXACT des arrivées : ni moins (aveugle), ni plus (paranoïaque),
    # ni d'autres noms (bon cardinal, mauvaises identités).
    neuf3 = set(s3["references_mortes"]) - set(base["references_mortes"])
    ok3 = neuf3 == {victime}
    print(f"   S3 fiche « {victime[:34]} » renommée : référence morte "
          f"· arrivée(s) {sorted(neuf3)}  {'✅ détectée' if ok3 else '⛔ NON DÉTECTÉE'}")
    os.rename(os.path.join(faux, "lessons", victime + "-renommee.md"),
              os.path.join(faux, "lessons", victime + ".md"))

    # S5 — LA FAUTE HISTORIQUE : l'annotation de D1 réattribuée à D2, comme avant D5.2c.
    # Elle avait vécu 2 jours sans être vue, parce qu'on ne comparait que les ensembles.
    man5 = json.load(open(j_copie, encoding="utf-8"))
    d1 = next((e for e in man5["entrees"] if e["fiche"].startswith("carte-d1-")), None)
    d2 = next((e for e in man5["entrees"] if e["fiche"].startswith("carte-d2-")), None)
    if d1 and d2:
        # LE SABOTAGE POSE SON MATÉRIAU ET MESURE SES VRAIES VICTIMES (corrigé le 28/08).
        #
        # Il empruntait l'annotation RÉELLE de D1 dans le manifeste, puis exigeait un
        # changement de composition sur D1 ET D2. Deux fautes couplées, révélées en
        # simulant une décision parfaitement légitime — retirer l'annotation de D1 parce
        # qu'elle est redondante avec sa fiche :
        #   · sans annotation à déplacer, l'échange ne déplace plus rien et le sabotage
        #     devient insatisfiable — S5 rougissait alors qu'AUCUN instrument n'était en
        #     cause, et le banc refusait un manifeste pourtant à divergence nulle ;
        #   · même en posant un témoin, D1 revient à son état d'origine et la seule
        #     victime observable est D2 : exiger D1 rendait le critère impossible.
        #
        # RÈGLE GÉNÉRALE QUE CE CAS IMPOSE : un sabotage ne doit jamais dépendre d'une
        # donnée de production qui a le droit de disparaître. Il fabrique son matériau.
        #
        # `_av` se lit AVANT la pose du témoin : c'est l'état auquel `base` a été mesurée.
        # Le lire après décalerait la référence d'un cran et compterait D1 comme victime
        # alors que la mesure de base ne peut pas le voir bouger.
        _av = {e["fiche"]: (e.get("annotation") or "") for e in man5["entrees"]}
        if not (d1.get("annotation") or ""):
            d1["annotation"] = "TÉMOIN-S5 posé par le banc"
        d2["annotation"], d1["annotation"] = d1["annotation"], ""
        _ap = {e["fiche"]: (e.get("annotation") or "") for e in man5["entrees"]}
        _victimes = {f for f in (d1["fiche"], d2["fiche"]) if _av[f] != _ap[f]}
        json.dump(man5, open(j_copie, "w", encoding="utf-8"), ensure_ascii=False)
        s5 = analyser(m_copie, j_copie, faux)
        # DIFFÉRENCE SYMÉTRIQUE, PAS DIFFÉRENCE SIMPLE (corrigé le 2026-08-28).
        #
        # La faute injectée est une RÉATTRIBUTION : l'annotation QUITTE D1 et ARRIVE sur
        # D2. Sa signature est donc un DÉPART et une ARRIVÉE. Mesuré sur l'état du jour :
        #     avant {carte-d1, carte-d3, heldout}  →  après {carte-d2, carte-d3, heldout}
        # D1 SORT de l'ensemble, D2 y ENTRE, et le cardinal ne bouge pas.
        #
        # `après − avant` ne regarde que les ARRIVÉES : il ne rend que {D2} et exige
        # pourtant {D1, D2}. Ce critère ne pouvait pas être satisfait, quelle que soit la
        # qualité de l'instrument — et il a fait déclarer `sabotages ⛔ DÉFAILLANT` pendant
        # huit jours, donc refuser toute qualification du rouge de la carte.
        #
        # ⚠️ CE N'EST PAS UN ASSOUPLISSEMENT POUR OBTENIR DU VERT. Contre-épreuve exécutée :
        # avec un instrument RÉELLEMENT aveugle (annotations_divergentes toujours vide),
        # la différence symétrique est VIDE, ne contient pas les victimes, et S5 ÉCHOUE.
        # Le critère passe avec l'instrument sain et tombe avec l'instrument aveugle : il
        # mesure donc quelque chose. L'ancien, lui, tombait dans les deux cas.
        #
        # LEÇON DE MÉTHODE : un sabotage qui ne peut pas réussir est indiscernable d'un
        # instrument qui ne peut pas voir. Tout critère de sabotage doit être éprouvé
        # DANS LES DEUX SENS — sain ⇒ passe, aveugle ⇒ échoue.
        avant5 = set(base["annotations_divergentes"])
        apres5 = set(s5["annotations_divergentes"])
        ok5 = bool(_victimes) and (avant5 ^ apres5) >= _victimes
        print(f"   S5 faute historique D1→D2 réinjectée : annotations divergentes "
              f"{sorted(avant5)} → {sorted(apres5)}")
        print(f"      composition changée sur {sorted(avant5 ^ apres5)} · victimes réelles "
              f"{sorted(_victimes)}  "
              f"{'✅ DÉTECTÉE' if ok5 else '⛔ INVISIBLE — le contrôle ne vaut rien'}")
        shutil.copy2(MANIFESTE, j_copie)
    else:
        ok5 = None; print("   S5 — entrées D1/D2 absentes, non testable")

    # S4 — tout restauré : on doit retomber exactement sur l'état de référence
    s4 = analyser(m_copie, j_copie, faux)
    ok4 = (s4 == base and sha(m_copie) == sha(MEMORY) and sha(j_copie) == sha(MANIFESTE))
    print(f"   S4 restauration exacte : état identique et SHA retrouvés  "
          f"{'✅' if ok4 else '⛔ DÉRIVE'}")
finally:
    shutil.rmtree(bac, ignore_errors=True)

# ── preuve de non-écriture ──────────────────────────────────────────────────
intacts = all(sha(p) == sha_avant[p] for p in sha_avant)
print(f"\n   vrais fichiers intacts après l'exécution : {'✅' if intacts else '⛔ MODIFIÉS'}")
print(f"     MEMORY.md    {sha_avant[MEMORY][:16]}…")
print(f"     manifeste    {sha_avant[MANIFESTE][:16]}…")

sabotages_ok = all(x is not False for x in (ok1, ok2, ok3, ok4, ok5)) and intacts

# ── SABOTAGES DE LA QUALIFICATION — logique pure, aucun fichier touché ───────
print("\n── SABOTAGES DE LA QUALIFICATION (T1–T6, en mémoire) ──")
_t = []
def _t_cas(titre, courant, declares, fiable, attendu_statut, verif=None):
    q = qualifier(set(courant), set(declares), fiable)
    ok = q["statut"] == attendu_statut and (verif is None or verif(q))
    _t.append(ok)
    print("   %s %-52s %s attendu, %s observé"
          % ("✅" if ok else "⛔", titre, attendu_statut, q["statut"]))
    return q

# T1 — le rouge historique EXACT, déclaré : il est ATTENDU.
_t_cas("T1 rouge historique exact, déclaré", ["a:x"], ["a:x"], True, "ATTENDU",
       lambda q: q["attendus"] == {"a:x"} and not q["nouveaux"] and not q["perimes"])
# T2 — un rouge que rien ne déclare : NOUVEAU, donc refusé.
_t_cas("T2 rouge neuf, aucun témoin", ["a:y"], [], True, "NOUVEAU",
       lambda q: q["nouveaux"] == {"a:y"})
# T3 — historique ET neuf ensemble : les deux DISTINGUÉS, pas fondus.
_t_cas("T3 historique + neuf : distingués", ["a:x", "a:y"], ["a:x"], True, "NOUVEAU",
       lambda q: q["attendus"] == {"a:x"} and q["nouveaux"] == {"a:y"})
# T4 — le témoin a survécu à sa cause : signalé PÉRIMÉ, et le banc reste vert.
_t_cas("T4 témoin déclaré, courant vert → périmé", [], ["a:x"], True, "VERT",
       lambda q: q["perimes"] == {"a:x"})
# T5 — instrument non fiable : INCONNU, JAMAIS « attendu ».
_t_cas("T5 mesure non fiable → INCONNU, jamais ATTENDU", ["a:x"], ["a:x"], False, "INCONNU",
       lambda q: not q["attendus"])
# T6 — LE PIÈGE DU COMPTEUR : même NOMBRE d'écarts, contenu entièrement différent.
#      Une qualification par total dirait « attendu ». Par observable, elle refuse.
_t_cas("T6 même total, écarts tous différents", ["a:z"], ["a:x"], True, "NOUVEAU",
       lambda q: q["nouveaux"] == {"a:z"} and q["perimes"] == {"a:x"})
qualif_ok = all(_t)
print("   %s" % ("✅ la qualification sait refuser un rouge neuf, et sait se taire"
                 if qualif_ok else "⛔ DÉFAILLANTE — elle ne prouve rien"))
# ── SABOTAGES DU CONTRÔLE DE RANG (R1–R5, logique pure) ─────────────────────
print("\n── SABOTAGES DU CONTRÔLE DE RANG (R1–R5, en mémoire) ──")
_r = []
def _r_cas(titre, entrees, carte_slugs, attendu_dupes, attendu_hors):
    par_carte = {f: {"section": "S"} for f in carte_slugs}
    q = rangs_incoherents(entrees, par_carte)
    ok = (bool(q["rangs_dupliques"]) == attendu_dupes) and (bool(q["rangs_hors_domaine"]) == attendu_hors)
    _r.append(ok)
    print("   %s %-54s dupes=%-5s hors=%-5s"
          % ("✅" if ok else "⛔", titre, bool(q["rangs_dupliques"]), bool(q["rangs_hors_domaine"])))

_e = lambda *rangs: [{"fiche": "f%d" % i, "section": "S", "rang": r} for i, r in enumerate(rangs)]
# R3 d'abord : sans un VERT de référence, quatre rouges ne prouvent rien.
_r_cas("R3 permutation exacte 1..N → VERT", _e(1, 2, 3), ["f0", "f1", "f2"], False, False)
_r_cas("R1 deux entrées au même rang → ROUGE", _e(1, 2, 2), ["f0", "f1", "f2"], True, False)
# R2 : trou 1,2,4 sur 3 entrées → le 4 est hors domaine. Le trou n'a pas besoin d'être
#      cherché : il ne peut exister sans un doublon ou un rang hors bornes.
_r_cas("R2 trou dans la séquence → ROUGE (section couverte)", _e(1, 2, 4), ["f0", "f1", "f2"], False, True)
# R4 : LE PIÈGE DU COMPTEUR — 3 entrées, 3 rangs, cardinal juste, identités fausses.
_r_cas("R4 bon cardinal mais rangs dupliqués → ROUGE", _e(2, 2, 3), ["f0", "f1", "f2"], True, False)
# R5 : CONTRE-ÉPREUVE INVERSE — le contrôle doit se TAIRE quand le trou est légitime :
#      la carte porte une 4e entrée que le manifeste ne déclare pas encore.
_r_cas("R5 trou légitime (section non couverte) → SILENCE", _e(1, 2, 4),
       ["f0", "f1", "f2", "pas-au-manifeste"], False, False)
rangs_ok = all(_r)
print("   %s" % ("✅ le contrôle de rang voit les collisions et ne fabrique pas de faux rouge"
                 if rangs_ok else "⛔ DÉFAILLANT"))

print("\n" + "─" * 74)
q = qualifier(observable(reel), temoins_declares(), sabotages_ok and rangs_ok)

if total(reel):
    print(f"⛔ DIVERGENCE : {total(reel)} écart(s). Le manifeste ne représente plus la carte.")
    if q["statut"] == "INCONNU":
        print(f"   ⛔ STATUT INCONNU — {q['raison']}.")
        print("      Ce rouge n'est PAS qualifié d'attendu : on ne sait pas ce qu'on mesure.")
    elif q["statut"] == "NOUVEAU":
        print(f"   🆕 ROUGE NOUVEAU — {len(q['nouveaux'])} écart(s) qu'AUCUN témoin ne déclare :")
        for x in sorted(q["nouveaux"])[:8]: print(f"        · {x}")
        if len(q["nouveaux"]) > 8: print(f"        … {len(q['nouveaux'])-8} de plus")
        if q["attendus"]:
            print(f"   ⓘ  et {len(q['attendus'])} écart(s) déclarés, distingués de ceux-ci.")
        print("      Un rouge neuf n'hérite pas de la phrase d'une dette ancienne.")
    else:
        print(f"   ⓘ  ROUGE ATTENDU — les {len(q['attendus'])} écarts sont tous déclarés dans")
        print("      tools/temoins-bancs.json. Le témoin EXPLIQUE ce rouge, il ne l'EXCUSE pas :")
        print("      --check refuse quand même. Ne pas 'corriger' le test pour l'éteindre.")
else:
    print("✅ manifeste et carte disent la même chose")

if q["perimes"]:
    print(f"   ⚠️  {len(q['perimes'])} TÉMOIN(S) PÉRIMÉ(S) — déclarés, plus observés :")
    for x in sorted(q["perimes"])[:8]: print(f"        · {x}")
    print("      Un témoin qui a survécu à sa cause couvre un état que personne ne regarde.")

print(f"instrument : sabotages {'✅ tous rouges quand ils doivent' if sabotages_ok else '⛔ DÉFAILLANT'}"
      f" · qualification {'✅' if qualif_ok else '⛔ DÉFAILLANTE'}"
      f" · contrôle de rang {'✅' if rangs_ok else '⛔ DÉFAILLANT'}")
sys.exit(1 if ("--check" in sys.argv
               and (total(reel) or not sabotages_ok or not qualif_ok or not rangs_ok)) else 0)
