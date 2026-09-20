#!/usr/bin/env python3
"""
graph_export.py — exporte le C Brain en graphe pour la PLANÈTE de connaissance.

Scanne toutes les fiches .md du tronc (projects/, lessons/, meta/, life/, agents/),
lit leur frontmatter (`name`, `description`) et leurs liens `[[...]]`, et écrit
`planet/graph.json` : la matière première du visualizer 3D (1 fiche = 1 point sur le globe).

Conçu pour être appelé :
  - à la main : `python3 hooks/graph_export.py`
  - automatiquement par on_fiche_write.py à chaque fiche écrite (croissance temps réel).

Déterministe et sans dépendance externe. Sort toujours 0 (ne bloque jamais un hook).
"""
import os, re, json, sys
import subprocess
from collections import Counter

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
OUT = os.path.join(BRAIN, "planet", "graph.json")
# le corps des fiches, sorti de graph.json : chargé à la demande au premier dépliage
OUT_TEXTES = os.path.join(BRAIN, "planet", "textes.json")
EMBED2 = os.path.join(BRAIN, "state", "embed2.json")   # carte SÉMANTIQUE (Étage 1), calculée par brain_embed2.py
COACT = os.path.join(BRAIN, "state", "coactivation.json")  # mémoire de travail (Étage 2), calculée par coactivation.py
CHALLENGES = os.path.join(BRAIN, "state", "challenges.json")  # avis du challenger (Étage 3 : la carte a un avis)
BELIEFS = os.path.join(BRAIN, "meta", "beliefs.json")        # convictions datées de l'auteur du tronc (Étage 3 : couche goût)
MEDIA = os.path.join(BRAIN, "meta", "media.json")            # nœuds REJOUABLES (Étage 4 : capture glb/clip/courbe)


def load_media():
    """Captures rejouables par fiche → { rel_path: {type, src, caption} }. Curé (meta/media.json). Stdlib."""
    out = {}
    try:
        for f, v in json.load(open(MEDIA, encoding="utf-8")).items():
            if f.startswith("_") or not isinstance(v, dict) or not v.get("src"):
                continue
            out[f] = {"type": v.get("type", "glb"), "src": v["src"], "caption": v.get("caption", "")}
    except Exception:
        return {}
    return out


def load_beliefs():
    """Convictions datées de l'auteur du tronc → { rel_path: "depuis <date> — <note>" }. Curé (meta/beliefs.json). Stdlib."""
    out = {}
    try:
        for f, v in json.load(open(BELIEFS, encoding="utf-8")).items():
            if f.startswith("_") or not isinstance(v, dict):
                continue
            since = v.get("since", "")
            out[f] = (f"depuis {since} — " if since else "") + v.get("note", "")
    except Exception:
        return {}
    return out


def load_challenges():
    """Verdicts ACTIFS du challenger par fiche → { rel_path: "verdict court" }. Les challenges
    marqués PÉRIMÉ/résolu sont ignorés (la carte ne conteste que ce qui tient encore). Stdlib."""
    out = {}
    try:
        for c in json.load(open(CHALLENGES, encoding="utf-8")):
            vp = (c.get("verdict_pair") or "")
            prob = (c.get("probleme") or "")
            if "PÉRIMÉ" in prob or "périmé" in vp.lower() or "résolu" in vp.lower():
                continue                                  # challenge éteint → pas un avis vivant
            f = c.get("fiche")
            if not f:
                continue
            reason = vp or prob
            out.setdefault(f, reason[:200])               # 1 verdict (le 1er actif) par fiche
    except Exception:
        return {}
    return out


def load_embed2():
    """Positions 3D sémantiques { rel_path: [x,y,z] } — cache produit hors-ligne (numpy).
    Lu SANS dépendance : graph_export reste pur-stdlib (appelé à chaque écriture de fiche).

    REND (positions, état, détail) — ET C'EST TOUT L'INTÉRÊT DE CETTE SIGNATURE.
    Avant, un `except Exception: return {}` confondait trois situations qu'un lecteur doit
    pouvoir distinguer : le module n'a jamais été installé (légitime — les embeddings sont
    optionnels par dessein, docs/design-doc.md), le cache est là et illisible (une vraie
    panne), le cache est là et bon. La Planète annonçait alors « SENS EN VOLUME — proximité
    = sens, toutes les fiches » sur une carte où PAS UNE fiche n'avait de vecteur, parce
    qu'un dictionnaire vide ne dit rien de la raison de son vide. Mesuré à l'écran le
    2026-09-19 sur le paquet livré : 0 fiche sur 10, et la carte S'OUVRE sur cette vue.
    """
    if not os.path.exists(EMBED2):
        return {}, "absent", ("state/embed2.json n'a jamais été produit — le module "
                              "sémantique est optionnel et n'a pas tourné")
    try:
        pos = json.load(open(EMBED2, encoding="utf-8")).get("pos", {})
    except Exception as e:                      # illisible, tronqué, pas du JSON
        return {}, "broken", f"state/embed2.json est là mais illisible : {e}"
    if not isinstance(pos, dict):
        return {}, "broken", "state/embed2.json n'a pas de table `pos` exploitable"
    return pos, "ready", ""


