#!/usr/bin/env python3
"""brain_recall — récupération par pertinence dans le C Brain (Volet 2 · Horizon 1).

FONDATION du rappel sémantique : au lieu de charger MEMORY.md en entier à chaque
session, on récupère le top-k des fiches PERTINENTES pour une requête.

Backend v0 = BM25 lexical (pur Python, ZÉRO dépendance, ZÉRO API, instantané).
Architecture enfichable : un backend `Embedding` (sentence-transformers local) pourra
remplacer/compléter BM25 sans toucher l'appelant — c'est l'upgrade « vrai sémantique ».

Usage :
  brain_recall.py "rotation main capteur profondeur"        → top-k fiches
  brain_recall.py -k 8 "facturation coûts IA"
  brain_recall.py --json "..."                              → sortie machine
"""
import os, re, sys, json, math, glob, hashlib, unicodedata
from collections import Counter

# ⚠️ LA DÉFINITION DU CORPUS N'EST PAS ÉCRITE ICI — elle vit dans brain_corpus.py, et les
# deux moteurs (BM25 et embeddings) l'importent. Elle a existé en double jusqu'au
# 2026-08-16 et les deux copies avaient divergé de 65 documents sans que rien ne le voie.
# Les noms sont ré-exportés tels quels : `br.SKIP_DIRS` reste valide pour ses appelants
# (tests/pas_de_fuite_evaluation.py notamment).
from brain_corpus import (  # noqa: E402
    BRAIN, SKIP_DIRS, SKIP_PREFIX, SKIP_FILES, skip as _skip, indexable as _indexable_de,
)
STOP = set("""
au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me meme
mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi
ton tu un une vos votre vous c d j l m n s t y est sont a as ai ont pas plus tres etre fait
le la les un une que qui pour dans sur avec sans est the and for with not are was you your
""".split())


