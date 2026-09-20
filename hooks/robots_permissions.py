#!/usr/bin/env python3
"""robots_permissions — ce qu'un robot du Brain a le droit de faire, robot par robot.

POURQUOI CE FICHIER EXISTE (décidé le 2026-09-14, écrit le 2026-09-15)
    Les deux lanceurs de robots (`auto_maintain.py`, `brain_upkeep.py`) passaient
    `--dangerously-skip-permissions` : aucune commande n'était jamais refusée à un robot.
    C'est ce qui a rendu possibles les portes, le `git reset --hard` du 08/09 et le
    `--no-verify` du 09/09. Le verrou du pre-commit n'en voit qu'un geste sur trois.
    Condition 1 et 2 de la levée du gel : tools/REPRISE-2026-09-14-reouverture-et-sobriete.md,
    section 7.

LE PRINCIPE : AUTORISER, PAS INTERDIRE
    Une liste noire se contourne par une autre orthographe. Ici, tout ce qui n'est pas
    nommé est refusé par Claude lui-même, avant exécution :
      · `--restricted` retire Bash sauf si `--tools` le nomme, ignore les réglages
        utilisateur (donc leurs éventuelles règles d'autorisation), refuse le passe-droit
        et protège les fichiers git et de réglages ;
      · `--permission-prompts none` : personne ne peut dire oui, tout ce qui demanderait
        une permission est refusé ;
      · chaque robot reçoit ses chemins d'écriture et ses commandes EXACTES.
    Aucune écriture git n'est autorisée à aucun robot : les commits sont faits par du code,
    lancé par le shell après eux. Depuis le 2026-09-19 ce code est
    `tools/revendication/revendiquer.py`, qui ne commite QUE les fichiers écrits par les
    robots de la passe — leur propre journal d'actions fait foi. `commit_par_zone.py` reste
    le repli du paquet livré, où `tools/` n'est pas distribué.

CE QUE `--restricted` COUPE, ET CE QU'ON REND
    Il ignore ~/.claude/settings.json en entier. Deux choses doivent donc être rendues :
      · les définitions d'agents (`--agent jardinier` n'est plus trouvé) → `--agents`,
        lues depuis ~/.claude/agents/<nom>.md ;
      · le hook `on_fiche_write.py`, qui masque les secrets écrits par un robot → `--settings`.
    Les autres hooks (rappel injecté, battement, capsule, lab) visent une session humaine
    et ne sont pas rendus.

MESURÉ LE 2026-09-15, dans un dépôt jetable (haiku, 4 centimes)
    Refusés : `git reset --hard`, `ok.py && git reset --hard`, `ok.py; rm state/FREEZE`,
    `ok.py $(rm state/FREEZE)`, `python3 -c …`, `mv state/FREEZE …`, Edit d'un hook,
    Write dans .git/hooks. Passés : la commande autorisée, l'écriture dans lessons/, la
    lecture d'un dossier ajouté. Dépôt vérifié ensuite : HEAD, FREEZE et hook intacts.

CE QUE ÇA CHANGE POUR LES ROBOTS
    Un robot ne peut plus déplacer ni renommer une fiche (il faudrait `mv` ou `git mv`) :
    il le PROPOSE dans state/a-valider.md. Il n'écrit plus MEMORY.md : la place d'une fiche
    dans la carte se propose aussi (ADR-0015). Il ne peut plus toucher hooks/, tools/, tests/,
    skills/, agents/, ni meta/ depuis le 2026-09-16 (les règles et le vocabulaire du rappel). Il n'appelle plus brain_recall.py, qui compterait ses lectures comme
    des ouvertures humaines.
"""
import json
import os
import re

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
AGENTS = os.path.expanduser("~/.claude/agents")
SETTINGS = os.path.expanduser("~/.claude/settings.json")
TRANSCRIPTS = os.path.join(os.path.expanduser("~/.claude/projects"),
                           os.path.expanduser("~").replace(os.sep, "-"))

# Où le savoir s'écrit. Chemins relatifs au dossier de travail du robot, qui est le Brain.
# PAS MEMORY.md (2026-09-15) : ADR-0015 veut chaque entrée de carte validée par un humain, et le
# pre-commit refuse tout commit tant que la carte et son manifeste divergent. Un robot qui range
# dans la carte bloquerait donc tous les enregistrements. Il propose, dans state/a-valider.md.
# PAS meta/ (décision de l'auteur, 2026-09-16, après la passe adverse du 15/09 21 h) : ce dossier
# porte les règles que suivent les sessions (meta/jardinage-regles.md, « source de vérité » du
# jardinier) et le vocabulaire du moteur de rappel (meta/familles.json, lu par brain_recall.py
# et index_lecons.py). Un robot qui l'écrit change ce que toutes les sessions retrouvent, ou
# réécrit sa propre loi. Une retouche de meta/ se propose dans state/a-valider.md.
SAVOIR = ["projects/**", "lessons/**", "life/**", "state/a-valider.md"]

# Les pulses de la capsule : les définitions d'agents les écrivent sous deux formes.
PULSES = ["python3 hooks/brain_status.py *", "python3 ~/.c-brain/trunk/hooks/brain_status.py *"]

