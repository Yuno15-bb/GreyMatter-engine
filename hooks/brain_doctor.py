#!/usr/bin/env python3
"""brain_doctor — healthcheck d'intégrité du C Brain.

Vérifie, sans rien modifier :
  1. liens [[x]] morts (en EXCLUANT les exemples de doc et les blocs de code),
  2. fiches orphelines (jamais ciblées par un lien),
  3. frontmatter complet (name / description / metadata.type) et name == nom de fichier,
  4. convention de nom kebab-case,
  5. présence dans la carte MEMORY.md + lessons/INDEX.md,
  6. taille de MEMORY.md sous le seuil de chargement sûr,
  7. drift git (modifs non commitées),
  8. relation typée dont le TYPE est hors vocabulaire (et dérive d'orthographe),
  9. relation typée qui pointe vers une fiche INEXISTANTE,
 10. sujet (`topic:`) absent, dédoublé, ou étranger aux 12 validés le 28/08.

LE DOCTEUR DIAGNOSTIQUE. IL NE RÉPARE JAMAIS, ET IL NE DÉFINIT JAMAIS.

Les contrôles 8, 9 et 10 portent sur des VOCABULAIRES, et aucun n'est écrit ici. Ils sont
IMPORTÉS de la pièce qui les possède déjà :

    relations:   hooks/graph_export.py   TYPES_RELATION (+ son propre analyseur)
    topic:       hooks/topics_fiche.py   qui lit meta/topics.json à chaque appel

C'est tout l'intérêt : une troisième copie d'un vocabulaire est une troisième chose avec
laquelle diverger — le tronc l'a déjà payé (deux moteurs de rappel indexant des corpus
différents en silence, un visualiseur lisant un champ que son exporteur n'écrivait pas,
et TROIS dialectes de relations mesurés le 17/08, cf. [[relations-typees-vocabulaire-divergent]]).
Un vocabulaire INJOIGNABLE fait dire au docteur que le contrôle n'a PAS tourné, au lieu de
rendre un arbre sain pour toujours (récolte J : deux vérificateurs incapables de rougir).

Usage :
  brain_doctor.py            → rapport lisible + exit 0 (sain) / 1 (anomalies)
  brain_doctor.py --json     → écrit state/doctor.json (pour les hooks) + exit code
  brain_doctor.py --quiet    → exit code seulement
"""
import os, re, sys, json, subprocess, glob, difflib

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from identite_fiche import identite, scanner   # noqa: E402

MEMORY = os.path.join(BRAIN, "MEMORY.md")
LESSONS_INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")
# ⚠ DEUX LIMITES, PAS UNE — et la PREMIÈRE ATTEINTE coupe, en silence.
#   Mesuré le 2026-08-25 sur le harnais 2.1.245 ([[carte-capacite-remesure-2026-08-25]],
#   protocole : carte d'essai sous une clé de projet SÉPARÉE, sentinelle en dernière ligne,
#   observable = le modèle cite la sentinelle ou ne la cite pas) :
#     · 200 lignes passent, 201 tronquent — QUELLE QUE SOIT la taille ;
#     · 24 000 octets passent, 30 000 tronquent (le harnais publie « limit: 24.4KB » ;
#       la frontière exacte en octets n'a jamais été mesurée, ne pas l'écrire comme un fait).
#   L'avertissement du harnais n'est visible QUE du modèle : jamais un code de sortie,
#   jamais un refus. D'où ces deux seuils, qui gardent la même prudence des deux côtés,
#   ~17 % sous la limite mesurée : 200 × 0,825 ≈ 165.
#   Jusqu'au 2026-09-20, SEULE la taille était surveillée. La limite qui a réellement
#   invalidé la projection D3 est celle des LIGNES (292 contre 200) : la dimension qui
#   mord n'était modélisée nulle part, et relever le seul seuil d'octets aurait rendu le
#   garde-fou vert sur une carte réellement tronquée.
MEMORY_WARN_BYTES = 20_000
MEMORY_WARN_LINES = 165
# ⚠ ET LE PLAFOND APPARTIENT AU HARNAIS, PAS À NOUS : il peut bouger d'une version à
#   l'autre sans prévenir, et le mode d'échec reste silencieux. La version sous laquelle
#   les deux limites ci-dessus ont été mesurées est donc écrite ici, et le docteur la
#   compare à celle qui tourne. C'est une information, pas une faute : elle n'a jamais le
#   droit de faire sortir le docteur en 1, sinon la moindre mise à jour de Claude Code
#   rougit un arbre sain et personne ne peut l'éteindre honnêtement (ADR-0016).
MEMORY_LIMITS_MEASURED_ON = "2.1.245"