def fold(s):
    """minuscule + sans accents (robustesse FR : 'résumé' ~ 'resume')."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Racinisation légère du français. Sans elle, « ranger » et « rangement » sont deux
# tokens étrangers l'un à l'autre : la requête « comment ranger une fiche du brain » ne
# touchait pas jardinage-regles.md, dont la description dit « rangement ». BM25 ne ratait
# pas la fiche par manque de finesse, il la ratait par absence de recouvrement lexical.
#
# Deux temps, et l'ordre est le cœur du correctif :
#   1. le PLURIEL d'abord, sinon « fiche » et « fiches » ne se rejoignent jamais
#      (« fiches » tombait sur la règle -es et donnait « fich », « fiche » restait
#      « fiche ») — c'est le mot le plus fréquent du tronc, le rater ruine tout ;
#   2. puis UN SEUL suffixe, du plus long au plus court, et seulement si la racine
#      garde au moins 4 lettres.
# Volontairement conservateur : un stemmer gourmand fabrique des collisions silencieuses
# qui abîment toutes les autres requêtes. Les suffixes ambigus sont donc absents — -re
# donnait « mesure » → « mesu », -es et -ee font doublon avec l'étape 1.
_SUFFIXES = sorted((
    "issement", "ellement", "ications", "ication", "atrice", "ateur", "ation",
    "ement", "ance", "ence", "isme", "iste", "euse", "able", "ible", "aire",
    "ite", "ive", "age", "ure", "eur",
    # formes verbales courantes
    "eraient", "erions", "assent", "erais", "erait", "erons", "eront", "aient",
    "ant", "ent", "ons", "ier", "ez", "er", "ir",
), key=len, reverse=True)
_MIN_RACINE = 4          # en dessous, la racine ne veut plus rien dire


# Memoise : un corpus repete son vocabulaire sans relache — 835 tokens distincts
# pour 8 013 occurrences dans un seul fichier, donc 90 % des appels ci-dessous
# sont redondants. Le cout de la racinisation se paie a la construction FROIDE de
# l'index, c'est-a-dire au premier prompt apres qu'une fiche a change, et
# tests/recall_benchmark.py tient ce temps sous seuil. Le dictionnaire est borne
# par le VOCABULAIRE du tronc, pas par sa taille en octets : il cesse de grossir
# bien avant le corpus.
_STEM_CACHE = {}


def stem(t):
    cached = _STEM_CACHE.get(t)
    if cached is not None:
        return cached
    _STEM_CACHE[t] = s = _stem(t)
    return s


def _stem(t):
    if len(t) <= 4:
        return t
    # Pluriel : le « s » seulement. Retirer un « x » final visait les pluriels
    # français en -aux/-eux, mais le tronc est bilingue et ça MUTILE les mots
    # anglais : « outbox » → « outbo », « index » → « inde ». Le gain sur
    # « journaux » ne vaut pas ce dégât ; attrapé par tests/recall_cache.py du
    # paquet, que mes propres essais n'avaient pas vu.
    if t.endswith("s") and len(t) > 4:             # 1. pluriel
        t = t[:-1]
    for suf in _SUFFIXES:                          # 2. un seul suffixe
        if t.endswith(suf) and len(t) - len(suf) >= _MIN_RACINE:
            return t[: -len(suf)]
    return t


# Alias français ↔ anglais. Le tronc est écrit dans les deux langues : « offline » est
# dans 37 fiches, « queue » dans 27, « deploy » dans 54 — mais on tape « hors ligne »,
# « file d'attente », « déploiement ». AUCUN stemmer ne franchit une TRADUCTION : mesuré,
# « l app terrain plante hors ligne » laissait offline-first-queue-pattern au-delà du
# rang 20 avec ou sans racinisation ; avec ces alias il remonte au rang 4.
# Appliqué AVANT la racinisation, pour que corpus et requête soient normalisés pareil.
# Table courte et justifiée par le corpus : on n'ajoute un couple que si les deux mots y
# sont réellement présents — pas de vocabulaire inventé.
_ALIAS = {
    r"hors[- ]ligne": "offline",
    r"file d[' ]attente": "queue",
    r"\bsauvegarde\w*": "backup",
    r"\bdeploiement\w*": "deploy",
    r"\bdeploy(?:er|ee?s?)\b": "deploy",
    r"mise en production": "deploy",
    r"\bmemoire cache\b": "cache",
}
# UNE passe, pas une par couple. Sept `sub()` separes parcouraient le document
# sept fois ; une alternation unique le parcourt une fois et aiguille sur le
# groupe qui a matche. Le motif le plus long reste en tete — Python essaie les
# alternatives de gauche a droite a chaque position, donc l'ordre qui rendait la
# version sequentielle correcte garde la version combinee correcte.
_ALIAS_COUPLES = sorted(_ALIAS.items(), key=lambda kv: -len(kv[0]))
_ALIAS_RE = re.compile("|".join(f"({k})" for k, _ in _ALIAS_COUPLES))
_ALIAS_CANON = [v for _, v in _ALIAS_COUPLES]


def aliaser(txt):
    return _ALIAS_RE.sub(lambda m: _ALIAS_CANON[m.lastindex - 1], txt)


def tokenize(text):
    return [stem(t) for t in re.findall(r"[a-z0-9]+", aliaser(fold(text)))
            if len(t) > 2 and t not in STOP]


def strip_md(text):
    text = re.sub(r"^---\n.*?\n---", "", text, flags=re.S)   # frontmatter
    text = re.sub(r"```.*?```", " ", text, flags=re.S)        # blocs code
    return text


def _indexable():
    """Les .md que le rappel considère, triés — l'entrée de l'empreinte."""
    return _indexable_de(BRAIN)


def _fingerprint(files):
    """Identité du contenu indexable du tronc : chemin, mtime, taille.

    Un stat() par fichier, quelques millisecondes — contre les ~200 ms qu'il
    faut pour les lire et les tokeniser. Hacher le contenu obligerait à tout
    lire, c'est-à-dire exactement le coût qu'on évite.
    """
    h = hashlib.sha256()
    for rel, p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        h.update(f"{rel}\0{st.st_mtime_ns}\0{st.st_size}\0".encode())
    # ⚠️ LE REGISTRE DES FAMILLES FAIT PARTIE DU TEXTE INDEXÉ, IL DOIT DONC ÊTRE DANS
    # L'EMPREINTE. Il n'est pas un `.md` : sans cette ligne, corriger un lexique ne change
    # rien à l'empreinte, le cache d'avant est relu tel quel, et la correction est ignorée
    # EN SILENCE. Vécu le 2026-08-14 : deux mesures identiques au centième après avoir changé
    # le lexique ET le poids — je mesurais l'index d'avant en croyant mesurer le neuf.
    # On hache son CONTENU (quelques Ko), pas son mtime : un `git checkout` du registre remet
    # un mtime neuf sur un contenu identique, et rejetterait le cache pour rien.
    try:
        with open(os.path.join(BRAIN, "meta", "familles.json"), "rb") as f:
            h.update(b"\0familles\0"); h.update(f.read())
    except OSError:
        h.update(b"\0familles\0absent")
    # Même raison pour la configuration : sa section `index` (poids du nom, de la
    # description, du pont) décide du TEXTE tokenisé. Sans cette ligne, changer un poids
    # relirait le cache d'avant et la modification serait ignorée en silence — exactement
    # l'incident du 14/08 ci-dessus. On hache le fichier ENTIER plutôt que la seule section
    # `index` : découper le hachage sur une partie du contenu est le genre de finesse qui
    # se désynchronise du jour où quelqu'un déplace une clé. Le coût est une reconstruction
    # d'index (~0,4 s) après une retouche de poids qui n'en avait pas besoin. C'est le bon
    # sens de l'erreur : reconstruire pour rien est gratuit, servir un index périmé ne l'est pas.
    try:
        with open(os.path.join(BRAIN, "config", "ranking.json"), "rb") as f:
            h.update(b"\0ranking\0"); h.update(f.read())
    except OSError:
        h.update(b"\0ranking\0absent")
    return h.hexdigest()


# Incrémenté dès que la tokenisation ou la forme d'un document change, pour
# qu'un vieux cache soit jeté au lieu de servir en silence des fiches notées
# selon les règles précédentes.
#   v2 (2026-08-12) : racinisation + alias FR/EN dans tokenize().
#   v3 (2026-08-12) : les documents portent redirectsTo / relations.remplace.
#   v4 (2026-08-14) : le texte indexé inclut le pont de vocabulaire des familles thématiques.
#   v5 (2026-08-14) : le registre des familles entre dans l'empreinte (cf. _fingerprint) —
#       sans ça, toute retouche de lexique était ignorée en silence.
#   v6 (2026-08-15) : les poids d'indexation viennent de config/ranking.json, qui entre
#       lui aussi dans l'empreinte. Les VALEURS n'ont pas bougé (3/3/1) : un cache v5 et un
#       cache v6 contiennent les mêmes documents. On incrémente quand même, parce qu'un
#       numéro de version qui ne bouge pas quand la SOURCE des poids change est un piège
#       posé pour la prochaine fois.
_CACHE_VERSION = 6


# ---------------------------------------------------------------- configuration du classement
# POURQUOI CE BLOC. Les poids vivaient en dur ici : personne ne pouvait les lire sans lire
# le moteur, et aucun résultat ne pouvait dire d'où venait son score. Ils sortent dans
# config/ranking.json — À COMPORTEMENT IDENTIQUE, c'est la condition de l'opération, et
# tests/golden_recall.py la vérifie.
#
# Les défauts ci-dessous ne sont pas décoratifs : ce sont EXACTEMENT les anciennes valeurs
# en dur. Fichier absent, illisible ou tronqué → le rappel classe comme avant. Une
# configuration ne doit jamais pouvoir mettre le rappel en panne ; au pire elle ne s'applique pas.
_DEFAUTS = {
    "version": "ranking-v1-defaut",
    "index": {"poids_nom": 3, "poids_description": 3, "poids_pont_familles": 1},
    "bm25": {"k1": 1.5, "b": 0.75},
    "utilite": {"alpha": 0.0},   # M5 : hors classement (ADR-0018)
    "exploration": {"denominateur": 3, "seuil_peu_proposee": 3},
}
_CONFIG_CACHE = None


def config():
    """Poids du classement, fusionnés sur les défauts. Chargés une fois par processus.

    Fusion CLÉ PAR CLÉ et non remplacement de section : un fichier qui ne redéfinit que
    `utilite.alpha` ne doit pas faire disparaître `bm25.k1`. Les clés commençant par `_`
    sont de la documentation (le fichier est fait pour être lu par un humain), jamais des
    paramètres — elles sont ignorées ici.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _DEFAUTS.items()}
    try:
        with open(os.path.join(BRAIN, "config", "ranking.json"), encoding="utf-8") as f:
            brut = json.load(f)
        for section, valeurs in brut.items():
            if section.startswith("_"):
                continue
            if isinstance(valeurs, dict) and isinstance(cfg.get(section), dict):
                for cle, val in valeurs.items():
                    if not cle.startswith("_") and isinstance(val, (int, float)):
                        cfg[section][cle] = val
            elif not isinstance(valeurs, dict):
                cfg[section] = valeurs
    except Exception:
        pass        # absent / illisible / cassé : on classe avec les défauts, sans bruit
    _CONFIG_CACHE = cfg
    return cfg


