#!/usr/bin/env python3
"""
Hook PostToolUse (Write|Edit) du C Brain — garde mécanique instantanée.
À CHAQUE fiche déposée dans le tronc, sans LLM, sans boucle, sans bloquer :
  1. masque tout secret en clair
  2. vérifie que la fiche est dans la carte MEMORY.md + lessons/INDEX.md
     (sinon -> state/a-classer.md ; la carte elle-même n'est jamais écrite ici, ADR-0015)
  3. signale si le frontmatter manque

Anti-boucle : ce script édite les fichiers en I/O direct Python (pas via l'outil
Write/Edit), donc il ne re-déclenche jamais le hook. Le travail sémantique
(dédup, reclassement, distillation) reste aux agents LLM jardinier/distillateur.

Règle d'or : ne JAMAIS bloquer. Sort toujours 0.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status
except Exception:
    def write_status(*a, **k): pass

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
LESSONS_INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")
MAP_RELS = {"MEMORY.md", os.path.join("lessons", "INDEX.md")}

# Vocabulaire des types de fiche. CINQ valeurs, pas quatre : `lesson` a été ajouté
# le 2026-08-13 parce que 32 fiches l'utilisaient déjà et que c'est la catégorie la
# plus utile d'un tronc dont 205 fiches vivent dans `lessons/`. Divergence assumée
# avec la spec mémoire du harnais (qui en liste 4) — ne pas la « réparer » à 4.
TYPES_VALIDES = {"project", "feedback", "reference", "lesson", "user"}

SECRET = re.compile(
    r'(ntn_[A-Za-z0-9]+|sk-ant-[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+|secret_[A-Za-z0-9]+'
    r'|eyJ[A-Za-z0-9_.-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})'
)

def get_target(data):
    ti = (data or {}).get("tool_input", {}) or {}
    return ti.get("file_path") or ti.get("path")

def main(data):
    fp = get_target(data)
    if not fp:
        return
    real = os.path.realpath(fp)
    # uniquement les fiches du tronc
    if not real.startswith(BRAIN + os.sep):
        return
    rel = os.path.relpath(real, BRAIN)

    # --- pulse de statut pour la capsule (toute activité sur l'arbre) ---
    name = os.path.basename(rel)[:-3] if rel.endswith(".md") else os.path.basename(rel)
    if rel in MAP_RELS:
        write_status("busy", "mapping", "mise à jour de la carte")
    elif rel.endswith(".md") and not rel.startswith("sessions" + os.sep):
        write_status("busy", "filing", name)

    # exclure la carte elle-même, l'archive auto, et les non-.md du travail mécanique
    if rel in MAP_RELS or rel.startswith("sessions" + os.sep) or not rel.endswith(".md"):
        return
    if not os.path.exists(real):
        return
    try:
        txt = open(real, encoding="utf-8").read()
    except Exception:
        return

    # --- LEDGER « sauvegardes manuelles » (anti-redondance distillateur) ---
    # Si TU (la session en cours, pas le jardinier headless) écris/affines une fiche de savoir,
    # on le note par session_id. Au SessionEnd, le distillateur recevra « ne recrée pas ces fiches »
    # → il ne refait pas le travail déjà fait à la main (tokens économisés, zéro doublon), tout en
    # gardant le filet auto pour le savoir NON sauvé. Foreground seulement, zones de savoir seulement.
    if os.environ.get("CLAUDE_BRAIN_GARDENING") != "1":
        sid = (data or {}).get("session_id")
        if sid and rel.split(os.sep)[0] in ("projects", "lessons", "meta", "life"):
            try:
                import time
                led = os.path.join(BRAIN, "state", "manual-saves.jsonl")
                os.makedirs(os.path.dirname(led), exist_ok=True)
                with open(led, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": int(time.time()), "sid": sid, "path": rel},
                                       ensure_ascii=False) + "\n")
            except Exception:
                pass

    # détection de cohérence (Horizon 2) : flag des fiches qui se recouvrent, détaché
    try:
        import subprocess
        cc = os.path.join(BRAIN, "hooks", "check_coherence.py")
        if os.path.exists(cc):
            subprocess.Popen([sys.executable, cc, real],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

    # --- 1. masquage des secrets (in place, I/O direct) ---
    masked = SECRET.sub("«SECRET-MASQUÉ»", txt)
    if masked != txt:
        try:
            open(real, "w", encoding="utf-8").write(masked)
            txt = masked
            write_status("busy", "correcting", f"secret masqué dans {name}")
        except Exception:
            pass

    # --- 1 bis. vocabulaire des types : OBSERVER, jamais bloquer ni corriger ---
    # Pourquoi ce contrôle existe : mesuré le 2026-08-13, le champ `type` avait dérivé
    # (`lessons` au pluriel, faute de frappe pure) sans que rien ne s'en aperçoive —
    # le garde vérifiait la PRÉSENCE du frontmatter, jamais la VALIDITÉ de ses valeurs.
    # Un standard que rien ne contrôle dérive toujours.
    #
    # On consigne, on ne répare pas : `type` n'est lu par aucun code (vérifié), donc une
    # valeur inattendue n'a jamais d'effet mécanique. C'est une question de vocabulaire,
    # elle se tranche fiche par fiche, par le jardinier — pas par une substitution muette.
    try:
        mt = re.search(r'^\s*type:\s*(\S+)\s*$', txt[:1200], re.M)
        if mt and mt.group(1) not in TYPES_VALIDES:
            import time
            with open(os.path.join(BRAIN, "state", "types-hors-vocabulaire.jsonl"),
                      "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": int(time.time()), "path": rel,
                                    "type": mt.group(1)}, ensure_ascii=False) + "\n")
            write_status("busy", "correcting", f"type inconnu « {mt.group(1)} » dans {name}")
    except Exception:
        pass

    # --- 1 ter. vocabulaire de l'ADR-0019 : OBSERVER À L'ÉCRITURE, jamais bloquer ---
    # Décidé par l'auteur le 2026-09-17 : le sujet est obligatoire sur les fiches NEUVES seulement.
    # Cette règle ne peut pas se tenir chez le docteur, qui voit les 686 fiches d'un coup et
    # accuserait les 51 anciennes sans sujet ; elle se tient au SEUL moment où « neuve » a un
    # sens — celui où la fiche est écrite. Même forme que le contrôle 1 bis juste au-dessus :
    # on consigne, on ne répare pas, on ne bloque pas.
    #
    # Le vocabulaire n'est pas recopié, il est IMPORTÉ : `TYPES_RELATION` et son lecteur
    # viennent de hooks/graph_export.py, les 12 sujets de meta/topics.json via topics_fiche.
    # Une troisième copie serait une troisième chose à faire diverger — c'est exactement la
    # dérive que l'ADR-0019 vient de mesurer (309 liens qualifiés sur 563 jetés en silence).
    #
    # CE JOURNAL A UN LECTEUR NOMMÉ, et c'est la condition pour l'écrire : l'ADR-0019 pose
    # comme hypothèse réfutable qu'obliger `lie_a` à porter sa raison produit des raisons
    # réellement écrites. L'expérience qui la réfute est « compter, deux semaines après le
    # 17/09, les fiches écrites APRÈS cette date qui manquent à la règle » — et seul un
    # journal daté à l'écriture sait distinguer ces fiches-là des anciennes.
    if rel.split(os.sep)[0] in ("projects", "lessons", "meta", "life"):
        try:
            import time
            import topics_fiche
            from graph_export import TYPES_RELATION, _REL_BLOC, relations_brutes
            fm = re.match(r"^---\n(.*?)\n---", txt, re.S)
            ecarts = []
            if fm:
                topic, secondaires = topics_fiche.lire(txt)
                if not topic:
                    ecarts.append({"champ": "sujet", "ecart": "absent"})
                elif isinstance(topic, list):     # clé `topic:` écrite deux fois — cf. topics_fiche.lire
                    ecarts.append({"champ": "sujet", "ecart": "dedouble", "valeur": ", ".join(topic)})
                elif topic not in topics_fiche.ids_canoniques():
                    ecarts.append({"champ": "sujet", "ecart": "hors-vocabulaire", "valeur": topic})
                bloc_rel = _REL_BLOC.search(fm.group(1) + "\n")
                if bloc_rel:
                    for typ, cible, raison in relations_brutes(bloc_rel.group(1)):
                        if typ not in TYPES_RELATION:
                            ecarts.append({"champ": "relation", "ecart": "type-hors-vocabulaire",
                                           "valeur": typ, "cible": cible})
                        elif typ == "lie_a" and not raison:
                            ecarts.append({"champ": "relation", "ecart": "lie_a-sans-raison",
                                           "cible": cible})
            if ecarts:
                journal = os.path.join(BRAIN, "state", "vocabulaire-a-l-ecriture.jsonl")
                os.makedirs(os.path.dirname(journal), exist_ok=True)
                with open(journal, "a", encoding="utf-8") as f:
                    for e in ecarts:
                        f.write(json.dumps(dict(e, ts=int(time.time()), path=rel),
                                           ensure_ascii=False) + "\n")
                premier = ecarts[0]
                write_status("busy", "correcting",
                             f"{premier['champ']} {premier['ecart']} dans {name}")
        except Exception:
            pass

    # slug / nom pour la détection de présence dans la carte
    m = re.search(r'^name:\s*(.+)$', txt, re.M)
    slug = m.group(1).strip() if m else None
    fname = os.path.basename(rel)[:-3]

    # --- 2. garantir la présence dans la carte composée ---
    try:
        mem = open(MEMORY, encoding="utf-8").read()
    except Exception:
        return
    try:
        lessons_index = open(LESSONS_INDEX, encoding="utf-8").read()
    except Exception:
        lessons_index = ""  # repli migration/récupération : l'Inbox reste fonctionnelle
    card = mem + "\n" + lessons_index
    linked = (rel in card) or (fname in card) or (slug and f"[[{slug}]]" in card) \
             or (slug and f"({rel})" in card)
    # LA FILE N'EST PLUS DANS MEMORY.md (2026-09-15). Ce dépôt date du 21/06, d'avant deux
    # décisions qui l'ont rendu impossible : le budget de 20 000 octets de la carte, et
    # ADR-0015 (le manifeste fait autorité, toute entrée de carte est validée par un humain).
    # Mesuré le 15/09 sur une copie : MEMORY.md à 90 octets du budget, UNE ligne d'Inbox la
    # passait à 20 003 octets et le pre-commit refusait tout commit, toutes zones confondues.
    # La fiche attend donc dans state/a-classer.md ; le jardinier PROPOSE sa place dans
    # state/a-valider.md ; un humain l'inscrit dans la carte et réconcilie le manifeste.
    # Plus de course avec le jardinier (il ne touche plus la carte) : le dépôt vaut aussi
    # pendant une passe de maintenance, sinon les fiches écrites par un robot seraient perdues de vue.
    if not linked:
        a_classer = os.path.join(BRAIN, "state", "a-classer.md")
        deja = ""
        for p in (a_classer, os.path.join(BRAIN, "state", "a-valider.md")):
            try:
                deja += open(p, encoding="utf-8").read()
            except Exception:
                pass
        if f"({rel})" not in deja:
            title = slug or fname
            try:
                with open(a_classer, "a", encoding="utf-8") as f:
                    f.write(f"- [{title}]({rel}) — pas encore dans la carte\n")
            except Exception:
                pass

def refresh_doctor():
    """Rafraîchit state/doctor.json en arrière-plan (détaché, jamais bloquant)."""
    try:
        import subprocess
        doc = os.path.join(BRAIN, "hooks", "brain_doctor.py")
        if os.path.exists(doc):
            subprocess.Popen([sys.executable, doc, "--json"],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

def refresh_planet():
    """Régénère planet/graph.json — la PLANÈTE de connaissance grandit en temps réel
    à chaque fiche écrite (détaché, jamais bloquant)."""
    try:
        import subprocess
        ge = os.path.join(BRAIN, "hooks", "graph_export.py")
        if os.path.exists(ge):
            subprocess.Popen([sys.executable, ge],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    fp = get_target(data)
    in_brain = bool(fp) and os.path.realpath(fp).startswith(BRAIN + os.sep)
    try:
        main(data)
    except Exception:
        pass
    # refresh des artefacts (doctor.json + planet/graph.json) UNIQUEMENT pour une écriture DANS
    # le tronc. Avant, le hook étant global (Write|Edit), CHAQUE édition de n'importe quel projet
    # lançait 2 scans complets du Brain et appendait une ligne à metrics.jsonl (sur-fréquence +
    # courbe polluée). On gate sur l'appartenance au tronc.
    if in_brain:
        try:
            refresh_doctor()
        except Exception:
            pass
        try:
            refresh_planet()
        except Exception:
            pass
    sys.exit(0)