def harness_version():
    """La version de Claude Code qui tourne, SANS lancer de processus.

    `claude --version` coûte un démarrage de node à chaque appel du docteur, et le
    docteur tourne dans des hooks. Deux lectures de fichier suffisent : l'installeur
    natif fait de `claude` un lien vers `…/versions/<version>`, et `~/.claude.json`
    garde la dernière version vue par l'accueil. Renvoie None si ni l'un ni l'autre
    ne répond — un plafond dont on ignore le harnais ne s'invente pas.
    """
    import shutil
    exe = shutil.which("claude")
    if exe:
        try:
            cible = os.path.basename(os.path.realpath(exe))
            if re.match(r"^\d+\.\d+\.\d+$", cible):
                return cible
        except OSError:
            pass
    try:
        with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as f:
            v = json.load(f).get("lastOnboardingVersion")
        if isinstance(v, str) and re.match(r"^\d+\.\d+\.\d+$", v):
            return v
    except (OSError, ValueError):
        pass
    return None
STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}
LINKED_DIRS = ("projects", "lessons", "life", "meta", "skills")           # zones tissées
# LES FICHES, au sens des deux axes de classement (686 le 17/09). `skills/` en est exclu :
# un SKILL.md vient du dehors (convention Claude Code, dossier `synced/` recopié depuis le
# compte) et n'a jamais été rangé par les lots de sujets du 27-28/08. Lui réclamer un
# `topic:` ferait 39 accusations sur des fichiers que personne n'a écrits ici — le défaut
# mesuré le 14/08 avec les 223 « famille inconnue », où la vraie pièce manquante se noyait.
ZONES_FICHES = ("projects", "lessons", "meta", "life")
# skip cohérent avec brain_recall/brain_embed : segments de DOSSIER (set) + préfixes (startswith).
# L'ancien `"sessions/archive" in parts` (token multi-segment vs segment unique) ne matchait JAMAIS
# → les ~130 notes d'archive + TIMELINE étaient comptées comme « fiches », polluant le compteur et
# la courbe metrics.jsonl. cf. [[scan-skip-par-segment-pas-substring]]
SKIP_DIRS = {".git", "node_modules", "capsule", "corpus", "audits", "state",
             # `archive/` = couche froide : ses journaux ne sont pas des fiches et
             # leurs [[liens]] gelés ne doivent pas polluer le compteur ni les liens morts.
             "archive",
             # `vision/` = documents sources de vision (cf. brain_corpus.py) : ni
             # fiches de savoir, ni tissés par [[liens]]. Les compter fausserait le
             # compteur de fiches et metrics.jsonl, et exigerait d'eux une place
             # dans la carte qu'ils ont déjà, mais comme SOURCE et non comme fiche.
             "vision",
             # `references/` et `_refs/` = ressources internes des skills, non des fiches
             "references",
             "_refs"}
SKIP_PREFIX = ("sessions",)   # toute la couche d'archive/timeline (≠ savoir tissé)
# tokens qui apparaissent comme [[...]] mais sont des EXEMPLES de doc, pas des liens
EXAMPLE_WHITELIST = {"slug", "nom-du-fichier", "exemples", "lien", "liens",
                     "...", "name", "class", "defined", "x", "their-name"}
INDEX_EXEMPT = {"MEMORY", "README", "TIMELINE"}


def md_files():
    out = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if any(rel.startswith(pre) for pre in SKIP_PREFIX):
            continue
        parts = rel.split(os.sep)[:-1]          # segments de DOSSIER (hors nom de fichier)
        if any(d in parts for d in SKIP_DIRS):
            continue
        out.append(p)
    return out