def load_coact():
    """Chaleur (récence d'usage) par id + liens d'usage + ACTIVITÉ EN DIRECT — Étage 2. Stdlib.

    `live` = { path: ts } des fiches lues dans la fenêtre glissante (quelques minutes), plus la
    fenêtre elle-même : le visualizer en a besoin pour éteindre un anneau tout seul, en continu,
    même si le graphe n'est pas régénéré entre-temps."""
    try:
        c = json.load(open(COACT, encoding="utf-8"))
        lv = c.get("live") or {}
        live = {p: ts for p, ts in lv.get("items", [])}
        return c.get("heat_id", {}), c.get("edges", []), live, int(lv.get("window_min", 10))
    except Exception:
        return {}, [], {}, 10
# dossiers de premier niveau = « domaines » (couleurs sur le globe)
DOMAINS = ["projects", "lessons", "meta", "life", "agents"]

FM_NAME = re.compile(r'^\s*name:\s*["\']?([^"\'\n]+)["\']?\s*$', re.M)
FM_TITLE = re.compile(r'^\s*title:\s*["\']?(.+?)["\']?\s*$', re.M)  # libellé humain descriptif (≠ slug stable)
FM_DESC = re.compile(r'^\s*description:\s*["\']?(.+?)["\']?\s*$', re.M)
FM_BORN = re.compile(r'^\s*born_from:\s*(.+?)\s*$', re.M)   # born_from: <projet>[, autre]
FM_SCALE = re.compile(r'^\s*scale:\s*([0-9](?:\.[0-9])?)\s*$', re.M)  # scale: 1..4 (centre-ville→périphérie)
FM_TYPE = re.compile(r'^\s*type:\s*["\']?(\w+)["\']?\s*$', re.M)      # metadata.type : feedback|project|lesson…
LINK = re.compile(r'\[\[([^\]]+)\]\]')          # [[nom-de-fiche]]
# ⚠️ ANCIEN DÉTECTEUR, RETIRÉ LE 2026-08-14 :
#     RESUME_RE = re.compile(r'REPRENDRE ICI|point de reprise|à reprendre', re.I)
# Il allumait le badge ↻ sur 32 fiches en continu — et un marqueur allumé partout ne marque
# plus rien. Il comptait notamment : les fiches qui PARLENT du marqueur (la leçon
# `marqueur-barre-ou-nie-nest-pas-une-tache-ouverte`, l'audit de la planète lui-même), celles
# qui le NIENT (« confirme qu'il n'y a rien à reprendre »), celles où il est BARRÉ
# (`~~À reprendre~~`, une décision d'abandon), et les leçons/méta où un point de reprise n'a
# aucun sens. C'est exactement le défaut déjà consigné dans
# [[marqueur-barre-ou-nie-nest-pas-une-tache-ouverte]], corrigé dans `etat_projets.py` puis
# jamais propagé ici : deux détecteurs pour la même question, un seul réparé.
# Le badge lit maintenant `brain_anticipate` — le MÊME détecteur et le MÊME classement que les
# reprises proposées au démarrage de session. Une seule source, donc plus de divergence
# possible entre ce que le Brain propose et ce que la carte montre.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
def _head_courant():
    """Le HEAD du tronc, ou None si le tronc n'est pas un dépôt."""
    try:
        r = subprocess.run(["git", "-C", BRAIN, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def load_reprises():
    """Les fiches en tête des reprises proposées (badge ↻), et la raison si le calcul échoue.

    APPELÉE PAR scan(), PLUS AU CHARGEMENT DU MODULE (17/09). `brain_anticipate.collect()`
    parcourt tout l'arbre : mesuré à 281 ms, et ces 281 ms étaient payées par TOUT importateur
    du module — le docteur, les bancs, et depuis ce matin le hook qui relit chaque fiche à
    l'écriture — alors que le seul lecteur du résultat est le graphe. Le hook les payait dans
    son temps de PREMIER PLAN, celui que l'utilisateur attend, là où il prend soin de détacher ses
    rafraîchissements. Même forme que load_coact, load_challenges et les autres chargeurs
    au-dessus : une fonction, appelée là où son résultat sert.
    """
    try:
        import brain_anticipate
        return {it["path"] for it in brain_anticipate.collect()[:brain_anticipate.TOP_REPRISES]}, None
    except Exception as e:
        # Jamais bloquer l'export du graphe pour un badge — mais un badge éteint parce
        # que la capacité manque et un badge éteint parce qu'il n'y a rien à reprendre
        # sont deux états DIFFÉRENTS. Le graphe porte donc la raison, et l'invariant la
        # lit plutôt que de comparer deux ensembles vides et de se croire vert.
        indisponible = "%s: %s" % (type(e).__name__, e)
        print("⚠️  badge ↻ non calculé — %s" % indisponible, file=sys.stderr)
        return set(), indisponible
DASH = re.compile(r'\s+[—–]\s+')                # tiret cadratin/demi-cadratin entouré d'espaces

# poids des appartenances (modèle continent/ville/frontière) — voir respirabilite & volet-3
W_PRIMARY = 1.00     # dossier d'origine (un projet) = appartenance forte
W_BORN    = 0.70     # né d'un projet (born_from) mais rangé ailleurs (ex. leçon réutilisable)
W_LINK    = 0.18     # lien [[...]] vers/depuis une fiche de projet = appartenance douce
HOME_MIN  = 0.50     # appartenance mini pour avoir une VILLE maison (dossier/born_from, pas un simple lien)
FRONTIER_MIN = 0.30  # seuil pour qu'une 2ᵉ appartenance compte comme « frontière »

# heuristique d'échelle quand `scale:` absent : centre-ville (vision/projet) → périphérie (détail)
def guess_scale(nid):
    s = nid.lower()
    if s.startswith("project-") or "vision" in s:
        return 1.0                                   # cœur : le projet, sa vision
    if any(k in s for k in ("audit", "naming", "precision", "couts", "labo", "lab")):
        return 3.0                                   # périphérie : détail/annexe
    return 2.0                                        # ville standard


def clean_desc(raw):
    """Résumé court et propre pour le panneau : la phrase d'accroche avant le 1er ' — ',
    sinon la description entière ; jamais coupée en plein mot."""
    full = (raw or "").strip()
    summary = DASH.split(full, 1)[0].strip()
    if len(summary) < 35:                       # accroche trop maigre → on garde tout
        summary = full
    if len(summary) > 180:                       # coupe nette au mot + …
        summary = summary[:180].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return summary


def frontmatter(text):
    """Renvoie le bloc frontmatter (entre les --- de tête) ou ''."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end]
    return ""


RE_H1 = re.compile(r'^#[ \t]+(.+?)[ \t]*$', re.M)
# Un H1 qui n'est PAS un titre : un nom de fichier, un identifiant, un chemin. Ces lignes-là
# existent bel et bien dans le tronc (« on_fiche_write.py »), et les prendre pour un titre
# donnerait un panneau qui annonce un nom de fichier en gros.
RE_PAS_UN_TITRE = re.compile(r'^[\w./-]+\.(py|md|js|mjs|json|sh|html|ts|cjs)$|^`|^[A-Z_]{3,}$')


def titre_de(frontmatter_title, texte, nid):
    """Le titre affiché : `title:` du frontmatter, sinon le H1 du corps, sinon le nom de fichier.

    Avant (2026-08-14), il n'y avait que deux marches : `title:` ou le nom de fichier avec les
    tirets remplacés par des espaces. Or 258 fiches sur 359 n'ont pas de `title:` — le panneau
    affichait donc « email commit git fuite a la publication » en guise de titre d'article.
    115 de ces fiches portaient pourtant DÉJÀ un vrai titre, en H1, dans leur corps. Il n'était
    simplement jamais lu. La marche manquante coûtait plus cher que 115 réécritures à la main.

    Dernier recours, on remet au moins une majuscule : « capturer stderr dans un test le rend
    toujours vert » se lit mal, « Capturer stderr… » se lit.
    """
    if frontmatter_title and frontmatter_title.strip():
        return frontmatter_title.strip()
    m = RE_H1.search(texte)
    if m:
        h1 = m.group(1).strip().replace("`", "")
        if len(h1) >= 12 and " " in h1 and not RE_PAS_UN_TITRE.match(h1):
            return h1
    mots = nid.replace("-", " ").strip()
    return mots[:1].upper() + mots[1:]


EN_CLAIR = re.compile(r'^##[ \t]+En clair[ \t]*$(.*?)(?=^## |\Z)', re.M | re.S)


def extract_en_clair(text):
    """Le bloc « ## En clair » d'une fiche — la version humaine, sans jargon (4-6 lignes).

    Format tranché par l'auteur le 2026-08-14 : UN fichier, pas deux. Deux fichiers tenus à
    la main divergent toujours ; au bout d'un mois il y a deux vérités, donc aucune. Le
    bloc vit DANS la fiche, et c'est l'afficheur qui choisit ce qu'il montre en premier.
    Rend None si la fiche n'a pas encore de bloc — le panneau retombe alors sur `desc`.
    """
    m = EN_CLAIR.search(text)
    if not m:
        return None
    txt = re.sub(r"\[\[([^\]]+)\]\]", r"\1", m.group(1))
    txt = txt.replace("**", "").replace("`", "")
    # Les retours à la ligne du fichier servent la relecture du .md, pas l'affichage :
    # on recolle les paragraphes et on ne garde que les vraies coupures (ligne vide).
    paras = [" ".join(p.split()) for p in re.split(r"\n[ \t]*\n", txt) if p.strip()]
    return "\n\n".join(paras) or None


def clean_body(text):
    """Corps de la fiche nettoyé du markdown → explication longue, lisible, pour le panneau déplié."""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:]
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)        # images
    body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)          # [[lien]] → lien
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)     # [texte](url) → texte
    out = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            out.append("")
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)                     # titres
        s = re.sub(r"^[-*]\s+", "• ", s)                      # puces
        s = re.sub(r"^\d+\.\s+", "• ", s)                     # listes numérotées
        s = re.sub(r"^>\s?", "", s)                           # citations
        s = s.replace("**", "").replace("`", "").replace("*", "")
        out.append(s)
    txt = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    if len(txt) > 1600:                                       # coupe nette au mot + …
        txt = txt[:1600].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return txt


def scan():
    nodes = {}      # id -> {id, name, domain, group, desc, file}
    raw_links = []   # (src_id, target_name)
    types_liens = {}  # (src_id, target_name) -> "base_sur" | "contredit" | "remplace"
    embed2, sem_state, sem_detail = load_embed2()   # positions sémantiques + POURQUOI (Étage 1)
    heat, coact_edges, live, live_window_min = load_coact()   # chaleur + liens d'usage + activité en direct (Étage 2)
    challenges = load_challenges()             # avis du challenger par fiche (Étage 3)
    beliefs = load_beliefs()                   # convictions datées de l'auteur du tronc (Étage 3 : couche goût)
    media = load_media()                       # captures rejouables par fiche (Étage 4)
    reprises, reprises_indisponibles = load_reprises()   # fiches en tête des reprises (badge ↻)

    for domain in DOMAINS:
        root = os.path.join(BRAIN, domain)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                # on ne garde QUE des fiches de savoir : pas les README ni les docs
                if fn.lower() == "readme.md":
                    continue
                low = dirpath.lower()
                if os.sep + "documentation" in low or os.sep + "docs" in low:
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    text = open(path, encoding="utf-8").read()
                except Exception:
                    continue
                fm = frontmatter(text)
                m = FM_NAME.search(fm)
                if not m:
                    continue                     # pas de `name:` → ce n'est pas une fiche, on saute
                nid = m.group(1).strip()
                dm = FM_DESC.search(fm)
                desc = clean_desc(dm.group(1) if dm else "")
                tm = FM_TITLE.search(fm)
                title = titre_de(tm.group(1) if tm else None, text, nid)
                # sous-groupe = sous-dossier de projet (ex. mon-projet) sinon = domaine
                rel = os.path.relpath(dirpath, root)
                group = rel.split(os.sep)[0] if rel != "." else domain
                # appartenance déclarée : born_from (1+ projets), scale (centre↔périphérie)
                bm = FM_BORN.search(fm)
                born = [b.strip().strip("[]\"'") for b in bm.group(1).split(",")] if bm else []
                born = [b for b in born if b]
                sm = FM_SCALE.search(fm)
                scale = float(sm.group(1)) if sm else guess_scale(nid)
                rel_file = os.path.relpath(path, BRAIN)
                # ── AXE THÉMATIQUE (2026-08-14) : la famille de la fiche, pour que la
                # planète puisse montrer le SUJET et pas seulement le dossier. Les dossiers
                # disent la portée, les familles disent de quoi ça parle — deux axes.
                tm = re.search(r"^tags:\s*\[(.*?)\]", fm, re.M)
                tags = [t.strip() for t in tm.group(1).split(",") if t.strip()] if tm else []
                nodes[nid] = {"id": nid, "name": nid, "title": title, "domain": domain,
                              "group": group, "desc": desc, "tags": tags,
                              "born_from": born, "scale": scale,
                              "type": (FM_TYPE.search(fm).group(1) if FM_TYPE.search(fm) else None),
                              "en_clair": extract_en_clair(text),  # version humaine, affichée en 1er
                              "long": clean_body(text),
                              "embed2": embed2.get(rel_file),   # [x,y] sémantique ou None
                              "heat": heat.get(nid, 0.0),        # chaleur d'usage 0..1 (Étage 2)
                              "active": rel_file in live,        # LUE à l'instant (fenêtre glissante, Étage 2)
                              "active_ts": live.get(rel_file),   # horodatage de cette lecture → extinction côté visualizer
                              "challenge": challenges.get(rel_file),   # avis du challenger (Étage 3) ou None
                              "conviction": beliefs.get(rel_file),     # conviction datée de l'auteur du tronc (Étage 3) ou None
                              "media": media.get(rel_file),            # capture rejouable (Étage 4) ou None
                              "resume": rel_file in reprises,    # fait partie des reprises en tête (badge ↻)
                              "file": rel_file}
                # liens sortants (dédupliqués plus bas)
                for tgt in set(LINK.findall(text)):
                    raw_links.append((nid, tgt.strip()))
                # relations TYPÉES du frontmatter (cf. jardinage-regles §4 bis).
                # Elles n'ajoutent pas d'arête : elles QUALIFIENT celle qui existe déjà,
                # puisque la convention impose de garder le [[slug]] dans le corps.
                for typ, cibles in _relations(text).items():
                    for c in cibles:
                        types_liens[(nid, c)] = typ

    # ne garde que les liens dont la cible est une fiche connue (pas les [[à écrire]])
    ids = set(nodes)
    seen = set()
    links = []
    for src, tgt in raw_links:
        if tgt in ids and src != tgt and (src, tgt) not in seen and (tgt, src) not in seen:
            seen.add((src, tgt))
            arete = {"source": src, "target": tgt}
            typ = types_liens.get((src, tgt)) or types_liens.get((tgt, src))
            if typ:
                arete["type"] = typ
            links.append(arete)

    # ---------- RÈGLES TRANSVERSES : une étiquette, plus un voisin ----------
    # `verifier-le-code-jamais-supposer` est cité par 77 fiches sur 359, `verifier-le-rendu-final`
    # par 49. À ce niveau, une règle n'est plus un VOISIN de la fiche — c'est une ÉTIQUETTE posée
    # dessus, et les 215 arcs qui en partent forment l'essentiel du nuage gris.
    # On ne supprime AUCUN lien : le savoir reste, le panneau les liste toujours. On les marque,
    # et le viewer ne les dessine qu'au survol.
    # Le critère n'est pas un seuil inventé : c'est le `type:` déclaré dans le frontmatter.
    # `type: feedback` = une règle de travail de l'auteur ; `type: project` = une fiche de projet,
    # qui a le droit d'être un hub de son domaine (`claude-brain`, 41 liens, en est un et doit
    # le rester). Le degré ne sert qu'à distinguer la règle omniprésente de celle citée trois fois.
    DEGRE_ETIQUETTE = 20            # ~5 % du tronc : au-delà, la règle est partout
    degres = Counter()
    for l in links:
        degres[l["source"]] += 1
        degres[l["target"]] += 1
    regles = {nid for nid, n in nodes.items()
              if n.get("type") == "feedback" and degres[nid] >= DEGRE_ETIQUETTE}
    for nid, n in nodes.items():
        n["regle"] = nid in regles
    for l in links:
        if l["source"] in regles or l["target"] in regles:
            l["regle"] = True

    # ---------- APPARTENANCE (modèle continent/ville/frontière) ----------
    # « villes » = les sous-dossiers du domaine projects (chaque projet est une ville).
    projects = sorted({n["group"] for n in nodes.values() if n["domain"] == "projects"})
    proj_set = set(projects)
    # voisinage non orienté vers les fiches de projet (pour l'appartenance douce des leçons)
    proj_of = {nid: n["group"] for nid, n in nodes.items() if n["domain"] == "projects"}
    adj_proj = {nid: [] for nid in nodes}       # nid -> [groupes de projet reliés]
    for l in links:
        s, t = l["source"], l["target"]
        if s in proj_of and t not in proj_of:
            adj_proj[t].append(proj_of[s])
        elif t in proj_of and s not in proj_of:
            adj_proj[s].append(proj_of[t])

    for nid, n in nodes.items():
        m = {}
        if n["domain"] == "projects":                       # fiche déjà dans une ville
            m[n["group"]] = m.get(n["group"], 0.0) + W_PRIMARY
        for b in n["born_from"]:                              # née d'un projet, rangée ailleurs
            if b in proj_set:
                m[b] = m.get(b, 0.0) + W_BORN
        for g in adj_proj[nid]:                               # tirée par les liens vers un projet
            m[g] = m.get(g, 0.0) + W_LINK
        if not m:
            n["membership"] = {}                             # hors-ville (méta/vie pures)
            n["primary_project"] = None
            n["frontier"] = False
            continue
        # poids ABSOLUS ancrés sur W_PRIMARY=1.0 (pas de normalisation par le max :
        # un simple lien reste ténu ~0.20, il ne doit pas se gonfler en pleine appartenance)
        m = {k: round(min(v, 1.0), 3) for k, v in m.items()}
        n["membership"] = dict(sorted(m.items(), key=lambda kv: -kv[1]))
        mx = max(m.values())
        # une fiche n'a une VILLE que si son appartenance est FORTE (dossier d'origine ou born_from).
        # Un simple lien (~0.18) ne suffit pas → l'agent/méta qui mentionne un projet n'y est pas classé.
        n["primary_project"] = max(m, key=m.get) if mx >= HOME_MIN else None
        # frontière = a une vraie ville maison ET une 2ᵉ ville ≥ seuil (ex. VoiceShell)
        n["frontier"] = (n["primary_project"] is not None
                         and sum(1 for v in m.values() if v >= FRONTIER_MIN) >= 2)

    # LA COUVERTURE SE COMPTE SUR LES FICHES, pas sur la taille du cache : une entrée qui
    # ne correspond à aucune fiche actuelle ne place personne, et un cache de 400 clés
    # périmées se lirait sinon comme une santé parfaite.
    sem_covered = sum(1 for n in nodes.values() if n.get("embed2"))
    return {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        # LE HEAD QUE CE GRAPHE DÉCRIT (2026-08-20). Le badge ↻ est un INSTANTANÉ ;
        # les reprises proposées au démarrage sont un RECALCUL. Depuis que le
        # classement suit la date de commit, les deux concordent tant qu'ils parlent
        # du même HEAD — et divergent légitimement dès qu'un commit passe. Sans ce
        # champ, « périmé » et « incohérent » sont indiscernables.
        "head": _head_courant(),
        "reprises_indisponibles": reprises_indisponibles,
        "counts": {"nodes": len(nodes), "links": len(links),
                   "projects": len(projects),
                   "frontier": sum(1 for n in nodes.values() if n.get("frontier")),
                   "challenged": sum(1 for n in nodes.values() if n.get("challenge")),
                   "convictions": sum(1 for n in nodes.values() if n.get("conviction")),
                   "media": sum(1 for n in nodes.values() if n.get("media")),
                   "active": sum(1 for n in nodes.values() if n.get("active")),
                   "resume": sum(1 for n in nodes.values() if n.get("resume")),
                   "regles": sum(1 for n in nodes.values() if n.get("regle")),
                   # compteur d'avancement de la conversion : combien de fiches ont déjà
                   # leur version humaine. Sans lui, « on en a fait 10 » n'est vérifiable
                   # nulle part et la campagne s'oublie à mi-chemin.
                   "en_clair": sum(1 for n in nodes.values() if n.get("en_clair"))},
        "domains": DOMAINS,
        # fenêtre de l'ACTIVITÉ EN DIRECT (minutes) : le visualizer éteint lui-même un anneau
        # dont `active_ts` est sorti de la fenêtre, sans attendre une régénération du graphe.
        "live_window_min": live_window_min,
        "projects": projects,
        "nodes": sorted(nodes.values(), key=lambda n: (n["domain"], n["group"], n["id"])),
        "links": links,
        # liens d'USAGE (co-activation) : fiches activées ensemble en session, ≠ liens déclarés (Étage 2)
        "coact": [e for e in coact_edges if e[0] in ids and e[1] in ids],
        # LA CAPACITÉ SÉMANTIQUE, DÉCLARÉE — pas supposée. L'afficheur lisait l'absence de
        # vecteurs comme « rien à signaler » et gardait sa formulation nominale ; on lui dit
        # désormais, en toutes lettres, combien de fiches sont réellement posées par le sens
        # et pourquoi les autres ne le sont pas. `covered == 0` AVEC un cache lisible n'est
        # pas « en cours » : le cache existe et ne correspond à aucune fiche actuelle (clés
        # périmées, tronc déplacé), ce qu'un lecteur doit VOIR, pas deviner.
        "semantic": {
            "state": (sem_state if sem_state != "ready" else
                      "ready" if nodes and sem_covered == len(nodes) else
                      "partial" if sem_covered else "broken"),
            "covered": sem_covered,
            "total": len(nodes),
            "detail": (sem_detail if sem_detail else
                       "" if sem_covered == len(nodes) else
                       f"state/embed2.json ne correspond à aucune des {len(nodes)} fiches — cache périmé"
                       if not sem_covered else
                       f"{len(nodes) - sem_covered} fiche(s) écrite(s) depuis la dernière indexation"),
        },
    }


# ── LE VOCABULAIRE DES RELATIONS — fermé, décidé par l'auteur le 2026-09-17 (ADR-0019) ──
# Quatre types qui disent chacun une chose précise, plus UN fourre-tout qui doit dire pourquoi.
# Le fourre-tout existe parce que le refuser ne supprime pas le besoin, il le pousse vers des
# mots inventés que l'export jette en silence : mesuré le 17/09, `voisin_de` — qui n'existe
# dans aucun vocabulaire — portait 239 liens, 42 % du total, et disparaissait sans un mot.
#   base_sur   cette fiche PRÉSUPPOSE l'autre
#   precise    cette fiche affine l'autre sans la contredire (37 liens l'utilisaient déjà)
#   contredit  les deux ne peuvent pas être vraies ensemble
#   remplace   l'autre est morte, celle-ci prend la suite (SEUL type actif : sort du rappel)
#   lie_a      tout le reste — n'est complet qu'accompagné de sa raison, en une phrase
TYPES_RELATION = ("base_sur", "precise", "contredit", "remplace", "lie_a")

# DEUX FORMES, parce que les deux étaient déjà écrites dans le tronc le 17/09 :
#     base_sur: [a, b]         la forme courte — 558 liens ;
#     base_sur:                la forme bloc (liste YAML) — 5 fiches, et elle était jetée EN
#       - a                    SILENCE, l'analyseur n'acceptant que les crochets ;
#     lie_a:                   la forme bloc porte en plus la raison, après deux-points.
#       - a: parce que …
# `- a: raison` est du YAML valide (une liste d'associations), donc un lecteur YAML réel ne
# s'étrangle pas dessus le jour où il en passe un.
_REL_BLOC = re.compile(r"^relations:\s*$(.*?)(?=^\S|\Z)", re.M | re.S)
_REL_LIGNE = re.compile(r"^\s+(\w+)\s*:\s*\[([^\]]*)\]", re.M)
_REL_TETE = re.compile(r"^\s+(\w+)\s*:\s*$")
_REL_ITEM = re.compile(r"""^\s+-\s+["']?([^:"'\n]+?)["']?\s*(?::\s*(\S.*?))?\s*$""")


def relations_brutes(bloc):
    """[(type, cible, raison|None)] pour TOUT ce qui est écrit sous `relations:`, sans filtrer
    sur TYPES_RELATION. C'est ce que lit le docteur pour NOMMER les types que l'export va
    jeter : il ne peut le dire que s'il voit d'abord ce qui est écrit, y compris l'inconnu."""
    out, courant = [], None
    for ligne in bloc.split("\n"):
        m = _REL_LIGNE.match(ligne)
        if m:
            courant = None
            for c in m.group(2).split(","):
                c = c.strip().strip('"\'')
                if c:
                    out.append((m.group(1), c, None))
            continue
        m = _REL_TETE.match(ligne)
        if m:
            courant = m.group(1)
            continue
        m = _REL_ITEM.match(ligne) if courant else None
        if m:
            out.append((courant, m.group(1).strip(), (m.group(2) or "").strip() or None))
        elif ligne.strip():
            courant = None
    return out


def _relations(text):
    """Lit le bloc `relations:` du frontmatter. Silencieux si absent ou mal formé —
    un frontmatter bancal ne doit jamais faire tomber l'export du graphe."""
    fm = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not fm:
        return {}
    bloc = _REL_BLOC.search(fm.group(1) + "\n")
    if not bloc:
        return {}
    out = {}
    for typ, cible, _raison in relations_brutes(bloc.group(1)):
        if typ in TYPES_RELATION:
            out.setdefault(typ, []).append(cible)
    return out


def main():
    try:
        data = scan()
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        # ---------- LE CORPS DES FICHES PART DANS SON PROPRE FICHIER ----------
        # `long` (la fiche entière, dense) pesait 536 Ko des 1051 Ko de graph.json : plus de la
        # MOITIÉ du fichier, pour un texte que seul le panneau DÉPLIÉ affiche — donc jamais au
        # chargement, et jamais pour les 358 fiches qu'on ne déplie pas. La page revalide
        # graph.json toutes les 3 s ; le jour où le serveur répond 200 plutôt que 304 (fiche
        # modifiée, ce qui arrive à chaque passage de hook), c'est 1 Mo qui repart pour rien.
        # Les textes vivent maintenant à côté, chargés au premier dépliage et gardés en cache.
        textes = {n["id"]: n.pop("long") for n in data["nodes"] if n.get("long")}
        # ---------- ET LE BLOC « EN CLAIR » SUIT LE MÊME CHEMIN ----------
        # La campagne du 2026-08-14 a donné son bloc humain aux 362 fiches. Excellent pour la
        # lecture — et graph.json est repassé de 472 Ko à 1309 Ko, dont 826 Ko pour ce seul
        # champ. Le dégonflage de la veille était annulé par le chantier du lendemain.
        # Or le SURVOL n'affiche que le PREMIER PARAGRAPHE (`en_clair.split('\n\n')[0]` côté
        # viewer) ; le bloc entier ne sert qu'au panneau déplié, comme `long`. On ne garde donc
        # que ce premier paragraphe — 60 Ko au lieu de 826 — et le reste part avec les textes.
        for n in data["nodes"]:
            plein = n.get("en_clair")
            if not plein:
                continue
            textes[n["id"] + "::clair"] = plein
            n["en_clair"] = plein.split("\n\n")[0]
        # ⚠️ ÉCRITURE ATOMIQUE — SINON LA PLANÈTE SE RETROUVE AVEC UN GRAPHE ILLISIBLE.
        # `open(OUT, "w")` tronque le fichier puis le réécrit : pendant ce temps, quiconque lit
        # obtient un fichier à moitié écrit, et deux exports lancés en même temps (la ronde
        # launchd et la boucle d'entretien) entrelacent leurs octets. Constaté le 2026-08-14 :
        #   "target": "une-fiche-quel"une-fiche-quelconque,
        # JSON invalide → la page charge 0 fiche et n'affiche RIEN, sans la moindre erreur
        # visible (le fetch réussit, c'est le parse qui échoue, dans un `catch` silencieux).
        # On écrit donc à côté, puis on bascule d'un coup : `os.replace` est atomique, un lecteur
        # voit toujours l'ancien fichier OU le nouveau, jamais un mélange des deux.
        def ecrire_atomique(chemin, charge, indent=None):
            tmp = f"{chemin}.{os.getpid()}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(charge, f, ensure_ascii=False, indent=indent)
                    f.flush()
                    os.fsync(f.fileno())          # les octets sont sur le disque avant la bascule
                os.replace(tmp, chemin)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        # les textes d'abord : le graphe qui les référence ne doit jamais arriver avant eux
        ecrire_atomique(OUT_TEXTES, textes)               # pas d'indent : personne ne le lit à l'œil
        ecrire_atomique(OUT, data, indent=1)
        if sys.stdout.isatty():
            c = data["counts"]
            ko = lambda p: round(os.path.getsize(p) / 1024)
            print(f"🪐 graph.json écrit : {c['nodes']} points, {c['links']} liens → {os.path.relpath(OUT, BRAIN)}"
                  f" ({ko(OUT)} Ko + {ko(OUT_TEXTES)} Ko de textes à la demande)")
    except Exception as e:
        if sys.stdout.isatty():
            print(f"graph_export: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
    sys.exit(0)
