#!/usr/bin/env python3
"""
Hook SessionEnd du C Brain — maintenance AUTONOME complète (phase 2).
À la fin d'une session, en arrière-plan détaché, enchaîne :
  1. DISTILLER  : le distillateur extrait les fiches durables de la session finie
  2. RANGER     : le jardinier vide l'Inbox, déduplique, affine, optimise
  3. COMMIT     : versionné

Remplace maybe_garden.py (qui ne faisait que ranger). Ici on distille AUSSI,
automatiquement, sans rien déclencher à la main.

Garde-fous quotas/boucles :
  - anti-récursion : CLAUDE_BRAIN_GARDENING=1 (le headless ne se relance pas)
  - une distillation MAX par session (marqueur sessions/.distilled.json)
  - sessions triviales ignorées (< MIN_MSG messages)
  - ne spawn que s'il y a du travail (session substantielle non distillée OU Inbox pleine)
  - détaché : ne bloque jamais la fermeture de session

Sort toujours 0.
"""
import os, sys, re, json, time, glob, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status
except Exception:
    def write_status(*a, **k): pass
try:
    import brain_guard as guard
except Exception:
    guard = None

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
SESS = os.path.join(BRAIN, "sessions")
INDEX = os.path.join(SESS, ".index.json")          # écrit par archive_session.py
DISTILLED = os.path.join(SESS, ".distilled.json")  # sessions déjà distillées
LOG = os.path.join(SESS, "gardening.log")
A_CLASSER = os.path.join(BRAIN, "state", "a-classer.md")   # fiches pas encore dans la carte
# ⚠ LE NOM DU DOSSIER VIENT DU DOSSIER D'OÙ LA SESSION A ÉTÉ OUVERTE, PAS DE $HOME,
#   et la nuance n'est pas théorique : mesuré le 2026-09-20, `~/.claude/projects/` porte
#   HUIT dossiers, et celui que cette ligne construit n'en contient que 155 transcripts
#   sur 733. Le commentaire d'origine disait « $HOME avec / -> - » — c'est vrai tant que
#   l'auteur ouvre ses sessions depuis son dossier personnel, et faux le jour où il en ouvre
#   une depuis ~/.c-brain/trunk. Ne JAMAIS coder le nom d'utilisateur en dur non plus
#   (cf. [[restauration-machine-2026-07-22]]). Ce chemin reste le PREMIER endroit où
#   regarder, parce qu'il répond dans le cas courant sans lister quoi que ce soit ;
#   `transcript_for` prend le relais quand il ne répond pas.
PROJECTS_ROOT = os.path.expanduser("~/.claude/projects")
TRANSCRIPTS = os.path.join(PROJECTS_ROOT, os.path.expanduser("~").replace(os.sep, "-"))


def transcript_for(sid):
    """Le transcript de CETTE session-là, cherché dans TOUS les dossiers de projet.

    Rend le chemin, ou None — jamais un chemin qui n'existe pas : « je n'ai pas trouvé »
    et « voilà un fichier » sont deux réponses différentes, et l'appelant qui reçoit un
    chemin inexistant le passe tel quel au distillateur, qui lit alors le vide sans le
    dire. C7 (2026-09-20) : c'est exactement ce que faisait la reprise d'une session
    différée — elle transportait le chemin de la session EN COURS sous l'identifiant de
    la session REPRISE."""
    if not sid:
        return None
    direct = os.path.join(TRANSCRIPTS, f"{sid}.jsonl")
    if os.path.exists(direct):
        return direct
    ailleurs = sorted(glob.glob(os.path.join(PROJECTS_ROOT, "*", f"{sid}.jsonl")))
    return ailleurs[0] if ailleurs else None
MANUAL_SAVES = os.path.join(BRAIN, "state", "manual-saves.jsonl")  # ledger posé par on_fiche_write
MIN_MSG = 20  # en dessous : session triviale, pas de distillation

def inbox_has_work():
    """Des fiches attendent leur place dans la carte. Depuis le 2026-09-15 la file vit dans
    state/a-classer.md, plus dans MEMORY.md (voir on_fiche_write.py, section 2)."""
    try:
        file = open(A_CLASSER, encoding="utf-8").read()
    except Exception:
        return False
    return bool(re.search(r'^\s*-\s*\[', file, re.M))

