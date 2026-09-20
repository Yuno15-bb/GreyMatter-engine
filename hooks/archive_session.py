#!/usr/bin/env python3
"""
Hook SessionEnd du C Brain.
À chaque fin de session :
  1. rafraîchit l'index lossless sessions/TIMELINE.md (cache incrémental, rapide)
  2. capture le diff git du projet travaillé (cwd) dans sessions/archive/

⚠ Ce hook n'écrit PLUS dans git. Les étapes 3 (commit du tronc) et 4 (push vers
le remote) ont été coupées le 2026-08-03 — voir `commit_brain()`, qui garde le
détail et la condition de leur retour. Elles sont restées annoncées ici pendant
dix jours après leur suppression : ce docstring est le premier écran que lit
quiconque ouvre le fichier, et il promettait une sauvegarde qui n'existait plus.
La sauvegarde distante est assurée par le coffre chiffré, pas par ce hook.

Règle d'or : ne JAMAIS bloquer ni faire échouer la session. Sort toujours 0.
"""
import sys, os, json, re, glob, subprocess
from datetime import datetime

BRAIN = (os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
# Nom du dossier transcripts = $HOME avec "/" -> "-" (convention Claude Code).
# NE JAMAIS coder le nom d'utilisateur en dur ici (a cassé silencieusement la
# distillation lors de la migration d'un compte utilisateur vers un autre, cf. [[restauration-machine-2026-07-22]]).
PROJECTS_ROOT = os.path.expanduser("~/.claude/projects")
PROJECTS_DIR = os.path.join(PROJECTS_ROOT, os.path.expanduser("~").replace(os.sep, "-"))


def transcripts_hors_index():
    """Ce que cet index NE LIT PAS, compté dossier par dossier.

    ⚠ LE NOM DU DOSSIER VIENT DU DOSSIER D'OÙ LA SESSION A ÉTÉ OUVERTE, pas de $HOME :
      `rebuild_timeline` n'en balaie qu'UN, et l'en-tête annonçait pourtant « index sans
      perte de l'intégralité de nos sessions ». Mesuré le 2026-09-20 : 155 transcrits lus
      sur 733, sept dossiers jamais ouverts. **Les élargir serait une régression**, pas une
      réparation : 371 des 376 transcrits du plus gros dossier sont des sessions de
      maintenance automatique, et les mêler aux vraies est exactement le défaut réparé le
      2026-08-03 (voir la garde ANTI-RÉCURSION dans `main`). Ce qui n'est pas acceptable,
      c'est que l'index se taise. Il dit donc ce qu'il laisse dehors, avec le compte."""
    hors = []
    try:
        for d in sorted(os.listdir(PROJECTS_ROOT)):
            chemin = os.path.join(PROJECTS_ROOT, d)
            if chemin == PROJECTS_DIR or not os.path.isdir(chemin):
                continue
            n = len(glob.glob(os.path.join(chemin, "*.jsonl")))
            if n:
                hors.append((d, n))
    except OSError:
        pass
    return hors
SESSIONS = os.path.join(BRAIN, "sessions")
ARCHIVE = os.path.join(SESSIONS, "archive")
CACHE = os.path.join(SESSIONS, ".index.json")

SECRET = re.compile(
    r'(ntn_[A-Za-z0-9]+|sk-ant-[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+|secret_[A-Za-z0-9]+'
    r'|eyJ[A-Za-z0-9_.-]{20,}|[A-Za-z0-9_-]{32,}\.apps\.googleusercontent|gh[pousr]_[A-Za-z0-9]{20,})'
)
def redact(s): return SECRET.sub("«SECRET-MASQUÉ»", s or "")

# Table de classement des sessions : mot-clé (minuscules) → nom de projet.
# À REMPLIR avec TES projets — c'est elle qui range tes sessions archivées.
# Vide, tout tombe dans « À TRIER », ce qui reste correct mais peu utile.
# Exemple :
#   # Table de classement des sessions : mot-clé (minuscules) → nom de projet.
# À REMPLIR avec TES projets — c'est elle qui range tes sessions archivées.
# Vide, tout tombe dans « À TRIER », ce qui reste correct mais peu utile.
# Exemple :
#   PROJ = {
#       'facture': 'Compta', 'devis': 'Compta',
#       'shader': 'Graphismes', 'wallpaper': 'Graphismes',
#   }
PROJ = {
}
def classify(topic):
    low = (topic or "").lower()
    return next((v for k, v in PROJ.items() if k in low), "À TRIER")

def parse_transcript(path):
    """date de début, sujet (1er message texte), nb de messages."""
    ts = topic = None; nmsg = 0
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            for line in f:
                try: o = json.loads(line)
                except Exception: continue
                if o.get('type') in ('user', 'assistant'): nmsg += 1
                if o.get('timestamp') and ts is None: ts = o['timestamp']
                if topic is None and o.get('type') == 'user':
                    c = o.get('message', {}).get('content'); t = None
                    if isinstance(c, str): t = c
                    elif isinstance(c, list):
                        for p in c:
                            if isinstance(p, dict) and p.get('type') == 'text': t = p.get('text'); break
                    if t:
                        t = t.strip()
                        if t.startswith('<') or t.startswith('Caveat') or 'system-reminder' in t[:40] or t.startswith('[Request'):
                            continue
                        topic = redact(re.sub(r'\s+', ' ', t))[:200]
    except Exception:
        pass
    return ts, topic, nmsg

def load_cache():
    try:
        return json.load(open(CACHE, encoding='utf-8'))
    except Exception:
        return {}

def rebuild_timeline():
    """Incrémental : ne re-parse que les .jsonl dont le mtime a changé."""
    cache = load_cache()
    changed = False
    for path in glob.glob(os.path.join(PROJECTS_DIR, "*.jsonl")):
        pid = os.path.basename(path)[:-6]
        mt = os.path.getmtime(path)
        ent = cache.get(pid)
        if ent and abs(ent.get("mtime", 0) - mt) < 1:
            continue
        ts, topic, n = parse_transcript(path)
        if not topic:
            topic = "(reprise via fichier brief — pas de message texte initial)"
        cache[pid] = {"mtime": mt, "ts": ts or "z", "date": (ts[:10] if ts else "?"),
                      "proj": classify(topic), "n": n, "topic": topic}
        changed = True
    if changed or not os.path.exists(os.path.join(SESSIONS, "TIMELINE.md")):
        json.dump(cache, open(CACHE, "w", encoding='utf-8'), ensure_ascii=False, indent=0)
        write_timeline(cache)
    return cache, changed

def write_timeline(cache):
    rows = sorted(cache.values(), key=lambda e: e["ts"])
    hors = transcripts_hors_index()
    out = ["# 🕰️ Timeline — les sessions ouvertes depuis le dossier personnel\n",
           f"Index **sans perte de ce qu'il lit** : les {len(rows)} sessions dont le "
           f"transcript vit dans `{PROJECTS_DIR}/`. Tenu à jour automatiquement par le "
           "hook SessionEnd. Secrets masqués automatiquement.\n"]
    if hors:
        total = sum(n for _, n in hors)
        detail = ", ".join(f"`{d}` ({n})" for d, n in sorted(hors, key=lambda x: -x[1]))
        out.append(
            f"⚠️ **Et {total} transcripts qu'il ne lit PAS**, dans {len(hors)} autres "
            f"dossiers : {detail}. Le nom du dossier vient de l'endroit d'où la session a "
            "été ouverte, pas de `$HOME` — l'essentiel de ce qui est ici sont les sessions "
            "de maintenance automatique, tenues dehors depuis le 2026-08-03 pour ne pas "
            "les mêler aux vraies. Ce compte est là pour que le jour où une VRAIE session "
            "est ouverte depuis un autre dossier, elle se voie au lieu de disparaître.\n")
    cur = None
    for e in rows:
        mois = e["date"][:7]
        if mois != cur:
            cur = mois; out.append(f"\n## {mois}\n")
        out.append(f"- **{e['date']}** · `{e['proj']}` · {e['n']} msg — {e['topic']}")
    from collections import Counter
    c = Counter(e["proj"] for e in rows)
    out.append("\n\n---\n\n## Récap par domaine\n")
    for k, v in c.most_common(): out.append(f"- **{k}** — {v} sessions")
    out.append(f"\n\n*Total : {len(rows)} sessions. Dernière mise à jour : {datetime.now():%Y-%m-%d %H:%M}.*\n")
    open(os.path.join(SESSIONS, "TIMELINE.md"), "w", encoding='utf-8').write("\n".join(out))

def capture_git_diff(cwd):
    """Si cwd est un repo git (et pas le tronc lui-même), capture un résumé du diff."""
    if not cwd or os.path.realpath(cwd) == os.path.realpath(BRAIN):
        return None
    try:
        inside = subprocess.run(["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=10)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        stat = subprocess.run(["git", "-C", cwd, "diff", "--stat"],
                              capture_output=True, text=True, timeout=15).stdout.strip()
        status = subprocess.run(["git", "-C", cwd, "status", "--short"],
                                capture_output=True, text=True, timeout=15).stdout.strip()
        branch = subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
        if not (stat or status):
            return None
        return {"branch": branch, "stat": stat, "status": status}
    except Exception:
        return None

def write_archive_note(data, cache):
    sid = data.get("session_id", "unknown")
    pid = sid
    ent = cache.get(pid, {})
    cwd = data.get("cwd", "")
    reason = data.get("reason", "?")
    # C7 : le chemin fourni par Claude Code fait autorité sur toute reconstruction.
    _tp = data.get("transcript_path")
    _tp_path = _tp or f"{PROJECTS_DIR}/{sid}.jsonl"
    _tp_topic = _tp_n = None
    if _tp and os.path.exists(_tp):
        try:
            _r = parse_transcript(_tp)
            _tp_topic, _tp_n = _r[1], _r[2]
        except Exception:
            pass
    git = capture_git_diff(cwd)
    date = ent.get("date") or f"{datetime.now():%Y-%m-%d}"
    proj = ent.get("proj", classify(cwd))
    os.makedirs(ARCHIVE, exist_ok=True)
    safe_proj = re.sub(r'[^A-Za-z0-9]+', '-', proj).strip('-').lower()
    fn = os.path.join(ARCHIVE, f"{date}_{safe_proj}_{sid[:8]}.md")
    lines = [
        "---",
        f"name: session-{sid[:8]}",
        f"description: Archive auto de session {date} · {proj}",
        "metadata:\n  type: reference",
        "---\n",
        f"# Session {date} — {proj}\n",
        f"- **Sujet** : {ent.get('topic') or _tp_topic or '(non capté)'}",
        f"- **Messages** : {ent['n'] if ent.get('n') is not None else (_tp_n if _tp_n is not None else '?')}",
        f"- **Fin** : `{reason}`",
        f"- **Dossier** : `{cwd}`",
        f"- **Transcript brut** : `{_tp_path}`",
    ]
    if git:
        lines.append(f"\n## Diff git (`{git['branch']}`)\n")
        if git["stat"]:
            lines.append("```\n" + redact(git["stat"])[:3000] + "\n```")
        if git["status"]:
            lines.append("\n**Fichiers touchés (status) :**\n```\n" + redact(git["status"])[:2000] + "\n```")
    else:
        lines.append("\n*(Pas de diff git capté — cwd hors repo ou aucun changement.)*")
    open(fn, "w", encoding='utf-8').write("\n".join(lines))
    return fn

def commit_brain():
    """DÉSACTIVÉ le 2026-08-03 — Phase 0 du RFC Brain V3.

    Ce qui était fait ici : `git add -A`, commit, puis push. Donc TOUT ce qui
    avait changé dans le tronc partait, pas seulement l'archive de session.

    Ce que ça a produit : le commit e61fd01 « auto: archivage session » a avalé
    et poussé 19 fichiers d'un chantier de refonte en cours — MEMORY.md, 12
    hooks, la suite de tests. 612 commits de ce type existent dans l'historique.
    Un fichier partiel, un brouillon ou un secret en attente de nettoyage suivait
    le même chemin, sans que rien ne le signale.

    Pourquoi une simple liste blanche ne suffirait pas : des fichiers déjà
    présents dans l'index git seraient embarqués quand même. Le commit sûr
    demande un index isolé (GIT_INDEX_FILE) ou un worktree dédié, un manifeste
    exact, une comparaison du diff final au manifeste, puis UN commit. Ça se
    construit dans le lab, pas ici.

    Le push automatique ne revient qu'après ce dispositif. En attendant, la
    sauvegarde distante est assurée par le coffre chiffré (restic →
    Yuno15-bb/brain-backup), pas par un commit opportuniste.

    Archiver n'écrit plus dans git : l'archive est posée sur le disque, et c'est
    un humain qui décide ce qui entre dans l'historique.
    """
    return

def main():
    # ANTI-RÉCURSION (Phase 0 du RFC Brain V3, 2026-08-03).
    # Les agents de maintenance sont lancés en headless au SessionEnd ; leur
    # propre fin de session redéclenchait CE hook. Résultat : des archives
    # d'agents mêlées aux vraies sessions, et — tant que commit_brain écrivait
    # dans git — des commits intermédiaires posés avant même que la distillation
    # soit validée. auto_maintain et desktop_sync avaient déjà cette garde ;
    # archive_session ne l'avait pas.
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        sys.exit(0)

    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    try:
        cache, _ = rebuild_timeline()
        if data.get("session_id"):
            write_archive_note(data, cache)
        commit_brain()
    except Exception:
        pass  # jamais bloquer la session
    sys.exit(0)

if __name__ == "__main__":
    main()
