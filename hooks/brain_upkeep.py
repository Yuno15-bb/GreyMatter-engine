#!/usr/bin/env python3
"""brain_upkeep — SECONDE COUCHE autonome du C Brain (veille de cohésion).

La boucle SessionEnd (auto_maintain.py) ne réveille que 2 agents sur 7 :
  distillateur (écrit) → jardinier (range) → commit.
Les 4 agents de VEILLE (challenger, architecte, archiviste, mécanicien) ne
tournaient qu'à la main. Ce module les branche dans l'auto, SANS exploser le coût.

Principe « cadence + seuil capteur » :
  1. O1 — on ne RÉGÉNÈRE que les capteurs des agents dont le cooldown est ouvert
     (gratuits, zéro LLM ; inutile de recalculer la topologie si l'architecte dort) :
       brain_topology --json  → state/topology.json   (architecte)
       brain_utility  --json  → state/utility.json     (archiviste)
       brain_doctor   --json  → state/doctor.json       (mécanicien)
       coherence.json         → accumulé par check_coherence (challenger, pas de régén)
  2. chaque agent n'est ÉLIGIBLE que si SON capteur dépasse un seuil
     (vrai travail à faire) ET qu'il a respecté son cooldown (pas de thrash).
  3. on n'en réveille AU PLUS UN par passage (garantie de coût : ~1 run LLM
     en plus, et seulement quand il y a réellement matière). Sur la durée,
     toutes les dimensions finissent tendues, par priorité.
  F1 — résilience quota : preflight AVANT dépense, et cooldown gravé SEULEMENT si
     l'agent a réellement réussi (un échec quota/login est réessayé, pas « brûlé »).

Séparation des pouvoirs respectée : ICI on MESURE + on DÉCIDE qui réveiller ;
l'agent LLM, lui, JUGE et agit. On ne touche jamais au contenu des fiches.

Appelé depuis le wrapper headless de auto_maintain (déjà sous quota préflighté,
CLAUDE_BRAIN_GARDENING=1). Best-effort : si un agent échoue (quota/login), la
veille est simplement sautée — contrairement à la distillation, rien n'est perdu.

Usage :
  brain_upkeep.py decide        → JSON de la décision (debug, zéro effet)
  brain_upkeep.py run [sid]      → régénère, décide, réveille au plus 1 agent
Sort toujours 0 (ne bloque jamais un hook).
"""
import os, sys, json, time, shutil, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status, journal_agent
except Exception:
    def write_status(*a, **k): pass
    def journal_agent(*a, **k): return None
try:
    import brain_guard as guard          # résilience quota/compte (même garde que la couche 1)
except Exception:
    guard = None

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
HOOKS = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BRAIN, "state")
CADENCE = os.path.join(STATE, "upkeep.json")   # mémoire des derniers réveils
LOG = os.path.join(BRAIN, "sessions", "gardening.log")
COST = os.path.join(BRAIN, "sessions", "cost.jsonl")

# Cooldown : un même agent ne se relance pas avant N heures, même si son capteur
# reste au-dessus du seuil (anti-thrash : laisse le temps qu'une passe porte ses
# fruits avant d'en redemander une).
COOLDOWN_H = 12

# Priorité de réveil (au plus un par passage) : l'honnêteté d'abord (contradictions),
# puis la cohésion (liens/îlots), l'élagage (poids mort), enfin l'infra (défauts doctor).
ORDER = ["challenger", "architecte", "archiviste", "mecanicien"]

# Modèle par agent (cohérent avec leur frontmatter ; le shell parent force haiku
# pour distill/jardin, ici on respecte le besoin réel de chaque rôle).
MODEL = {"architecte": "sonnet", "challenger": "sonnet",
         "archiviste": "haiku", "mecanicien": "sonnet"}

# Activité capsule par agent (clés DÉJÀ reconnues par capsule/index.html : la
# créature montre le bon rôle au travail). L'architecte a SA scène propre
# ('architecting' : ponts inter-domaines) — distincte du 'mapping' du jardinier.
ACT = {"architecte": "architecting", "challenger": "challenging",
       "archiviste": "archiving", "mecanicien": "auditing"}