def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def manual_saves_for(sid):
    """Fiches de savoir écrites À LA MAIN pendant la session `sid` (ledger posé par on_fiche_write).
    Sert à dire au distillateur de NE PAS recréer ce que Claude a déjà enregistré (anti-redondance).
    Best-effort : ledger absent/illisible → liste vide (le distillateur tourne normalement)."""
    out = []
    if not sid:
        return out
    try:
        for line in open(MANUAL_SAVES, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("sid") == sid and e.get("path") and e["path"] not in out:
                out.append(e["path"])
    except Exception:
        pass
    return out

# La capsule prouve qu'elle a une FENÊTRE en touchant state/capsule-alive toutes
# les 5 s (cf. capsule/main.js). Chercher un PROCESS ne prouve rien : le
# 2026-08-13, un Electron vieux de deux jours sans fenêtre s'est fait prendre
# pour une capsule ouverte, et bloquait donc son propre remplacement à chaque
# démarrage de session — silencieusement, puisque l'écriture du statut marchait.
# ⚠️ ANCRÉ SUR BRAIN — corrigé le 2026-09-20 (C bis, C3). Ce motif était un fragment de
#   chemin ÉCRIT EN DUR ("claude-brain/capsule/…"), donc juste dans un seul arbre. Le
#   paquet publié porte "c-brain/trunk/capsule/…", qui vise l'INSTALLÉ (~/.c-brain/trunk)
#   et ne matche ni ~/c-brain ni le plan de travail ~/c-brain-fr : là, pgrep rend 0 sur une
#   capsule bien vivante, on conclut « rien ne tourne » et on en relance une par-dessus.
#   Calibré le 2026-09-20 DANS LES DEUX SENS (cf. pkill-motif-approximatif-mesure-une-
#   instance-perimee) : 4 pids quand la capsule de CE tronc tourne, rc=1 pour un tronc
#   voisin qui n'en a pas. Le chemin absolu interdit en plus de prendre la capsule d'un
#   AUTRE arbre pour la sienne.
MOTIF_CAPSULE = os.path.join(BRAIN, "capsule", "node_modules", "electron")
BATTEMENT_MAX = 60          # 12 battements manqués : on ne réagit pas sur un hoquet
GRACE_DEMARRAGE = 90        # une capsule qui vient de partir n'a pas encore battu


def _age_process(pid):
    """Secondes depuis le lancement du process, ou None si illisible.

    ⚠ `etimes` (secondes brutes) est une extension GNU : macOS ne la connaît PAS
    et `ps` répond en imprimant sa LISTE DE MOTS-CLÉS, sur sa sortie standard et
    en code 0. Un `int(out)` échoue donc silencieusement, `_age_process` renvoyait
    None pour tout le monde, et le contrôle de zombie répondait « vivante »
    quoi qu'il arrive — un garde-fou mort-né. On lit `etime`, portable, et on le
    parse : [[jj-]hh:]mm:ss."""
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "etime="],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        if not out or " " in out:            # sortie inattendue (liste de mots-clés)
            return None
        jours, _, reste = out.rpartition("-")
        parts = [int(x) for x in reste.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        h, m, sec = parts[-3:]
        return (int(jours or 0) * 86400) + h * 3600 + m * 60 + sec
    except Exception:
        return None


def capsule_vivante(pids):
    """True si une FENÊTRE bat. Sinon le process est un zombie à remplacer.

    ⚠ Deux prudences, sans quoi ce contrôle tuerait des capsules saines :
      · un battement absent sur un process JEUNE n'est pas un zombie, c'est un
        démarrage en cours (GRACE_DEMARRAGE) ;
      · en cas de doute — âge illisible, erreur d'accès — on répond VIVANTE.
        Un faux zombie relance une capsule pour rien ; un faux vivant, lui, ne
        coûte qu'un tour de plus. Le doute ne doit pas tuer."""
    try:
        alive = os.path.join(BRAIN, "state", "capsule-alive")
        if not os.path.exists(alive):
            # ⚠ AUCUN battement n'a JAMAIS été écrit. Ce n'est pas un zombie, c'est
            #   une capsule qui ne sait pas battre. Deux cas réels :
            #     · une capsule jamais lancée depuis l'installation ;
            #     · une capsule d'une version ANTÉRIEURE à l'émetteur — le paquet
            #       public a longtemps porté ce contrôle sans lui (`capsule/main.js`
            #       n'est pas synchronisé ; l'émetteur y a été porté à la main le
            #       2026-08-13, mais une install plus vieille tourne encore sans).
            #   Sans ce garde, ces capsules-là seraient déclarées mortes passé le
            #   délai de grâce et tuées en boucle à chaque passage.
            #   On ne juge que ce qui a DÉJÀ battu puis s'est tu.
            return True
        if time.time() - os.path.getmtime(alive) < BATTEMENT_MAX:
            return True
        ages = [a for a in (_age_process(p) for p in pids) if a is not None]
        if not ages:
            return True                      # illisible → on ne touche à rien
        return min(ages) < GRACE_DEMARRAGE   # jeune → il démarre, pas un zombie
    except Exception:
        return True


def ensure_capsule():
    """Ouvre la capsule Tamagotchi si elle n'est pas déjà en cours (réveil des agents).

    Mode léger : si le fichier state/no-capsule existe, on ne relance rien.
    La capsule (Electron + son helper GPU) est le plus gros consommateur CPU
    de la machine au repos ; sur un MacBook Air sans ventilateur elle force
    WindowServer à recomposer l'écran en continu."""
    try:
        if os.path.exists(os.path.join(BRAIN, "state", "no-capsule")):
            return
        cap = os.path.join(BRAIN, "capsule")
        elec = os.path.join(cap, "node_modules", ".bin", "electron")
        if not os.path.exists(elec):
            return
        # le vrai process tourne sous .../node_modules/electron/dist/... (le .bin/electron
        # n'est qu'un symlink), donc on matche le chemin du projet, pas le symlink.
        r = subprocess.run(["pgrep", "-f", MOTIF_CAPSULE],
                           capture_output=True, text=True)
        # ⚠️ UNE SORTIE VIDE N'EST PAS UNE MESURE. pgrep rend 0 quand il trouve,
        #   1 quand il ne trouve rien, et 2 ou plus quand il a ÉCHOUÉ (option
        #   refusée, motif illisible) — dans ce dernier cas stdout est vide lui
        #   aussi, et rien ne distingue « aucune capsule » de « je n'ai pas pu
        #   regarder ». Conclure ici relancerait une capsule par-dessus une
        #   capsule vivante. On ne conclut pas.
        if r.returncode >= 2:
            return
        if r.stdout.strip():
            if capsule_vivante(r.stdout.split()):
                return                       # vraiment ouverte : une fenêtre bat
            # ZOMBIE : le process vit, sa fenêtre non. On le remplace au lieu de
            # le prendre pour une capsule saine — c'est ce qui l'a laissée
            # invisible deux jours le 2026-08-13.
            subprocess.run(["pkill", "-f", MOTIF_CAPSULE], capture_output=True)
            time.sleep(1)
        env = dict(os.environ)
        # 24/09 soir : l'orbe quitte l'encoche (L'utilisateur : « retire l'orbe de
        # l'encoche, on garde la pastille »). Ce qui démarre est la pastille de
        # la barre de menus (capsule/ilot.js), qui bat sur capsule-alive comme
        # l'orbe. L'orbe reste lançable à la main : CAPSULE_SOLO=1 electron .
        subprocess.Popen([elec, "ilot.js"], cwd=cap, env=env,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        pass

def session_msg_count(sid, transcript_path=None):
    """Nombre de messages, ou None si on ne PEUT PAS le mesurer.

    C7 (2026-08-19) : ce compteur reconstruisait le chemin depuis expanduser("~")
    et ignorait le `transcript_path` que Claude Code fournit dans la charge utile
    du hook. Une session ouverte depuis un AUTRE dossier — typiquement ~/.c-brain/trunk
    lui-même — retombait alors sur 0, donc sous MIN_MSG, donc jamais distillée, en
    silence. Balayage rétrospectif : 87 sessions de 20 à 221 messages perdues ainsi.

    L'ordre d'autorité est désormais : index → transcript_path fourni → chemin
    reconstruit (compatibilité). Et un échec rend **None**, jamais 0 : « 0 message
    mesuré » et « impossible de mesurer » sont deux états différents, et seul le
    premier a le droit d'entrer dans la comparaison avec MIN_MSG."""
    idx = load_json(INDEX, {})
    if sid in idx and isinstance(idx[sid], dict):
        n = idx[sid].get("n", 0)
        if n:
            return n
    for path in [p for p in (transcript_path, transcript_for(sid)) if p]:
        try:
            with open(path, "rb") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            continue
    return None

def launch_agent(sid, n, to_distill, transcript_path=None):
    """Lance le headless de maintenance (distill+jardin OU jardin seul) et le câble
    à brain_guard. Suppose que le verrou est DÉJÀ pris par l'appelant.
    Réutilisé par le SessionEnd (main) et par l'auto-reprise (resume_pending)."""
    claude = shutil.which("claude")
    if not claude:
        # `claude` introuvable — cas typique sous launchd (PATH minimal /usr/bin:/bin, sans
        # ~/.local/bin). L'appelant (resume_pending) a DÉJÀ dé-filé la session : si on rend juste
        # le lock, elle est perdue (jamais distillée) → garantie « zéro perte » violée. On la
        # RÉ-ENFILE avant de rendre le lock ; un SessionEnd interactif (PATH complet) la rejouera.
        if guard is not None:
            if to_distill and sid:
                guard.enqueue(sid)
            guard.release_lock()
        return

    ensure_capsule()  # la capsule s'ouvre au réveil des agents

    # ARCHITECTURE SANS PARENT (optimisation « zéro perte ») : on n'instancie PLUS
    # un LLM parent qui se contente d'orchestrer en spawnant deux sous-agents — ce
    # parent ne faisait aucun travail intellectuel mais relisait à chaque tour les
    # résultats remontés des sous-agents (gros cache_read pur gâchis). Désormais le
    # shell séquence directement DEUX appels `claude -p --agent …` (le distillateur
    # PUIS le jardinier), et fait lui-même les pulses capsule + le commit (mécaniques,
    # zéro LLM). Même travail, même qualité, un contexte LLM en moins.
    py = sys.executable
    status_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_status.py")
    mark_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mark_distilled.py")
    guard_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_guard.py")
    upkeep_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_upkeep.py")
    embed_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_embed.py")
    embed2_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_embed2.py")
    graph_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph_export.py")
    coact_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coactivation.py")
    doctor_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_doctor.py")
    cost = os.path.join(BRAIN, "sessions", "cost.jsonl")
    transcript = transcript_path or transcript_for(sid) or os.path.join(TRANSCRIPTS, f"{sid}.jsonl")

    # Les tâches : l'appel EST l'agent (via --agent), donc plus de « lance le
    # sous-agent X » — on lui donne directement sa mission. Consigne anti-gâchis :
    # ne pas relire un fichier déjà lu, ne pas committer (le shell s'en charge).
    distill_task = (
        f"Une session vient de se terminer (id={sid}, {n} messages, "
        f"transcript: {transcript}, note d'archive éventuelle dans sessions/archive/). "
        "Extrais les fiches/leçons DURABLES uniquement. ÉCONOMIE DE TOKENS IMPÉRATIVE : "
        "NE lis PAS le transcript en entier ; base-toi sur la note d'archive, au besoin "
        "grep + lis au plus ~60 lignes ciblées. Ne relis JAMAIS un fichier déjà lu. "
        "Si rien ne mérite de rester, ne crée rien. NE committe PAS (le shell s'en charge). "
        "Sois concis dans ton rapport."
    )
    # ANTI-REDONDANCE (option B) : les fiches que Claude a déjà écrites À LA MAIN pendant la session
    # ne doivent pas être recréées par le distillateur (sinon doublon transitoire + tokens gâchés). On
    # le lui dit explicitement ; il garde le filet pour le savoir NON sauvé.
    already = manual_saves_for(sid)
    if already:
        distill_task += (
            " IMPORTANT — Claude a DÉJÀ écrit/affiné ces fiches à la main pendant cette session : "
            + ", ".join(already) +
            ". NE LES RECRÉE PAS ; complète-les seulement s'il manque vraiment quelque chose, et "
            "n'extrais que le savoir DURABLE qu'elles ne couvrent pas encore."
        )
    garden_task = (
        "Traite la file state/a-classer.md : pour une LEÇON, pose son champ tags: puis lance "
        "python3 hooks/index_lecons.py ; pour toute autre fiche, écris dans state/a-valider.md "
        "la section de MEMORY.md où elle devrait aller, sans toucher MEMORY.md (ADR-0015 : "
        "la carte est validée par un humain). Retire ensuite sa ligne de state/a-classer.md. "
        "Déduplique, répare/tisse les liens [[...]] dans les fiches, masque tout secret, affine. "
        "Ne relis pas inutilement un fichier déjà lu. NE committe PAS (le shell s'en "
        "charge). Sois concis dans ton rapport."
    )

    env = dict(os.environ)
    env["CLAUDE_BRAIN_GARDENING"] = "1"
    try:
        logf = open(LOG, "a")
    except Exception:
        logf = subprocess.DEVNULL

    write_status("busy", "distilling" if to_distill else "gardening",
                 "Waking the agents…", source="agent")

    state_dir = os.path.join(BRAIN, "state")
    dpf = os.path.join(state_dir, ".distill.txt")
    gpf = os.path.join(state_dir, ".garden.txt")
    try:
        os.makedirs(state_dir, exist_ok=True)
        open(dpf, "w", encoding="utf-8").write(distill_task)
        open(gpf, "w", encoding="utf-8").write(garden_task)
    except Exception:
        if guard is not None:
            guard.release_lock()
        return

    # Modèle PAR AGENT. Le distillateur est le seul étage créatif de la couche 1 : son
    # échec perd du savoir définitivement (le jardinage, lui, est mécanique et rejouable).
    # D'où sonnet pour distiller, haiku pour ranger. cf. brain_upkeep.MODEL, même logique.
    MODEL_L1 = {"distillateur": "sonnet", "jardinier": "haiku"}
    # Plus de passe-droit depuis le 2026-09-15 : chaque robot n'a que ses outils nommés,
    # voir robots_permissions.py. Si les droits ne se construisent pas, on ne lance rien.
    try:
        import shlex
        from robots_permissions import drapeaux
        droits = {a: shlex.join(drapeaux(a, BRAIN)) for a in MODEL_L1}
    except Exception:
        write_status("idle")
        if guard is not None:
            guard.release_lock()
        return
    base = lambda m: f'"{claude}" -p --model {m} --output-format json'
    pulse = lambda act, det: f'"{py}" "{status_cli}" busy {act} "{det}"'
    # SAUVEGARDE MÉCANIQUE (pas de LLM), câblée ici le 2026-08-13.
    # Avant : `git add -A` + un commit fourre-tout. C'est ce `add -A` qui a noyé
    # 19 fichiers d'un chantier en cours dans e61fd01 (03/08), et 612 commits de
    # ce type dorment dans l'historique. On commite désormais ZONE PAR ZONE : le
    # hook pre-commit du tronc refuse déjà les commits mixtes, on s'appuie dessus
    # au lieu de le contourner.
    # DEUX LIGNES, ET LA SÉPARATION EST DÉLIBÉRÉE :
    #   · `commit_par_zone` est LIVRÉ — il commite en LOCAL, chez tout le monde.
    #   · `tools/sync_depots.py` n'existe QUE chez l'auteur (`tools/` n'est pas
    #     dans la liste blanche de sync.sh). Lui pousse, et mesure le paquet
    #     public. Un utilisateur qui a mis un dépôt distant sur son tronc n'a
    #     jamais demandé que ses notes y partent à chaque fin de session — donc
    #     le paquet ne contient AUCUN push, et l'absence du fichier suffit à ce
    #     que la ligne ne fasse rien là-bas.
    # ⚠️ CE QUE `--auto` FAIT A CHANGÉ LE 2026-08-15. Il poussait le tronc privé
    # et se contentait de MESURER le paquet public ; il pousse désormais aussi la
    # branche `fr` du paquet, via le plan de travail ~/c-brain-fr.
    # Pourquoi c'était bloqué, et pourquoi ça ne l'est plus : l'obstacle n'était
    # pas le risque mais un fait matériel — le dépôt de l'auteur vit sur `main`,
    # `sync.sh` refuse d'y tourner, et l'automatisme aurait été un no-op qui a
    # l'air branché. Le worktree lui donne un endroit où le garde-fou de branche
    # est DÉJÀ satisfait ; il n'est ni forcé ni contourné.
    # Ce qui n'a PAS bougé : le leakcheck reste la seule barrière et il décide
    # (rouge = rien ne part) ; le tag et `main` restent des gestes humains.
    # Voir le docstring de sync_depots.py, section « DEUX MODES ».
    # ── SÉLECTION PAR REVENDICATION — câblée le 2026-09-19 ────────────────────
    # `commit_par_zone` sélectionne « tout ce qui est modifié dans la zone », donc il
    # emporte le travail non commité des sessions voisines : mesuré en production le
    # 2026-09-15, 40 fichiers commités dont 13 seulement écrits par un robot.
    # La chaîne ne commite désormais que ce que SES robots ont écrit, lu dans leur
    # propre transcript, plus les dérivés régénérés à part et les archives machine.
    # Qualifié par sabotage : tools/revendication/banc.py, 9/9 au vert contre 2/9
    # pour l'ancienne sélection (contre-épreuve `--ancien`, rejouée le 19/09).
    # ⚠️ REPLI ASSUMÉ : `tools/` n'est pas dans le paquet livré. Là où le module est
    # absent, on retombe sur l'ancien producteur — un tronc qui ne commite plus rien
    # serait pire que la sélection large, et chez un utilisateur seul il n'y a pas de
    # session voisine à absorber.
    revendiquer = f"{BRAIN}/tools/revendication/revendiquer.py"
    instantane_rev = f"{BRAIN}/state/revendication.json"
    depots = (f'if [ -f "{revendiquer}" ]; then\n'
              f'  "{py}" "{revendiquer}" commite --instantane "{instantane_rev}" '
              f'|| true\n'
              f'else\n'
              f'  "{py}" "{BRAIN}/hooks/commit_par_zone.py" || true\n'
              f'fi\n'
              f'[ -f "{BRAIN}/tools/sync_depots.py" ] && '
              f'"{py}" "{BRAIN}/tools/sync_depots.py" --auto || true')

    # Garde anti-faux-positif (crash OS / SIGKILL du binaire `claude` AVANT d'écrire) :
    # `interpret` lit la DERNIÈRE ligne de cost.jsonl. Si claude meurt sans rien écrire,
    # cette dernière ligne est celle du run PRÉCÉDENT (peut-être un succès) → fausse
    # réussite → session marquée distillée sans l'être → savoir perdu. Parade : on compte
    # les lignes avant l'appel ; si aucune n'a été ajoutée, on injecte une ligne d'erreur
    # synthétique → `interpret` voit bien CE run, échoue, et ré-enfile la session.
    sentinel = ('{"is_error":true,'
                '"result":"claude exited without writing output (SIGKILL/crash?)"}')
    nlines = f"$(awk 'END{{print NR}}' \"{cost}\" 2>/dev/null || echo 0)"

    def agent_call(agent, pf):
        # JOURNAL PAR MISSION (20/09/2026). brain_status.journal_agent n'était appelé que
        # par brain_upkeep : la couche 2. Or la couche 1 est la plus sollicitée des deux —
        # le distillateur et le jardinier tournent à chaque fin de session — et elle part
        # par un shell, pas par Python. Résultat mesuré : state/agents.jsonl ne contenait
        # que des lignes du challenger, et tout affichage par agent aurait déclaré
        # « jamais vu » les deux qui travaillent le plus. `|| true` partout : un journal
        # best-effort ne doit jamais faire tomber une passe de maintenance.
        jr = f'"{py}" "{status_cli}" journal {agent}'
        modele = MODEL_L1.get(agent, "haiku")
        return [
            f'__N0={nlines}',
            f'__T0=$(date +%s)',
            f'{jr} debut couche=1 modele={modele} >/dev/null 2>&1 || true',
            f'{base(modele)} {droits[agent]} "$(cat {pf})" '
            f'>> "{cost}" 2>> "{LOG}"',
            f'if [ "{nlines}" -le "$__N0" ]; then '
            f"printf '%s\\n' '{sentinel}' >> \"{cost}\"; fi",
            f'{jr} fin couche=1 modele={modele} '
            f'duree_s=$(( $(date +%s) - $__T0 )) >/dev/null 2>&1 || true',
        ]

    lines = []
    # HEARTBEAT capsule : pendant toute la passe, un fond rafraîchit `ts` toutes les 5 s
    # (un appel `claude -p` dure des minutes sans réécrire le statut → sans ça la capsule
    # clignote en idle au milieu du travail). Borné à 600 itér. (~50 min) en sécurité au
    # cas où le kill final n'aurait pas lieu, et tué explicitement juste avant `idle`.
    lines.append(f'( __i=0; while [ $__i -lt 600 ]; do "{py}" "{status_cli}" touch '
                 f'>/dev/null 2>&1; sleep 5; __i=$((__i+1)); done ) & __HB=$!')
    # L'INSTANTANÉ SE PREND AVANT QUE LES ROBOTS PARTENT. Il photographie ce qui était
    # déjà modifié dans l'arbre partagé — donc ce qui appartient peut-être à une autre
    # session — et il donne au veto son point de comparaison. Pris après, il ne
    # distinguerait plus le brouillon d'un voisin de l'écriture d'un robot.
    # La photo porte elle-même sa borne de lecture de cost.jsonl : seules les sessions
    # enregistrées APRÈS elle sont des robots de CETTE passe. Compter ces lignes ici,
    # dans un second `awk`, aurait fait deux sources pour un seul nombre.
    lines.append(f'[ -f "{revendiquer}" ] && "{py}" "{revendiquer}" instantane '
                 f'"{instantane_rev}" >/dev/null 2>&1 || true')
    if to_distill:
        # 1) DISTILLER directement via --agent distillateur, puis interpréter le
        #    résultat (df=1 : ré-enfile la session si « Not logged in »/quota/crash).
        #    Le jardinage n'a lieu que si la distillation a RÉELLEMENT réussi.
        lines.append(pulse("distilling", "Distilling this session"))
        lines += agent_call("distillateur", dpf)
        lines.append(f'if "{py}" "{guard_cli}" interpret "{cost}" "{sid}" 1 ; then')
        lines.append(f'  "{py}" "{mark_cli}" "{sid}"')
        lines.append(f'  {pulse("gardening", "Organizing the tree")}')
        lines += ['  ' + l for l in agent_call("jardinier", gpf)]
        lines.append('fi')
    else:
        # Jardinage seul (Inbox pleine, pas de session à distiller).
        lines.append(pulse("gardening", "Organizing the tree"))
        lines += agent_call("jardinier", gpf)
        lines.append(f'"{py}" "{guard_cli}" interpret "{cost}" "{sid}" 0')
    # GARDE MÉCANIQUE post-jardinier (zéro LLM) : le jardinier est seul juge de sa propre
    # passe. brain_doctor recompte les défauts (liens morts, orphelins, frontmatter,
    # hors-carte, taille de MEMORY) JUSTE APRÈS lui, et trace le verdict dans gardening.log. Il ne corrige
    # rien — le mécanicien s'en charge plus tard, via son capteur. Ici on veut seulement
    # qu'une passe de jardinage qui dégrade l'arbre soit VISIBLE tout de suite, au lieu
    # d'attendre jusqu'à 12 h le prochain réveil du mécanicien.
    lines.append(f'"{py}" "{doctor_cli}" --json >/dev/null 2>&1')
    lines.append(
        f'''__D=$("{py}" -c 'import json;print(json.load(open("{BRAIN}/state/doctor.json"))["total"])' 2>/dev/null || echo -1); '''
        f'''if [ "$__D" != "0" ]; then echo "[doctor] $(date '+%F %T') post-jardinage: $__D defaut(s)" >> "{LOG}"; fi''')
    # SECONDE COUCHE (veille de cohésion) : après distill+jardin, régénère les capteurs
    # mécaniques (gratuit) et réveille AU PLUS un agent de veille (challenger / architecte
    # / archiviste) si son seuil est franchi et son cooldown respecté. brain_upkeep gère
    # seul priorité, cadence et coût (best-effort, ne perd aucune donnée s'il échoue).
    # brain_upkeep pulse lui-même l'activité capsule de l'agent qu'il réveille (ou rien).
    lines.append(f'"{py}" "{upkeep_cli}" run "{sid}"')
    # F4/O2 — rafraîchit l'index sémantique du recall (brain_embed `build` est
    # INCRÉMENTAL : il ne réencode que les fiches dont le contenu a changé, via hash).
    # Coût quasi nul, zéro LLM (modèle d'embeddings local), et le recall reste à jour
    # au lieu de tourner sur un index périmé. Placé après distill+jardin pour indexer
    # les fiches fraîches, juste avant le commit. IMPORTANT : brain_embed a besoin de
    # numpy/model2vec → on l'invoque avec le python du .venv (le python système des
    # hooks ne les a pas) ; absent → on saute silencieusement (|| true).
    venv_py = os.path.join(BRAIN, ".venv", "bin", "python")
    if os.path.exists(venv_py):
        # HF_HUB_OFFLINE=1 : le modèle d'embeddings est déjà en cache local → on évite
        # un aller-retour réseau HF Hub à chaque passe (plus rapide, marche hors-ligne).
        # ⚠️ `|| true` TOUT SEUL A CACHÉ CE DÉFAUT PENDANT UN MOIS. Il faut que la chaîne
        # continue — l'indexation sémantique est optionnelle, elle ne doit pas empêcher le
        # commit — mais « continuer » et « ne rien dire » sont deux choses différentes. Un
        # échec ici ne laissait pas UNE ligne dans le journal, et la Planète continuait
        # d'annoncer « proximité = sens, toutes les fiches » (C bis A7, mesuré le 2026-09-19).
        # Un refus qui s'annonce est un résultat ; un refus muet est un mensonge différé.
        lines.append(f'HF_HUB_OFFLINE=1 "{venv_py}" "{embed_cli}" build >> "{LOG}" 2>&1'
                     f' || echo "⚠️  index de RAPPEL sémantique non reconstruit'
                     f' (brain_embed build a échoué)" >> "{LOG}"')
        # Étage 1 — recalcule la carte SÉMANTIQUE (state/embed2.json) à partir de l'index frais,
        # puis régénère planet/graph.json pour que la vue « sens » (touche S) reflète le contenu courant.
        lines.append(f'HF_HUB_OFFLINE=1 "{venv_py}" "{embed2_cli}" >> "{LOG}" 2>&1'
                     f' || echo "⚠️  CARTE sémantique non recalculée (brain_embed2 a échoué) —'
                     f' la planète garde les positions précédentes et le dit" >> "{LOG}"')
    else:
        # Le cas LÉGITIME, dit à voix haute. Les embeddings sont optionnels par dessein
        # (docs/design-doc.md) ; ce qui ne l'est pas, c'est qu'un tronc sans eux ressemble en
        # tout point à un tronc dont le calcul a échoué.
        lines.append(f'echo "· module sémantique non installé (.venv absent) — BM25 seul,'
                     f' la planète montre la structure" >> "{LOG}"')
    # Étage 2 — recalcule la mémoire de travail (chaleur d'usage + liens de co-activation) depuis les
    # logs de recall/lecture, AVANT graph_export (qui lit coactivation.json). Pur stdlib.
    lines.append(f'"{py}" "{coact_cli}" >> "{LOG}" 2>&1 || true')
    lines.append(f'"{py}" "{graph_cli}" >> "{LOG}" 2>&1 || true')
    # dépôts + idle + release : TOUJOURS, quoi qu'il arrive au-dessus.
    lines.append(pulse("committing", "Saving to git"))
    lines.append(depots)
    lines.append('kill "$__HB" >/dev/null 2>&1 || true')   # stoppe le heartbeat AVANT idle
    lines.append(f'"{py}" "{status_cli}" idle')
    lines.append(f'"{py}" "{guard_cli}" release')
    wrapper = "\n".join(lines)

    try:
        proc = subprocess.Popen(
            ["sh", "-c", wrapper],
            cwd=BRAIN, env=env,
            stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
            start_new_session=True,
        )
        # le hook qui détient le lock va mourir ; on y inscrit le PID du worker détaché
        # (vivant toute la passe) → une autre session voit un lock VIVANT et n'en lance pas 2.
        if guard is not None:
            try:
                guard.update_lock_pid(proc.pid)
            except Exception:
                pass
    except Exception:
        write_status("idle")
        if guard is not None:
            guard.release_lock()


def main():
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return  # on EST déjà le headless de maintenance

    # GEL DES ÉCRIVAINS AUTONOMES (Phase 0 du RFC Brain V3, 2026-08-03).
    # Pendant la construction du Brain V3 hors production, le distillateur, le
    # jardinier et brain_upkeep continueraient à modifier le tronc — et depuis
    # que le commit automatique est coupé, ils le feraient SANS trace dans git.
    # Le lab travaillerait alors sur une base qui bouge sous lui, et le
    # rattrapage lab↔prod deviendrait impossible à raisonner.
    #
    # La file d'attente, elle, continue de se remplir (capture-only) : rien
    # n'est perdu, tout sera distillé après la bascule.
    #
    # Lever le gel : supprimer ~/.c-brain/trunk/state/FREEZE
    freeze = os.path.join(BRAIN, "state", "FREEZE")
    if os.path.exists(freeze):
        try:
            data = json.loads(sys.stdin.read() or "{}")
            sid = data.get("session_id")
            if sid:
                guard.enqueue(sid)  # capture-only : on note, on ne traite pas
        except Exception:
            pass
        return

    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    sid = data.get("session_id")

    distilled = set(load_json(DISTILLED, []))
    tp = data.get("transcript_path")
    n = session_msg_count(sid, tp) if sid else None
    if sid and n is None:
        # INDISPENSABLE : l'incapacité de mesurer ne doit pas se déguiser en session triviale.
        print(f"[auto_maintain] transcript illisible ou introuvable pour {sid} "
              f"(transcript_path={tp!r}) — distillation NON décidée, session mise en file",
              file=sys.stderr)
        if guard is not None:
            guard.enqueue(sid)
    to_distill = bool(sid) and sid not in distilled and n is not None and n >= MIN_MSG
    to_garden = inbox_has_work()

    if not (to_distill or to_garden):
        return  # rien à faire → aucun agent lancé

    claude = shutil.which("claude")
    if not claude:
        return

    # --- garde-fous tokens/compte (brain_guard) ---------------------------
    if guard is not None:
        if not guard.acquire_lock(sid):
            # Une maintenance tourne déjà (ex. plusieurs sessions fermées en même
            # temps : la 1re a pris le verrou). On ne double PAS (anti-corruption),
            # mais on ENFILE cette session pour qu'elle soit distillée ensuite —
            # sinon elle serait silencieusement perdue. Drainée par le prochain
            # SessionEnd ou par resume_pending (launchd, ~10 min).
            if to_distill:
                guard.enqueue(sid)
            return
        if not guard.preflight_ok():
            # quota épuisé (reset pas encore atteint) → on DIFFÈRE, jamais de crash
            if to_distill:
                guard.enqueue(sid)
            guard.release_lock()
            return
        # quota OK : on rejoue d'abord la session en attente la plus ancienne
        # (backlog accumulé pendant que le quota/login était KO), une par passage.
        # On la retire ATOMIQUEMENT (dequeue_one) : le reste de la file reste sur
        # DISQUE, jamais en mémoire. L'ancien drain_queue() vidait tout d'un coup
        # puis ré-enfilait le reste — un kill du process entre les deux engloutissait
        # tout le backlog (bug observé la nuit du 24/06, surface par `brain audit`).
        resume_sid = guard.dequeue_one()
        if resume_sid:
            if to_distill and resume_sid != sid:
                guard.enqueue(sid)               # session courante reportée d'un cran
            sid, to_distill = resume_sid, True
            # ⚠ LE CHEMIN DOIT SUIVRE L'IDENTIFIANT. `tp` vient de la charge utile du
            #   hook, donc de la session qui se TERMINE ; ici on vient d'en reprendre une
            #   AUTRE, sortie de la file. Jusqu'au 2026-09-20 `tp` n'était pas réévalué et
            #   partait tel quel dans `launch_agent` : le distillateur recevait
            #   « id=<repise>, transcript: <fichier de la session en cours> » — une paire
            #   incohérente, donc des fiches attribuées à une session qu'elles ne
            #   décrivent pas, et la session reprise jamais réellement lue. Le défaut est
            #   latent (il ne sort que quand la file n'est pas vide), ce qui est
            #   précisément pourquoi personne ne l'avait vu.
            tp = transcript_for(sid)
            _n = session_msg_count(sid, tp)
            n = _n if _n is not None else MIN_MSG

    launch_agent(sid, n, to_distill, tp)

if __name__ == "__main__":
    try:
        # `--capsule` : ouvrir l'orbe SANS déclencher de maintenance. Appelé par le
        # hook SessionStart. Avant ça, ensure_capsule() n'avait qu'un seul appelant
        # (launch_agent, en FIN de session) : l'orbe ne s'ouvrait donc jamais pendant
        # qu'on travaille — 12 h de session sans jamais la voir (constat de l'auteur,
        # 2026-08-04). Elle s'efface toujours seule au repos, ce mode ne force rien.
        if "--capsule" in sys.argv:
            ensure_capsule()
        else:
            main()
    except Exception:
        pass
    sys.exit(0)