# LA FAMILLE EST CE QU'ON APPELLE ; LA MISSION EST CE QU'ON FAIT (2026-09-20).
# Les huit rôles d'origine n'ont pas disparu : chacun garde ses outils, sa zone d'écriture et
# ses commandes. Ce qui change, c'est la surface : Claude Code ne voit plus que quatre
# vaisseaux (`agents/<famille>.md`), et la mission voyage dans la consigne. Les noms sont des
# noms propres — ADR-0013, « un identifiant interne ne se traduit jamais » : c'est précisément
# la traduction de `distillateur` en `distiller` qui avait rendu cinq agents introuvables le
# 19/08. cf. projects/claude-brain/renommage-agents-familles-2026-09-20.md
FAMILLE = {
    "mecanicien": "nostromo",   "machiniste": "nostromo",
    "distillateur": "narcissus", "jardinier": "narcissus",
    "challenger": "sulaco", "architecte": "sulaco", "archiviste": "sulaco",
    "synthetiseur": "anesidora",
}

ROBOTS = {
    "distillateur": {"outils": "Read,Edit,Write,Grep,Glob,Bash", "ecrit": SAVOIR,
                     "lance": ["python3 hooks/index_lecons.py"], "lit_aussi": [TRANSCRIPTS]},
    "jardinier":    {"outils": "Read,Edit,Write,Grep,Glob,Bash",
                     "ecrit": SAVOIR + ["state/a-classer.md", "state/coherence.json"],
                     "lance": ["python3 hooks/brain_doctor.py --json",
                               "python3 hooks/brain_utility.py --json",
                               "python3 hooks/index_lecons.py"]},
    "architecte":   {"outils": "Read,Edit,Write,Grep,Glob,Bash", "ecrit": SAVOIR, "lance": []},
    "challenger":   {"outils": "Read,Write,Edit,Grep,Glob,Bash", "ecrit": ["state/challenges.json"],
                     "lance": []},
    "archiviste":   {"outils": "Read,Edit,Write,Grep,Glob,Bash", "ecrit": SAVOIR,
                     "lance": ["python3 hooks/brain_utility.py --json"]},
    "mecanicien":   {"outils": "Read,Edit,Write,Grep,Glob,Bash", "ecrit": SAVOIR,
                     "lance": ["python3 hooks/brain_doctor.py --json"]},
}


def definition(mission):
    """La définition envoyée à Claude Code pour CETTE mission, au format attendu par --agents.

    Le fichier lu est celui de la FAMILLE ; le prompt rendu est l'en-tête commun du vaisseau
    plus la SEULE section `## MISSION — <mission>`. Envoyer le fichier entier coûterait les
    autres missions à chaque réveil — le NARCISSUS pèse 31 Ko pour 19 Ko de distillation —
    et la sobriété se mesure en octets envoyés."""
    famille = FAMILLE[mission]
    texte = open(os.path.join(AGENTS, f"{famille}.md"), encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n(.*)", texte, re.S)
    entete, corps = (m.group(1), m.group(2)) if m else ("", texte)
    desc = re.search(r"^description:\s*(.*)$", entete, re.M)
    parts = re.split(r"^## MISSION — (\S+)\s*$", corps, flags=re.M)
    commun, sections = parts[0], dict(zip(parts[1::2], parts[2::2]))
    if mission not in sections:
        raise KeyError(f"{famille}.md ne porte pas de section « ## MISSION — {mission} »")
    return {"description": desc.group(1).strip() if desc else famille,
            "prompt": commun.rstrip() + f"\n\n## MISSION — {mission}\n" + sections[mission],
            "tools": ROBOTS[mission]["outils"].split(",")}


def hooks_rendus(brain=BRAIN):
    """Le seul hook rendu aux robots : on_fiche_write (masquage des secrets), pris tel quel
    dans les réglages de l'utilisateur, avec le chemin du Brain réécrit si on tourne sur une copie."""
    reel = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
    try:
        groupes = json.load(open(SETTINGS, encoding="utf-8")).get("hooks", {}).get("PostToolUse", [])
    except Exception:
        return {}
    gardes = []
    for g in groupes:
        hs = [dict(h, command=h["command"].replace(reel, brain))
              for h in g.get("hooks", []) if "on_fiche_write.py" in h.get("command", "")]
        if hs:
            gardes.append(dict(g, hooks=hs))
    return {"hooks": {"PostToolUse": gardes}} if gardes else {}


def drapeaux(mission, brain=BRAIN):
    """Les options à placer après `claude -p --model … --output-format json`, prompt APRÈS.

    `--agent` vient en dernier exprès : `--allowedTools` et `--add-dir` avalent tous les
    arguments qui suivent, prompt compris, tant qu'une autre option ne les ferme pas
    (constaté le 2026-09-15 : « Input must be provided »)."""
    r = ROBOTS[mission]
    famille = FAMILLE[mission]
    autorise = (["Read", "Grep", "Glob"]
                + [f"Edit({p})" for p in r["ecrit"]]
                + [f"Bash({c})" for c in r["lance"] + PULSES])
    f = ["--restricted", "--permission-prompts", "none", "--strict-mcp-config",
         "--tools", r["outils"],
         "--agents", json.dumps({famille: definition(mission)}, ensure_ascii=False)]
    rendus = hooks_rendus(brain)
    if rendus:
        f += ["--settings", json.dumps(rendus, ensure_ascii=False)]
    for d in r.get("lit_aussi", []):
        f += ["--add-dir", d]
    f += ["--allowedTools", *autorise, "--agent", famille]
    return f


if __name__ == "__main__":
    import shlex, sys
    for a in (sys.argv[1:] or ROBOTS):
        print(a, "→", shlex.join(x if len(x) < 120 else x[:60] + "…" for x in drapeaux(a)))