def load_corpus():
    """Fiches tokenisées, depuis un cache tant que le tronc n'a pas bougé.

    POURQUOI C'EST CACHÉ. Ceci tourne à CHAQUE prompt, via le hook de rappel.
    Sans cache, il relisait et retokenisait tout le tronc à chaque fois :
    214 ms sur un tronc de 241 fiches, et ça croît linéairement — environ 1,6 s
    à 5000 fiches. L'utilisateur payait ça à chaque message, et rien ne l'aurait
    jamais signalé, puisque le rappel restait parfaitement correct. Il devenait
    simplement plus lent chaque semaine.

    JSON plutôt que pickle : le cache est un fichier sur disque, et un format
    capable d'exécuter du code au chargement ne vaut pas quelques millisecondes.
    """
    files = _indexable()
    fp = _fingerprint(files)
    cache = os.path.join(BRAIN, "state", "recall-index.json")

    try:
        with open(cache, encoding="utf-8") as f:
            blob = json.load(f)
        if blob.get("fingerprint") == fp and blob.get("version") == _CACHE_VERSION:
            return blob["docs"]
    except Exception:
        pass        # absent, illisible, tronqué : on reconstruit, jamais d'échec

    docs = _read_corpus(files)

    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        # Atomique : un hook tué en pleine écriture ne doit pas laisser un
        # demi-fichier que la fois suivante lira comme faisant autorité.
        # ... mais l'écriture atomique a un angle mort : si le hook est tué ENTRE
        # l'ouverture et le `replace`, le `.tmp` reste, et personne ne le ramasse
        # jamais. Deux orphelins retrouvés le 2026-09-22, 4,4 Mo, écrits le 09/09 et
        # le 21/09 par des PID morts depuis. On balaie donc les siens avant d'écrire.
        # Le test est la MORT DU PROCESSUS, pas l'âge du fichier : une indexation qui
        # dure ne doit pas se faire effacer son propre brouillon par une voisine.
        for orphelin in glob.glob(f"{cache}.*.tmp"):
            try:
                os.kill(int(orphelin.rsplit(".", 2)[-2]), 0)
            except (ValueError, IndexError):
                continue                    # nom inattendu : on n'y touche pas
            except ProcessLookupError:
                try:
                    os.remove(orphelin)     # son écrivain est mort, le brouillon ne sert plus
                except OSError:
                    pass
            except PermissionError:
                continue                    # vivant, mais à un autre utilisateur
        tmp = f"{cache}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": _CACHE_VERSION, "fingerprint": fp, "docs": docs}, f)
        os.replace(tmp, cache)
    except Exception:
        pass        # tronc en lecture seule, disque plein : le rappel marche, en plus lent

    return docs