# Capteur mécanique à régénérer pour CHAQUE agent (optimisation O1 : on ne régénère
# QUE les capteurs des agents dont le cooldown est ouvert — inutile de recalculer la
# topologie TF-IDF de 151 fiches si l'architecte est de toute façon en cooldown).
# Le challenger n'a pas de capteur à régénérer (coherence.json est accumulé en
# continu par check_coherence à chaque écriture de fiche).
REGEN = {"architecte": ("brain_topology.py", ["--json"]),
         "archiviste": ("brain_utility.py", ["--json"]),
         "mecanicien": ("brain_doctor.py", ["--json"])}


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def regen_sensors(agents):
    """Régénère SEULEMENT les capteurs des `agents` donnés (cheap, zéro LLM).
    Optimisation O1 : on ne recalcule pas un capteur dont l'agent est en cooldown."""
    py = sys.executable
    seen = set()
    for ag in agents:
        spec = REGEN.get(ag)
        if not spec or spec[0] in seen:
            continue
        mod, flags = spec
        seen.add(mod)
        try:
            subprocess.run([py, os.path.join(HOOKS, mod), *flags],
                           cwd=BRAIN, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=60)
        except Exception:
            pass  # capteur muet → l'agent concerné sera simplement jugé non éligible


def sensor_signal():
    """Lit les 4 capteurs et renvoie, par agent, (a-t-il du travail ?, raison lisible)."""
    topo = load_json(os.path.join(STATE, "topology.json"), {})
    util = load_json(os.path.join(STATE, "utility.json"), {})
    coh = load_json(os.path.join(STATE, "coherence.json"), [])
    doc = load_json(os.path.join(STATE, "doctor.json"), {})

    n_miss = len(topo.get("liens_manquants", []))
    n_iso = len(topo.get("isolees", []))
    n_bad = len(topo.get("placement_incoherent", []))
    n_comp = topo.get("n_composantes", 1)
    n_dead = len(util.get("poids_mort", []))
    # Un capteur compte des UNITÉS DE TRAVAIL, pas des lignes. coherence.json peut porter
    # des notes d'arbitrage (« ✓ faux positif ») laissées par un agent : les compter
    # gardait le challenger éligible à vie → un run sonnet toutes les 12 h pour rien, qui
    # préemptait l'architecte (1er dans ORDER). Seule une paire (a,b) est du travail.
    n_contra = sum(1 for f in coh if isinstance(f, dict)
                   and isinstance(f.get("a"), str) and isinstance(f.get("b"), str)
                   ) if isinstance(coh, list) else 0
    n_defaut = doc.get("total", 0) if isinstance(doc, dict) else 0

    sig = {}
    # ARCHITECTE : la cohésion globale s'effrite — îlot détaché, fiche isolée,
    # placement douteux, ou un tas de liens évidents manquants.
    arch_ok = n_iso >= 1 or n_bad >= 3 or n_comp >= 2 or n_miss >= 8
    sig["architecte"] = (arch_ok,
        f"{n_miss} liens manquants, {n_iso} isolées, {n_bad} placements douteux, "
        f"{n_comp} composante(s)")
    # CHALLENGER : au moins une paire signalée « doublon OU contradiction » à trancher.
    sig["challenger"] = (n_contra >= 1, f"{n_contra} recouvrement(s) fort(s) à arbitrer")
    # ARCHIVISTE : du poids mort s'accumule (fiches froides candidates à l'archivage).
    sig["archiviste"] = (n_dead >= 3, f"{n_dead} fiche(s) en poids mort")
    # MÉCANICIEN : le docteur signale des défauts d'infra (liens morts, orphelins,
    # frontmatter, nommage, hors-index). Ne se réveille QUE s'il y a un vrai défaut —
    # donc rare, exactement quand on en a besoin (sinon doctor.total = 0).
    sig["mecanicien"] = (n_defaut >= 1, f"{n_defaut} défaut(s) infra signalé(s) par le docteur")
    return sig


def cooldown_ok(agent, now):
    cad = load_json(CADENCE, {})
    last = cad.get(agent, {}).get("last_ts", 0)
    return (now - last) >= COOLDOWN_H * 3600