def strip_code(text):
    """Retire les blocs ``` et les spans `inline` pour ne pas lire les exemples."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    return text


def extract_links(text):
    return set(re.findall(r"\[\[([^\]|]+)", strip_code(text)))


def read(p):
    try:
        return open(p, encoding="utf-8").read()
    except Exception:
        return ""


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^(\w[\w.]*?):\s*(.*)$", line.strip())
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"')
    return fm


def _familles():
    """Le registre des familles, et POURQUOI il est vide s'il l'est.

    Un `except: return set()` nu confond deux états très différents : « le
    registre est là et ne contient rien » et « le registre est ABSENT ». Le
    second arrive pour de bon — meta/familles.json est resté hors de la liste
    blanche de sync.sh jusqu'au 2026-08-15, donc le paquet public embarquait
    les trois programmes qui le lisent sans le registre lui-même.

    Sans cette distinction, brain_doctor rougissait quand même, mais en
    disant 223 fois « famille inconnue ['controle-qui-ment'] » — un message
    qui accuse les FICHES alors que c'est la PIÈCE MAÎTRESSE qui manque.
    Cf. nommer-le-manque-ne-suffit-pas-nommer-l-etape-suivante.
    """
    p = os.path.join(BRAIN, "meta", "familles.json")
    try:
        with open(p, encoding="utf-8") as f:
            return set(json.load(f).get("familles", {})), None
    except FileNotFoundError:
        return set(), (f"meta/familles.json ABSENT ({p}) — le registre des familles "
                       "thématiques ne suit pas le code qui le lit ; le rappel perd son "
                       "pont de vocabulaire, sans autre signe. → restaure-le : "
                       "`git checkout meta/familles.json` dans le tronc, ou relance "
                       "./install.sh (le paquet le livre dans skeleton/meta/).")
    except Exception as e:
        return set(), (f"meta/familles.json illisible ({p}) : {e} — le registre est là "
                       "mais ne se charge pas ; répare le JSON avant de juger les tags.")


FAMILLES, FAMILLES_ERREUR = _familles()

def _vocabulaire_relations():
    """Les types de relation valides + l'analyseur qui les lit, EMPRUNTÉS à graph_export.

    Pourquoi emprunter plutôt que recopier : l'exporteur du graphe filtre déjà sur cette
    liste, et il le fait EN SILENCE — un type hors liste ne lève rien, la qualification du
    lien disparaît de la carte comme si personne ne l'avait écrite (mesuré le 17/08 :
    65 qualifications perdues, 0 relation reconnue sous le moteur public). Le docteur dit
    ici, fiche par fiche, ce que l'exporteur jette sans un mot ; s'il jugeait sur SA propre
    liste, il rougirait sur des relations que l'exporteur accepte, et se tairait sur des
    relations qu'il jette. Le rapport ne vaut que parce que les deux lisent la même chose.
    """
    try:
        from graph_export import TYPES_RELATION, _REL_BLOC, relations_brutes
        return (set(TYPES_RELATION), _REL_BLOC, relations_brutes), None
    except Exception as e:
        return (None, None, None), (
            f"hooks/graph_export.py illisible ({e}) — c'est LUI qui possède les types de "
            "relation valides (TYPES_RELATION) et leur analyseur. Contrôles 8 et 9 NON JOUÉS : "
            "une fiche peut déclarer n'importe quel type sans que rien ne le dise.")


def _sujets_canoniques():
    """Les 12 sujets validés par l'auteur le 2026-08-27, LUS dans meta/topics.json par son
    lecteur unique (hooks/topics_fiche.py). Même raison qu'au-dessus : un septième dialecte
    de frontmatter ferait diverger le contrôle de l'outil qui écrit les sujets."""
    try:
        import topics_fiche
        return (topics_fiche, topics_fiche.ids_canoniques()), None
    except Exception as e:
        return (None, None), (
            f"meta/topics.json ou hooks/topics_fiche.py injoignable ({e}) — la source des "
            "12 sujets validés le 27/08. Contrôle 10 NON JOUÉ : un sujet inventé passerait.")


(REL_TYPES, REL_BLOC, REL_BRUTES), RELATIONS_ERREUR = _vocabulaire_relations()
(SUJETS_MOD, SUJETS_IDS), SUJETS_ERREUR = _sujets_canoniques()

# DEUX MESURES QUI NE SONT PAS DES FAUTES — décidé par l'auteur le 2026-09-17 (ADR-0019).
# L'ADR rend le sujet obligatoire et la raison de `lie_a` obligatoire sur les fiches NEUVES
# seulement. Les fiches écrites avant n'ont pas enfreint une règle qui n'existait pas : les
# faire rougir ferait porter au docteur une accusation fausse, et — pire — inviterait à
# inventer 49 sujets et 239 raisons, c'est-à-dire à fabriquer de la provenance.
# Les deux chiffres sont donc MESURÉS et AFFICHÉS, et ne font pas sortir le docteur en 1.
# Ce qui tient la règle sur les fiches neuves, c'est le moment de l'écriture : hooks/on_fiche_write.py
# (contrôle « 1 ter », posé le 17/09) consigne chaque écart dans state/vocabulaire-a-l-ecriture.jsonl
# avec sa date, et c'est le seul endroit d'où l'on puisse distinguer une fiche neuve d'une ancienne.
# Reste la consigne du distillateur (étape 5 du chantier). Pas ce compteur-ci.
INFORMATIFS = {"sujet_absent", "lie_a_sans_raison", "carte_plafond_non_remesure"}