# ── le registre des familles thématiques (libellé + lexique). La VÉRITÉ des appartenances
# vit dans le `tags:` de chaque fiche ; ce fichier ne porte que le pont de vocabulaire.
def _charger_familles():
    p = os.path.join(BRAIN, "meta", "familles.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("familles", {})
    except Exception:
        return {}          # registre absent = axe thématique inactif, jamais une exception


_FAMILLES = _charger_familles()


def _fm_tags(fm):
    m = re.search(r"^tags:\s*\[(.*?)\]", fm, re.M)
    return [t.strip() for t in m.group(1).split(",") if t.strip()] if m else []


def _read_corpus(files):
    docs = []
    for rel, p in files:
        try:
            raw = open(p, encoding="utf-8").read()
        except Exception:
            continue
        fm = re.match(r"^---\n(.*?)\n---", raw, re.S)
        name = re.search(r"^name:\s*(.+)$", fm.group(1), re.M) if fm else None
        desc = re.search(r'^description:\s*"?(.+?)"?\s*$', fm.group(1), re.M) if fm else None
        body = strip_md(raw)
        # ── AXE THÉMATIQUE (2026-08-14) : le tag ouvre un PONT DE VOCABULAIRE ──
        # `strip_md()` supprime tout le frontmatter : un `tags:` y était donc écrit et lu par
        # PERSONNE. Mesuré avant ce correctif : « faux positif » ne remontait AUCUNE des 52 fiches
        # de la famille qui porte ce nom — le concept le plus central du tronc était introuvable
        # par son propre nom.
        # Et ce n'est pas le tag lui-même qui répare ça : personne ne tape « controle-qui-ment ».
        # C'est le LEXIQUE de la famille (meta/familles.json) — les mots qu'on tape vraiment,
        # que les fiches n'emploient pas — dont la fiche taguée hérite ici.
        # ⚠️ POIDS ×1, PAS ×2. Mesuré : à ×2, une fiche qui HÉRITE d'un mot par sa famille
        # passait devant une fiche qui l'ÉCRIT dans sa description — la requête « faux positif »
        # perdait `une-assertion-negative…` au profit de fiches qui ne parlent pas de ça.
        # Le pont doit rattraper ce que les mots ratent, jamais couvrir ce qu'ils trouvent.
        tags = _fm_tags(fm.group(1) if fm else "")
        cfg_idx = config()["index"]
        pont = ""
        for t in tags:
            f = _FAMILLES.get(t)
            if f:
                pont += " " + f["titre"] + " " + " ".join(f["lexique"])
        pont = (pont + " ") * int(cfg_idx["poids_pont_familles"])
        boosted = ((name.group(1) + " ") * int(cfg_idx["poids_nom"]) if name else "") + \
                  ((desc.group(1) + " ") * int(cfg_idx["poids_description"]) if desc else "") + \
                  pont + " " + body
        # `mots_pont` sert UNIQUEMENT à --explain : savoir si une fiche doit sa place au
        # pont de vocabulaire plutôt qu'à ses propres mots est la question qu'on se pose en
        # premier quand un résultat surprend. Ce n'est pas un terme du score.
        mots_pont = sorted(set(tokenize(pont)))
        docs.append({
            "path": rel,
            # succession : cette fiche est-elle un alias (redirectsTo) et/ou en
            # remplace-t-elle d'autres (relations.remplace) ? cf. _perimees()
            "redirige_vers": _fm_champ(raw, "redirectsTo"),
            "remplace": _fm_remplace(raw),
            "name": name.group(1).strip() if name else os.path.basename(rel)[:-3],
            "desc": desc.group(1).strip() if desc else "",
            "tokens": tokenize(boosted),
            "mots_pont": mots_pont,
        })
    return docs


# ---------------------------------------------------------------- boucle usage → classement
# Ce qui a DÉJÀ servi remonte. Le journal de rappel existait depuis des mois et personne ne
# le relisait : `inject_recall.py` l'ouvrait en « a » et rien ne le lisait — 2,3 % des
# fiches proposées étaient réellement ouvertes, et rien ne corrigeait ce taux.
# ⚠️ α N'EST PLUS UN PARAMÈTRE DE CLASSEMENT depuis le 2026-09-19 (ADR-0018, M5).
# Il l'a été du 2026-08 au 2026-09-19 : le score valait bm25 × (1 + α·ln(1+hits)), et α
# avait été MESURÉ, pas choisi — part du top-3 occupée par des fiches à historique, sur
# 10 requêtes : α=0 → 3/30 · 0,2 → 8/30 · 0,5 → 12/30 · 1,0 → 15/30.
# Ce qui a fermé le dossier n'est pas la valeur mais la RÉSOLUTION de l'instrument : sous
# 1 % d'écart lexical — la seule bande où un départage aurait le droit d'agir — l'ordre
# s'inverse une fois sur deux quand le corpus bouge. Dans cette bande, rien ne distingue
# le service du bruit, donc le bonus y est injustifiable, pas seulement petit.
# La constante reste lue ici pour ne pas casser ce qui l'importe (tests gelés, sondes),
# et vaut 0 dans config/ranking.json : même réintroduite par erreur, elle serait inerte.
ALPHA = config()["utilite"]["alpha"]
SEUIL_PEU_PROPOSEE = config()["exploration"]["seuil_peu_proposee"]
_UTILITE_CACHE = None


def _utilite():
    """{chemin: {sugg, hit}} produit par recall_feedback.py. Chargé une fois par processus.
    Absent = le rappel fonctionne exactement comme avant : jamais d'échec sur ce fichier."""
    global _UTILITE_CACHE
    if _UTILITE_CACHE is None:
        try:
            with open(os.path.join(BRAIN, "state", "recall-utilite.json"), encoding="utf-8") as f:
                _UTILITE_CACHE = json.load(f)
        except Exception:
            _UTILITE_CACHE = {}
    return _UTILITE_CACHE


# ---------------------------------------------------------------- succession de fiches
# `redirectsTo:` existait DÉJÀ dans le frontmatter (1 fiche) et n'était lu par PERSONNE :
# une fiche fusionnée restait donc l'égale de celle qui la remplace dans le rappel, et
# pouvait sortir devant elle. C'est la même relation que `relations.remplace` de
# jardinage-regles §4 bis, vue de l'autre bout — on lit les deux plutôt que d'inventer
# une convention concurrente.
_FM_REMPL = re.compile(r"^\s+remplace\s*:\s*\[([^\]]*)\]", re.M)


def _entete(raw):
    m = re.match(r"^---\n(.*?)\n---", raw, re.S)
    return m.group(1) if m else ""


def _fm_champ(raw, champ):
    m = re.search(rf"^\s*{champ}\s*:\s*[\"']?([^\"'\n]+)[\"']?\s*$", _entete(raw), re.M)
    return m.group(1).strip() if m else None


def _fm_remplace(raw):
    m = _FM_REMPL.search(_entete(raw))
    return [c.strip().strip("\"'") for c in m.group(1).split(",") if c.strip()] if m else []


def _perimees(docs):
    """Noms de fiches remplacées par une autre — retirées du rappel, jamais du disque.
    On n'écarte QUE si la fiche qui succède est réellement présente dans l'index :
    sinon une redirection cassée effacerait le savoir au lieu de le rediriger."""
    presents = {d["name"] for d in docs}
    morts = set()
    for d in docs:
        if d.get("redirige_vers") and d["redirige_vers"] in presents:
            morts.add(d["name"])                 # cette fiche-ci est un alias
        for cible in d.get("remplace") or ():
            if cible in presents and d["name"] in presents:
                morts.add(cible)                 # cette fiche-ci en remplace une autre
    return morts


class BM25:
    """Backend lexical v0 — Okapi BM25. Remplaçable par un backend embeddings."""
    def __init__(self, docs, k1=None, b=None):
        cfg = config()["bm25"]
        k1 = cfg["k1"] if k1 is None else k1
        b = cfg["b"] if b is None else b
        self.docs, self.k1, self.b = docs, k1, b
        self.N = len(docs)
        self.dl = [len(d["tokens"]) for d in docs]
        self.avgdl = (sum(self.dl) / self.N) if self.N else 0
        self.tf = [Counter(d["tokens"]) for d in docs]
        df = Counter()
        for d in docs:
            for t in set(d["tokens"]):
                df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def _contrib(self, i, t):
        """Contribution BM25 du terme `t` au document `i`.

        LA FORMULE N'EST ÉCRITE QU'ICI. Le classement servi et l'explication du score
        appellent la même fonction : il est donc impossible que le rappel explique un
        calcul et en serve un autre. Deux écritures de la même formule divergent toujours,
        et la divergence ne se voit pas — cf. [[un-detecteur-partage-par-concept]].
        """
        f = self.tf[i].get(t, 0)
        if not f:
            return 0.0
        denom = f + self.k1 * (1 - self.b + self.b * self.dl[i] / (self.avgdl or 1))
        return self.idf.get(t, 0) * (f * (self.k1 + 1)) / denom

    def classer(self, query, k=5, feedback=True):
        """Le classement AVEC sa décomposition — la source unique de search() et de --explain.

        Retourne une liste de dicts ordonnée, un par résultat retenu :
          doc · bm25 · detail_bm25 · hits · dernier · facteur_utilite · score ·
          exploration · rang

        Depuis M5 (ADR-0018) `score` EST `bm25` : `hits` et `dernier` sont des
        annotations d'usage, servies à côté du résultat et jamais dedans.

        `search()` n'en garde que (score, doc) pour ne rien casser chez ses appelants.
        """
        q = tokenize(query)
        scored = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                s += self._contrib(i, t)
            if s > 0:
                scored.append((s, d, i))
        if not scored:
            return []
        morts = _perimees(self.docs)
        if morts:
            vivants = [t for t in scored if t[1]["name"] not in morts]
            scored = vivants or scored        # jamais de résultat vide à cause du filtre
        util = _utilite() if feedback else {}
        ajuste = []
        for s, d, i in scored:
            # ADR-0018, mécanisme M5 — INSTALLÉ le 2026-09-19, décidé le 2026-08-30.
            # L'usage ne multiplie plus, ne départage plus, ne sélectionne plus : le rang
            # est le score lexical, et rien d'autre. `facteur_utilite` reste publié, figé
            # à 1,0, parce que des instruments gelés lisent la clé (tools/admin-L1) ; il
            # ne peut plus varier, donc il ne peut plus déplacer une fiche.
            u = util.get(d["path"], {})
            ajuste.append({"doc": d, "idx": i, "bm25": s,
                           "hits": u.get("hit", 0), "dernier": u.get("dernier"),
                           "facteur_utilite": 1.0, "score": s,
                           "exploration": False})
        ajuste.sort(key=lambda r: r["score"], reverse=True)

        def finir(retenues):
            """Détail par terme calculé UNIQUEMENT sur les résultats retenus.

            Le faire sur les centaines de fiches qui marquent un point coûterait à chaque
            prompt pour une information que personne ne lit. C'est le même `_contrib`, donc
            le détail ne peut pas raconter autre chose que le score.
            """
            for rang, r in enumerate(retenues, start=1):
                r["rang"] = rang
                r["detail_bm25"] = {t: round(self._contrib(r["idx"], t), 4)
                                    for t in q if self._contrib(r["idx"], t) > 0}
            return retenues

        if not util:
            return finir(ajuste[:k])

        # QUOTA D'EXPLORATION — 1 place sur 3. Sans lui, la boucle s'auto-renforce : une
        # fiche déjà ouverte remonte, donc elle est plus souvent proposée, donc plus
        # souvent ouverte. Les fiches rares mais justes disparaîtraient du rappel sans
        # que rien ne le signale. On réserve donc des places aux PEU proposées.
        cfg_ex = config()["exploration"]
        n_explo = k // int(cfg_ex["denominateur"])
        seuil = cfg_ex["seuil_peu_proposee"]
        retenues = ajuste[:k - n_explo]
        deja = {id(r["doc"]) for r in retenues}
        neuves = [r for r in ajuste[k - n_explo:]
                  if id(r["doc"]) not in deja
                  and util.get(r["doc"]["path"], {}).get("sugg", 0) < seuil]
        for r in neuves[:n_explo]:
            r["exploration"] = True               # cette place est due au quota, pas au score
            retenues.append(r); deja.add(id(r["doc"]))
        for r in ajuste[k - n_explo:]:            # pas assez de neuves : on complète normalement
            if len(retenues) >= k:
                break
            if id(r["doc"]) not in deja:
                retenues.append(r); deja.add(id(r["doc"]))
        return finir(retenues[:k])

    def search(self, query, k=5, feedback=True):
        """(score, doc) — la forme historique, pour ne rien casser chez les appelants."""
        return [(r["score"], r["doc"]) for r in self.classer(query, k, feedback)]


def _imprimer_explication(records, query, as_json):
    """« Pourquoi cette fiche, et pourquoi à cette place ? »

    HONNÊTETÉ DU SCHÉMA. On n'invente pas de composantes qui n'existent pas dans le
    calcul. Depuis M5 (ADR-0018, 2026-09-19) le score n'a plus qu'UNE composante, `bm25`.
    L'usage a donc quitté `composantes` pour `usage` : le laisser parmi les composantes
    à +0,00 aurait suggéré un terme qui vaut zéro aujourd'hui, alors qu'il n'existe plus.
    De même :
      • le pont des familles n'est PAS un terme du score : il est fondu dans le texte
        indexé, donc dans `bm25`. On publie les mots de la requête qui viennent de lui,
        ce qui répond à la vraie question (« cette fiche doit-elle sa place à ses propres
        mots ou à ceux de sa famille ? ») sans fabriquer un chiffre.
      • l'exploration n'est PAS un bonus numérique : c'est une PLACE réservée. On publie
        un booléen, parce que c'est ce que c'est.
    Publier `"family": 0.70` alors que rien dans le code ne calcule 0,70 serait une
    explication fausse — pire qu'une absence d'explication, parce qu'on s'y fierait.
    """
    cfg = config()
    sortie = []
    for r in records:
        d = r["doc"]
        pont = sorted(set(d.get("mots_pont") or []) & set(r["detail_bm25"]))
        sortie.append({
            "fiche": d["name"],
            "chemin": d["path"],
            "rang": r["rang"],
            "score_final": round(r["score"], 4),
            "composantes": {
                "bm25": round(r["bm25"], 4),
            },
            "usage": {
                "ouvertures_apres_suggestion": r["hits"],
                "derniere": r.get("dernier"),
            },
            "nature": {
                "utilite": "HORS CLASSEMENT (ADR-0018, M5) — annotation d'usage : "
                           "elle décrit le résultat, elle ne le déplace jamais",
                "pont_familles": "fondu dans bm25, jamais un terme séparé",
                "exploration": "place réservée, jamais un bonus de score",
            },
            "detail_bm25": dict(sorted(r["detail_bm25"].items(),
                                       key=lambda kv: kv[1], reverse=True)),
            "mots_venus_du_pont": pont,
            "place_exploration": r["exploration"],
            "config_version": cfg.get("version"),
        })
    if as_json:
        print(json.dumps(sortie, ensure_ascii=False, indent=2))
        return
    print(f"🔬 Décomposition du score pour « {query} »\n")
    for e in sortie:
        drapeau = "  ⟵ place d'exploration" if e["place_exploration"] else ""
        print(f"  #{e['rang']}  [{e['score_final']:6.2f}] {e['fiche']}{drapeau}")
        c, u = e["composantes"], e["usage"]
        quand = f", dern. {u['derniere']}" if u["derniere"] else ""
        print(f"        bm25 {c['bm25']:6.2f}   ← le rang, en entier")
        print(f"        usage : {u['ouvertures_apres_suggestion']} ouverture(s) après "
              f"suggestion{quand} — hors classement")
        if e["detail_bm25"]:
            termes = "  ".join(f"{t} {v:.2f}" for t, v in list(e["detail_bm25"].items())[:6])
            print(f"        termes : {termes}")
        if e["mots_venus_du_pont"]:
            print(f"        ⚠️  doit au pont des familles : {', '.join(e['mots_venus_du_pont'])}")
        print()
    print(f"  config : {sortie[0]['config_version'] if sortie else '—'}"
          f"  (config/ranking.json)")


def main():
    args = [a for a in sys.argv[1:]]

    # mode --semantic : délègue au backend embeddings (venv model2vec) s'il est dispo.
    # Défaut = BM25 (instantané, meilleur que les embeddings statiques à petite échelle).
    if "--semantic" in args:
        args.remove("--semantic")
        venv_py = os.path.join(BRAIN, ".venv", "bin", "python")
        embed = os.path.join(BRAIN, "hooks", "brain_embed.py")
        if os.path.exists(venv_py) and os.path.exists(embed):
            import subprocess
            os.execv(venv_py, [venv_py, embed, "query"] + args)
        # sinon : repli silencieux sur BM25

    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    explain = "--explain" in args
    if explain:
        args.remove("--explain")
    lignes = "--lignes" in args          # passages au lieu de descriptions (hooks/brain_lignes.py)
    if lignes:
        args.remove("--lignes")
    k = 5
    if "-k" in args:
        i = args.index("-k")
        try:
            k = int(args[i + 1]); del args[i:i + 2]
        except Exception:
            pass
    query = " ".join(args).strip()
    if not query:
        print('Usage : brain_recall.py [-k N] [--json] [--explain] [--lignes] "ta requête"'); sys.exit(1)

    if lignes:
        import brain_lignes
        moteur = BM25(load_corpus())
        res = moteur.classer(query, max(k, brain_lignes.REGLAGES["k"]))
        if not res:
            print(f"Aucune fiche pertinente pour : {query}"); return
        print(brain_lignes.rendre(moteur, tokenize, query, res), end="")
        return

    if explain:
        _imprimer_explication(BM25(load_corpus()).classer(query, k), query, as_json)
        return

    # `classer` et non `search` : depuis M5 (ADR-0018) l'usage est une ANNOTATION servie à
    # côté du résultat, et `search` ne rend que (score, doc) — elle la perdrait. Elle n'est
    # affichée QUE si la fiche a déjà été ouverte : une ligne « 0 ouverture » sur chaque
    # résultat serait du texte relu à chaque échange pour ne rien dire (sobriété en octets).
    # Le format compact injecté (`--lignes`) ne la porte pas, pour la même raison.
    results = BM25(load_corpus()).classer(query, k)
    if as_json:
        print(json.dumps([{"path": r["doc"]["path"], "name": r["doc"]["name"],
                           "desc": r["doc"]["desc"], "score": round(r["score"], 3),
                           "usage": {"ouvertures_apres_suggestion": r["hits"],
                                     "derniere": r.get("dernier")}}
                          for r in results], ensure_ascii=False, indent=2))
        return
    if not results:
        print(f"Aucune fiche pertinente pour : {query}"); return
    print(f"🔎 Top {len(results)} pour « {query} » :\n")
    for r in results:
        d = r["doc"]
        quand = f", dern. {r['dernier']}" if r.get("dernier") else ""
        usage = f"   · déjà ouverte {r['hits']}×{quand}" if r["hits"] else ""
        print(f"  [{r['score']:5.2f}] {d['name']}  ({d['path']}){usage}")
        if d["desc"]:
            print(f"          {d['desc'][:110]}")


if __name__ == "__main__":
    main()