def record_run(agent, now):
    cad = load_json(CADENCE, {})
    ent = cad.get(agent, {})
    ent["last_ts"] = now
    ent["runs"] = ent.get("runs", 0) + 1
    cad[agent] = ent
    try:
        os.makedirs(STATE, exist_ok=True)
        json.dump(cad, open(CADENCE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def decide(now=None):
    """Renvoie l'agent à réveiller (ou None) + le détail par agent, sans rien lancer."""
    now = now or time.time()
    sig = sensor_signal()
    report = {}
    chosen = None
    for agent in ORDER:
        has_work, reason = sig.get(agent, (False, ""))
        cd = cooldown_ok(agent, now)
        eligible = has_work and cd
        report[agent] = {"has_work": has_work, "cooldown_ok": cd,
                         "eligible": eligible, "reason": reason}
        if eligible and chosen is None:
            chosen = agent          # premier éligible par ordre de priorité
    return {"chosen": chosen, "agents": report}


TASKS = {
    "architecte": (
        "Veille de COHÉSION (auto). Le capteur state/topology.json est à jour : "
        "lis-le et traite EN PRIORITÉ les îlots détachés, les fiches isolées, les "
        "placements incohérents, puis quelques liens manquants inter-domaines à plus "
        "forte valeur. Tisse les liens [[...]] manquants, raccroche l'isolé. "
        "ÉCONOMIE DE TOKENS : appuie-toi sur le JSON du capteur, n'ouvre que les "
        "fiches que tu modifies. NE committe PAS (le shell s'en charge). Rapport bref."),
    "challenger": (
        "Veille d'HONNÊTETÉ (auto). state/coherence.json liste des paires à fort "
        "recouvrement (doublon OU contradiction). Pour chacune, tranche : vrai "
        "doublon à fusionner, contradiction à signaler, ou faux positif. Produis tes "
        "doutes étayés (tu ne réécris pas le savoir, tu le mets à l'épreuve). "
        "ÉCONOMIE DE TOKENS : n'ouvre que les fiches concernées. NE committe PAS. Rapport bref."),
    "archiviste": (
        "Veille de FRAÎCHEUR (auto). state/utility.json liste le poids mort (fiches "
        "froides). PROPOSE l'archivage des plus clairement périmées (ne supprime "
        "JAMAIS seul : marque/déplace selon la convention d'archivage). "
        "ÉCONOMIE DE TOKENS : appuie-toi sur le JSON. NE committe PAS. Rapport bref."),
    "mecanicien": (
        "Veille d'INFRA (auto). state/doctor.json liste des défauts mécaniques : "
        "liens_morts, orphelins, frontmatter, nommage, hors_index. Corrige UNIQUEMENT "
        "ces défauts ciblés et SÛRS (lien mort → bon lien ou retrait, frontmatter "
        "manquant → complété, nommage → kebab-case). PRUDENCE ABSOLUE : ne touche aux "
        "hooks/settings/symlinks QUE si le docteur les pointe explicitement ; au moindre "
        "doute, ne fais rien et signale-le dans le rapport. ÉCONOMIE DE TOKENS : "
        "appuie-toi sur le JSON, n'ouvre que ce que tu corriges. NE committe PAS. Rapport bref."),
}


def _last_cost_line():
    last = ""
    try:
        with open(COST, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line
    except Exception:
        pass
    return last


def _cout_du_segment(offset):
    """Ce que le passage qui vient de finir a coûté — et RIEN d'autre.

    On lit cost.jsonl À PARTIR de l'octet retenu avant le lancement. Prendre « la
    dernière ligne » du fichier attribuerait à cet agent le coût d'une distillation
    écrite en parallèle : cost.jsonl est un journal PARTAGÉ, en ajout seul."""
    out = {}
    try:
        with open(COST, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            for ligne in f:
                try:
                    o = json.loads(ligne)
                except Exception:
                    continue
                if "total_cost_usd" not in o:
                    continue
                out = {"cout_usd": round(o.get("total_cost_usd") or 0, 4),
                       "session_id": o.get("session_id"),
                       "jetons_sortie": (o.get("usage") or {}).get("output_tokens"),
                       "erreur": True if o.get("is_error") else None}
    except Exception:
        pass
    return {k: v for k, v in out.items() if v is not None}


def run(sid=""):
    # Le gel se lit ICI aussi (2026-09-15). Avant, seul auto_maintain le lisait : lancé à la
    # main, ce module réveillait un robot pendant le gel.
    if os.path.exists(os.path.join(STATE, "FREEZE")):
        return
    now = time.time()
    # O1 — quels agents ont leur cooldown OUVERT ? Si aucun, on s'arrête AVANT toute
    # dépense : pas de régénération de capteur, pas d'appel LLM. Coût strictement nul.
    open_agents = [a for a in ORDER if cooldown_ok(a, now)]
    if not open_agents:
        return
    # F1 — garde quota AVANT de dépenser quoi que ce soit (même résilience que la
    # couche 1). Quota épuisé → on diffère sans graver de cooldown : la veille
    # repassera au prochain SessionEnd authentifié, rien n'est « brûlé ».
    if guard is not None and not guard.preflight_ok():
        return
    regen_sensors(open_agents)         # O1 — seulement les capteurs des agents éligibles
    d = decide(now)
    agent = d["chosen"]
    if not agent:
        return                          # capteurs sous le seuil → veille au repos
    claude = shutil.which("claude")
    if not claude:
        return
    reason = d["agents"][agent]["reason"]
    write_status("busy", ACT.get(agent, "gardening"), f"{agent}: {reason}", source="agent")
    # 19/09 — la ligne NOMINATIVE que status.json ne peut pas porter (il n'a qu'un état
    # global, écrasé au passage suivant). Voir brain_status.journal_agent.
    modele = MODEL.get(agent, "sonnet")
    t0 = journal_agent(agent, "debut", raison=reason,
                       activite=ACT.get(agent, "gardening"), modele=modele) or time.time()
    # Plus de passe-droit depuis le 2026-09-15 : chaque robot n'a que ses outils nommés,
    # voir robots_permissions.py. Si les droits ne se construisent pas, on ne lance rien.
    try:
        from robots_permissions import drapeaux
        droits = drapeaux(agent, BRAIN)
    except Exception:
        journal_agent(agent, "fin", debut=t0, duree_s=round(time.time() - t0, 1),
                      verdict="droits-indisponibles")
        return
    cmd = [claude, "-p", "--model", modele,
           "--output-format", "json", *droits, TASKS[agent]]
    try:
        offset = os.path.getsize(COST)
    except OSError:
        offset = 0
    code = None
    try:
        with open(COST, "a") as cf, open(LOG, "a") as lf:
            code = subprocess.run(cmd, cwd=BRAIN, stdin=subprocess.DEVNULL,
                                  stdout=cf, stderr=lf, timeout=900).returncode
    except Exception:
        journal_agent(agent, "fin", debut=t0, duree_s=round(time.time() - t0, 1),
                      verdict="interrompu", **_cout_du_segment(offset))
        return  # best-effort : un échec de veille ne perd aucune donnée
    # F1 — ne GRAVE le cooldown 12 h que si l'agent a VRAIMENT réussi. Un échec
    # quota/login sort en code 0 avec is_error=true (pas d'exception Python) : sans ce
    # garde, on brûlait 12 h de veille sans rien faire. interpret_result pose aussi les
    # marqueurs quota/login → la couche 1 sait différer au prochain coup.
    ok = True
    if guard is not None:
        try:
            ok = guard.interpret_result(_last_cost_line(), sid, is_distill=False)
        except Exception:
            ok = True   # en cas de doute on grave (évite une boucle si interpret casse)
    if ok:
        record_run(agent, now)
    # Vu au banc du 19/09 : `subprocess.run` ne lève RIEN sur un code de sortie non nul,
    # si bien que le journal écrivait « ok » pour un agent qui venait d'échouer. Un
    # panneau nourri par ce verdict-là aurait menti en vert.
    if code:
        verdict = f"echec-code-{code}"
    else:
        verdict = "ok" if ok else "quota-ou-login"
    journal_agent(agent, "fin", debut=t0, duree_s=round(time.time() - t0, 1),
                  verdict=verdict, **_cout_du_segment(offset))


if __name__ == "__main__":
    try:
        arg = sys.argv[1] if len(sys.argv) > 1 else "decide"
        if arg == "run":
            run(sys.argv[2] if len(sys.argv) > 2 else "")
        else:
            print(json.dumps(decide(), ensure_ascii=False, indent=2))
    except Exception:
        pass
    sys.exit(0)