def main():
    files = md_files()
    checked_files = [
        f for f in files if os.path.relpath(f, BRAIN) not in STRUCTURAL_MAPS
    ]
    # L'IDENTITÉ LOGIQUE N'EST PLUS LE NOM DU FICHIER (2026-08-27, décision l'auteur).
    # `skills/design/SKILL.md` s'appelle `design` : la contrainte de Claude Code fait
    # autorité sur la forme physique, et c'est l'indexeur qui apprend. La règle vit dans
    # hooks/identite_fiche.py — une définition, plusieurs importateurs.
    slugs = set()
    for f in files:
        slug, canonique, _ = identite(os.path.relpath(f, BRAIN))
        if slug and canonique:
            slugs.add(slug)
    # UNE CIBLE PEUT VIVRE HORS DU CORPUS SANS ÊTRE MORTE. `vision/` est délibérément hors
    # rappel (tests/vision_hors_corpus.py) et ses documents ne sont pas des fiches — mais ils
    # EXISTENT, et une fiche a le droit de dire d'où elle vient. Les compter morts serait une
    # accusation fausse : mesuré le 17/09, `gmatter-vision-continuite` était accusée de pointer
    # dans le vide vers `vision/gmatter-master-continuite-2026-08-19.md`, qui est sur le disque.
    cibles_hors_corpus = {os.path.basename(p)[:-3]
                          for p in glob.glob(os.path.join(BRAIN, "vision", "*.md"))}
    # les représentations CONCURRENTES se signalent, elles ne s'indexent pas en silence :
    # indexer les deux donnerait 48 identités pour 24 skills et une résolution de
    # `[[design]]` qui dépendrait de l'ordre de parcours du disque.
    _, conflits_repr, _ = scanner(BRAIN, sorted(LINKED_DIRS))
    memory = read(MEMORY) + "\n" + read(LESSONS_INDEX)

    all_links = set()
    problems = {"liens_morts": [], "orphelins": [], "frontmatter": [],
                "nommage": [], "hors_index": [], "memory_trop_lourd": [],
                "memory_trop_de_lignes": [], "carte_plafond_non_remesure": [],
                # axe thématique (2026-08-14) : une leçon sans famille est invisible pour
                # le pont de vocabulaire du rappel — et la prochaine fiche écrite sortira
                # sans tag si RIEN ne l'exige, cf. le-premier-fichier-d-un-type-nouveau…
                "lecons_sans_famille": [], "index_derive": [],
                # deux fichiers pour une même identité logique : un choix à faire, pas un
                # doublon à absorber. cf. hooks/identite_fiche.py
                "representations_concurrentes": [],
                # LES GARDES DU DÉPÔT (2026-08-20). `.git/hooks/` ne se clone pas :
                # un tronc restauré ou cloné arrive SANS pre-commit (le garde
                # multi-zones et les 8 bancs) et SANS post-commit (la régénération
                # du graphe). `installer.sh --verifie` savait le dire depuis
                # toujours — et personne ne l'appelait. Le motif est celui du
                # held-out du même jour : une protection dont nul ne vérifie la
                # présence protège jusqu'au jour où elle disparaît sans bruit.
                "hooks_git": [],
                # LA PROJECTION DE HOOKS (2026-09-20). Même motif que `hooks_git`, sur
                # l'autre surface : `config/claude-hooks.json` est la source versionnée
                # des hooks Claude Code, `tools/settings_projection.py --verifie` sait
                # dire si ~/.claude/settings.json s'en est écarté — et PERSONNE ne
                # l'appelait depuis sa pose, le 2026-08-21. Mesuré le 20/09 : cinq écarts
                # vivaient là depuis 26 jours. La campagne L1 s'était close le 25/08 en
                # retirant trois hooks « pendant l'annotation » ; le dégel en a remis UN,
                # et la source n'a jamais appris que la campagne était finie. C'est le
                # sujet même de la friction #7 du chantier B : un MODE délibéré dont plus
                # rien ne surveille la sortie finit par habiller ses propres pannes en
                # « c'est voulu ».
                "projection_hooks": [],
                # LA RONDE D'ÉTAT QUI N'A PLUS MESURÉ (2026-09-20). `etat_projets.py`
                # tourne à 8 h et 19 h, sort en 0, affiche sa bannière — et depuis le
                # 28/08 il ne MESURE plus rien : le service launchd n'a pas le droit de
                # lire le Bureau, alors le programme refuse (très correctement) d'écraser
                # sa dernière mesure complète et annonce son âge. Un jour, c'est un état
                # passager. Vingt-trois jours, c'est une panne. Rien ne faisait passer
                # l'un dans l'autre : c'est exactement la question laissée « à arbitrer »
                # par la friction #7, et la réponse n'est pas une catégorie de plus, c'est
                # un SEUIL D'ÂGE. Trois jours — le chiffre est celui que la docstring
                # d'`etat_projets.py` se donne à elle-même : « une fiche d'état écrite à
                # la main pourrit en trois jours ; celle-ci se REGÉNÈRE ». À deux tours
                # par jour, trois jours valent six mesures manquées d'affilée.
                "ronde_perimee": [],
                # la PIÈCE elle-même, avant les fiches qui s'y réfèrent
                "registre_familles": [],
                # 8/9/10 (17/09) — L'ARCHITECTURE DES RELATIONS ET DES SUJETS.
                # Jusqu'ici personne ne regardait : l'exporteur du graphe jetait les types
                # inconnus sans un mot, et aucun instrument ne lisait la cible d'une
                # relation. Un lien qualifié vers une fiche disparue se lisait comme un
                # lien valide — c'est-à-dire comme un savoir qui existe encore.
                "relations_type_inconnu": [], "relations_cible_morte": [],
                "lie_a_sans_raison": [],
                "sujet_invalide": [], "sujet_absent": [],
                # un contrôle qui n'a PAS pu tourner le dit ; il ne rend pas « rien à signaler »
                "vocabulaire_injoignable": []}
    if FAMILLES_ERREUR:
        problems["registre_familles"].append(FAMILLES_ERREUR)
    for _err in (RELATIONS_ERREUR, SUJETS_ERREUR):
        if _err:
            problems["vocabulaire_injoignable"].append(_err)

    # Les hooks du dépôt sont-ils posés, et à jour ? On INTERROGE l'installateur
    # plutôt que de recomparer les fichiers ici : il possède déjà la liste des
    # hooks et la définition de « à jour ». Un second comparateur finirait par
    # diverger du premier.
    _inst = os.path.join(BRAIN, "tools", "git-hooks", "installer.sh")
    if os.path.isdir(os.path.join(BRAIN, ".git")) and os.access(_inst, os.X_OK):
        try:
            _r = subprocess.run([_inst, "--verifie"], capture_output=True,
                                text=True, timeout=30)
            if _r.returncode != 0:
                for _l in (_r.stdout or "").splitlines():
                    if _l.strip().startswith("⚠️"):
                        problems["hooks_git"].append(_l.strip().lstrip("⚠️ ").strip())
                if not problems["hooks_git"]:
                    problems["hooks_git"].append(
                        "installer.sh --verifie sort en %d sans rien nommer" % _r.returncode)
        except Exception as _e:
            # Ne jamais faire échouer le doctor sur son propre outillage — mais ne
            # jamais taire non plus qu'un contrôle n'a PAS pu tourner.
            problems["hooks_git"].append("contrôle impossible : %s" % _e)

    # La projection de hooks : on INTERROGE le projecteur, on ne recompare pas ici.
    # Même raison que ci-dessus — un second comparateur diverge du premier.
    _proj = os.path.join(BRAIN, "tools", "settings_projection.py")
    if os.path.exists(_proj):
        try:
            _r = subprocess.run([sys.executable, _proj, "--verifie"],
                                capture_output=True, text=True, timeout=30)
            if _r.returncode != 0:
                _section = "?"
                for _l in (_r.stdout or "").splitlines():
                    _m = re.match(r"\s*([A-G]) · (.+?)\s*$", _l)
                    if _m:
                        _section = _m.group(1)
                        continue
                    # La DERNIÈRE ligne du vérificateur est son verdict global, pas un
                    # écart : « ❌ écart(s) — `--diff` puis `--installe` ». Collée telle
                    # quelle, elle ajoutait un septième défaut qui n'existe pas, et gonflait
                    # le total d'une unité à chaque run. Les constats sont INDENTÉS sous
                    # leur section ; le verdict est en colonne 0. C'est ça qui les sépare.
                    if not _l.startswith(" "):
                        continue
                    _l = _l.strip()
                    if _l.startswith("❌"):
                        _t = _l.lstrip("❌ ").strip()
                        # une commande entière dans une liste d'alerte, c'est illisible :
                        # ce qui identifie le hook est son script, pas son préfixe.
                        _t = re.sub(r"(?:BRAIN_HOME=\S+ )?(?:python3 )?%s/" % re.escape(BRAIN),
                                    "", _t)
                        problems["projection_hooks"].append("%s · %s" % (_section, _t))
                if not problems["projection_hooks"]:
                    problems["projection_hooks"].append(
                        "settings_projection.py --verifie sort en %d sans rien nommer"
                        % _r.returncode)
        except Exception as _e:
            problems["projection_hooks"].append("contrôle impossible : %s" % _e)

    # La ronde d'état a-t-elle encore le droit de mesurer ? On lit l'ARTEFACT daté
    # qu'elle produit, jamais son code de sortie ni sa bannière : les deux sont verts
    # depuis vingt-trois jours. cf. un-compteur-a-zero-ne-distingue-pas-pas-encore-de-jamais
    _RONDE_JOURS = 3
    _cache = os.path.join(BRAIN, "state", "etat-projets.json")
    try:
        import datetime as _dt
        _mes = json.load(open(_cache, encoding="utf-8")).get("mesure_le")
        _age = (_dt.datetime.now() - _dt.datetime.fromisoformat(_mes)).days
        if _age >= _RONDE_JOURS:
            problems["ronde_perimee"].append(
                "state/etat-projets.json : dernière mesure COMPLÈTE il y a %d j (%s) — "
                "la ronde tourne et s'annonce, mais n'écrit plus. Cause vue le 20/09 : "
                "accès disque refusé au service launchd (le Bureau n'est pas lisible)."
                % (_age, _mes[:10]))
    except FileNotFoundError:
        pass
    except Exception as _e:
        problems["ronde_perimee"].append("âge de la ronde illisible : %s" % _e)

    # Les cartes structurelles contribuent les liens qu'elles portent, sans devenir
    # elles-mêmes des fiches soumises aux invariants de frontmatter/nommage.
    for f in files:
        txt = read(f)
        all_links |= extract_links(txt)

    # 1. liens morts
    # INDEX dérivé : la carte des leçons est GÉNÉRÉE depuis les tags. Si elle diffère de ce
    # que le générateur produirait, quelqu'un l'a éditée à la main — et sa correction sera
    # écrasée au prochain passage sans prévenir.
    # LE GÉNÉRATEUR EST DANS LE MOTEUR, L'INDEX EST DANS LE TRONC. Appeler
    # `BRAIN/hooks/index_lecons.py` revenait à demander à l'arbre examiné de fournir l'outil
    # qui l'examine : sur le tronc auteur les deux coïncident, mais dès que BRAIN_HOME
    # désigne un autre arbre (banc, clone partiel, restauration), python sortait en 2
    # « can't open file » — et le docteur accusait cet arbre d'avoir édité son INDEX à la
    # main. Le générateur qui fait foi est celui livré À CÔTÉ de ce fichier ; il lit
    # BRAIN_HOME de son côté (hooks/brain_racine.py), donc il juge bien l'arbre visé.
    # Trouvé le 17/09 par tests/relations_et_sujets.py, sur un tronc jetable.
    _gen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index_lecons.py")
    if not os.path.exists(_gen):
        problems["vocabulaire_injoignable"].append(
            f"hooks/index_lecons.py absent ({_gen}) — c'est lui qui dit si lessons/INDEX.md "
            "a dérivé. Contrôle NON JOUÉ : un INDEX réécrit à la main passerait.")
    else:
        try:
            import subprocess as _sp
            r = _sp.run([sys.executable, _gen, "--verifie"], capture_output=True, text=True)
            if r.returncode != 0:
                problems["index_derive"].append("lessons/INDEX.md a été édité à la main — régénérer")
        except Exception as e:
            problems["vocabulaire_injoignable"].append(
                f"hooks/index_lecons.py n'a pas pu tourner ({e}) — contrôle INDEX NON JOUÉ.")

    for slug, canon, concurrent, motif in conflits_repr:
        problems["representations_concurrentes"].append(
            "%s : %s (canonique %s)" % (slug, concurrent, canon or "AUCUN"))

    for l in sorted(all_links):
        if l in slugs or l in EXAMPLE_WHITELIST:
            continue
        problems["liens_morts"].append(l)

    for f in checked_files:
        rel = os.path.relpath(f, BRAIN)
        # `base` est l'identité LOGIQUE. Employer le nom de fichier ici est exactement ce
        # qui a cassé les 24 skills : `SKILL.md` donnait base="SKILL", le frontmatter
        # disait name="design", le doctor criait — et renommer le fichier était la seule
        # façon de le taire.
        base, canonique, _motif = identite(rel)
        if base is None:
            continue                       # ressource interne ou outillage : pas une fiche
        if not canonique:
            continue                       # déjà signalé comme représentation concurrente
        zone = rel.split(os.sep)[0]
        txt = read(f)

        # 3+4. frontmatter & nommage (uniquement zones tissées)
        if zone in LINKED_DIRS:
            fm = frontmatter(txt)
            if fm is None:
                problems["frontmatter"].append(f"{rel} : pas de frontmatter")
            else:
                if not fm.get("name"):
                    problems["frontmatter"].append(f"{rel} : 'name' manquant")
                elif fm["name"] != base:
                    problems["frontmatter"].append(
                        f"{rel} : name='{fm['name']}' ≠ identité '{base}'")
                if not fm.get("description"):
                    problems["frontmatter"].append(f"{rel} : 'description' manquante")
            if not re.fullmatch(r"[a-z0-9-]+", base):
                problems["nommage"].append(f"{rel} : '{base}' n'est pas en kebab-case")

            # 2. orphelin (jamais ciblé par un lien)
            if base not in INDEX_EXEMPT and base not in all_links:
                problems["orphelins"].append(base)

            # 5. présence dans la carte (MEMORY.md + lessons/INDEX.md)
            #
            # `carte: exclue` — ABSENCE VOULUE DE LA PROJECTION DE DÉMARRAGE
            # (2026-08-20, chantier B6). Le 20/08, une fiche laissée hors carte
            # par décision explicite est apparue ici en « Hors carte » ; le
            # jardinier, dont la règle d'or est « toute fiche est dans la carte »
            # et qui attaque en priorité ce que ce rapport signale, l'a insérée
            # dans MEMORY.md — sans toucher au manifeste, donc hors de la
            # transaction qu'ADR-0015 exige. L'agent a exécuté sa mission : le
            # défaut était qu'aucune décision « hors carte VOULU » ne pouvait
            # s'écrire quelque part où un instrument la lise.
            #
            # ⚠️ CE CHAMP NE PARLE QUE DE LA CARTE `MEMORY.md`. Il ne retire rien
            # du corpus, du rappel BM25, du graphe ni des liens : la fiche reste
            # une connaissance ordinaire du Brain, simplement non exigée dans la
            # projection de démarrage. Cf. meta/jardinage-regles.md.
            exclue_de_la_carte = (fm or {}).get("carte", "").strip() == "exclue"
            if base not in INDEX_EXEMPT and not exclue_de_la_carte \
                    and base not in memory and rel not in memory:
                problems["hors_index"].append(base)

            # 8/9. LES RELATIONS TYPÉES. Même analyseur et même vocabulaire que
            # graph_export : ce qui rougit ici est EXACTEMENT ce que la carte perd.
            # Les cibles se contrôlent pour TOUS les types, connus ou non — un lien qui
            # ne mène nulle part ne mène nulle part quel que soit le mot qui le qualifie.
            if zone in ZONES_FICHES and REL_TYPES is not None:
                tete = re.match(r"^---\n(.*?)\n---", txt, re.S)
                bloc = REL_BLOC.search(tete.group(1) + "\n") if tete else None
                if bloc:
                    vus = set()
                    for typ, c, raison in REL_BRUTES(bloc.group(1)):
                        if typ not in REL_TYPES and typ not in vus:
                            # DÉRIVE D'ORTHOGRAPHE : `based_on` pour `base_sur` n'est pas un
                            # type de plus, c'est le même type mal écrit. Le nommer évite
                            # qu'on « tranche » un vocabulaire qui n'a jamais divergé.
                            proche = difflib.get_close_matches(typ, sorted(REL_TYPES), 1, 0.6)
                            derive = f" (dérive de '{proche[0]}' ?)" if proche else ""
                            problems["relations_type_inconnu"].append(f"{rel} : '{typ}'{derive}")
                            vus.add(typ)
                        if c and c not in slugs and c not in cibles_hors_corpus \
                                and c not in EXAMPLE_WHITELIST:
                            problems["relations_cible_morte"].append(f"{rel} : {typ} → {c}")
                        # `lie_a` est le SEUL fourre-tout, et il se paie d'une phrase : sans
                        # elle, il redevient le lien nu qu'on vient de mesurer à 239 liens.
                        if typ == "lie_a" and not raison:
                            problems["lie_a_sans_raison"].append(f"{rel} → {c}")

            # 10. LE SUJET. `lire` rend ce qui est ÉCRIT sans rien deviner, `valider` refuse ;
            # les deux vivent dans topics_fiche, avec l'outil qui écrit les sujets.
            if zone in ZONES_FICHES and SUJETS_MOD is not None:
                sujet, secondaires = SUJETS_MOD.lire(txt)
                try:
                    SUJETS_MOD.valider(sujet, secondaires, SUJETS_IDS)
                except SUJETS_MOD.SujetInvalide as e:
                    cle = "sujet_absent" if not sujet else "sujet_invalide"
                    problems[cle].append(f"{rel} : {e}")

            # 6. toute leçon porte une famille thématique (1 principale + 1 secondaire max)
            if zone == "lessons" and base not in INDEX_EXEMPT:
                t = re.search(r"^tags:\s*\[(.*?)\]", txt, re.M)
                noms = [x.strip() for x in t.group(1).split(",") if x.strip()] if t else []
                if not noms:
                    problems["lecons_sans_famille"].append(f"{base} : aucun tag")
                elif len(noms) > 2:
                    problems["lecons_sans_famille"].append(f"{base} : {len(noms)} tags (plafond 2)")
                elif not FAMILLES_ERREUR:
                    # Muet SI le registre est absent : sans lui, chacune des 223 leçons
                    # sortirait « famille inconnue », et le vrai défaut (une pièce
                    # manquante) serait noyé sous 223 accusations de fiches saines.
                    inconnus = [n for n in noms if n not in FAMILLES]
                    if inconnus:
                        problems["lecons_sans_famille"].append(f"{base} : famille inconnue {inconnus}")

    # 6. garde-fou de chargement : alerte avant les DEUX limites mesurées du harnais.
    try:
        with open(MEMORY, "rb") as _f:
            _blob = _f.read()
        memory_bytes = len(_blob)
        # la dernière ligne compte même sans saut de ligne final : c'est elle que la
        # troncature emporte en premier, et c'est là qu'on met les renvois de fin.
        memory_lines = _blob.count(b"\n") + (1 if _blob and not _blob.endswith(b"\n") else 0)
    except OSError:
        memory_bytes = memory_lines = 0
    if memory_bytes > MEMORY_WARN_BYTES:
        problems["memory_trop_lourd"].append(
            f"MEMORY.md : {memory_bytes} octets > {MEMORY_WARN_BYTES}"
        )
    if memory_lines > MEMORY_WARN_LINES:
        problems["memory_trop_de_lignes"].append(
            f"MEMORY.md : {memory_lines} lignes > {MEMORY_WARN_LINES} "
            f"(limite mesurée 200 lignes, troncature SILENCIEUSE au-delà)"
        )
    _vh = harness_version()
    if _vh and _vh != MEMORY_LIMITS_MEASURED_ON:
        problems["carte_plafond_non_remesure"].append(
            f"limites mesurées sous Claude Code {MEMORY_LIMITS_MEASURED_ON}, "
            f"harnais actuel {_vh} — les deux seuils reposent sur une mesure "
            f"d'une autre version"
        )

    # 7. drift git
    drift = []
    try:
        r = subprocess.run(["git", "-C", BRAIN, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        drift = [l for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        pass

    total = sum(len(v) for k, v in problems.items() if k not in INFORMATIFS)
    report = {"ok": total == 0, "total": total, "fiches": len(checked_files),
              "liens": len(all_links), "memory_bytes": memory_bytes,
              "drift_git": len(drift), **problems}

    if "--json" in sys.argv:
        try:
            os.makedirs(os.path.join(BRAIN, "state"), exist_ok=True)
            json.dump(report, open(os.path.join(BRAIN, "state", "doctor.json"), "w"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass
        # historisation : une ligne compacte par run → tendance lisible dans le temps
        try:
            import time
            lessons = len([f for f in checked_files if os.path.relpath(f, BRAIN).startswith("lessons")])
            metric = {"ts": int(time.time()), "fiches": len(checked_files), "lecons": lessons,
                      "liens": len(all_links), "liens_morts": len(problems["liens_morts"]),
                      "orphelins": len(problems["orphelins"]),
                      "hors_index": len(problems["hors_index"]), "ok": report["ok"]}
            with open(os.path.join(BRAIN, "state", "metrics.jsonl"), "a", encoding="utf-8") as mf:
                mf.write(json.dumps(metric, ensure_ascii=False) + "\n")
        except Exception:
            pass

    if "--quiet" not in sys.argv and "--json" not in sys.argv:
        ico = "✅" if report["ok"] else "⚠️"
        print(f"{ico} brain_doctor — {len(files)} fiches, {len(all_links)} liens, "
              f"{len(drift)} modif(s) non commitée(s)")
        # ⚠️ TOUTE CLÉ DE `problems` DOIT AVOIR SON LIBELLÉ. Cette table était écrite en dur :
        # deux contrôles ajoutés le 2026-08-14 (famille manquante, INDEX dérivé) remplissaient
        # bien `problems`, comptaient dans le total et faisaient sortir en 1 — mais n'imprimaient
        # RIEN. Un contrôle qui détecte sans le dire est un contrôle muet. L'assertion en dessous
        # empêche la prochaine addition de retomber dedans.
        labels = {"registre_familles": "Registre des familles",
                  "liens_morts": "Liens morts", "orphelins": "Orphelins",
                  "representations_concurrentes": "Représentations concurrentes",
                  "frontmatter": "Frontmatter", "nommage": "Nommage",
                  "hors_index": "Hors carte",
                  "memory_trop_lourd": "MEMORY.md trop lourd",
                  "memory_trop_de_lignes": "MEMORY.md trop de lignes",
                  "carte_plafond_non_remesure": "Plafond de chargement mesuré sous un autre harnais",
                  "lecons_sans_famille": "Leçons sans famille thématique",
                  "index_derive": "lessons/INDEX.md édité à la main",
                  "hooks_git": "Gardes du dépôt absents ou périmés",
                  "projection_hooks": "Hooks Claude Code écartés de leur source versionnée",
                  "ronde_perimee": "Ronde d'état : plus aucune mesure complète",
                  "vocabulaire_injoignable": "CONTRÔLE NON JOUÉ, vocabulaire injoignable",
                  "relations_type_inconnu": "Relations que la carte jette en silence",
                  "relations_cible_morte": "Relations vers une fiche inexistante",
                  "lie_a_sans_raison": "lie_a sans sa raison (mesure — fiches d'avant l'ADR-0019)",
                  "sujet_invalide": "Sujet hors des 12 validés, ou dédoublé",
                  "sujet_absent": "Sans sujet (mesure — décision R2 en attente)"}
        muets = [k for k in problems if k not in labels]
        if muets:
            print(f"  ⚠️  contrôles SANS libellé, donc invisibles : {muets}")
        for k, lab in labels.items():
            if problems[k]:
                ico_k = "ℹ️ " if k in INFORMATIFS else "⚠️ "
                # UNE COUPE MUETTE LAISSE CROIRE QU'ON A TOUT VU. Mesuré le 2026-09-20 :
                # 58 plaintes de frontmatter, 57 venues d'un seul défaut d'identité, et le
                # skill saboté exprès par tests/identite_skills.py tombait au 13ᵉ rang —
                # donc hors écran. Le banc était rouge sur « SABOTAGE INVISIBLE » sans que
                # la sortie du doctor n'ait l'air fautive. Le nombre entre parenthèses ne
                # suffit pas : il demande une soustraction, et il ne dit pas OÙ la liste
                # s'arrête. On nomme la coupe à l'endroit où elle coupe.
                _montres = problems[k][:12]
                _coupe = len(problems[k]) - len(_montres)
                print(f"  {ico_k} {lab} ({len(problems[k])}): "
                      + ", ".join(map(str, _montres))
                      + (f"  … +{_coupe} non montré(s)" if _coupe else ""))
                # pour les relations, c'est le DÉCOMPTE PAR TYPE
                # qui dit s'il s'agit d'une dérive de masse ou de trois cas isolés.
                if k == "relations_type_inconnu":
                    par_type = {}
                    for x in problems[k]:
                        t = re.search(r"'([^']+)'", x)
                        if t:
                            par_type[t.group(1)] = par_type.get(t.group(1), 0) + 1
                    print("        par type : " + ", ".join(
                        f"{t} × {n}" for t, n in sorted(par_type.items(), key=lambda i: -i[1])))
        if report["ok"]:
            print("  Rien à signaler — arbre cohérent.")

    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
