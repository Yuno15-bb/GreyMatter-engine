#!/usr/bin/env python3
"""robots_permissions — what a Brain robot is allowed to do, robot by robot.

WHY THIS FILE EXISTS (decided on 2026-09-14, written on 2026-09-15)
    The two robot launchers (`auto_maintain.py`, `brain_upkeep.py`) passed
    `--dangerously-skip-permissions`: no command was ever refused to a robot.
    That is what made possible the lost work, the `git reset --hard` of 08/09 and the
    `--no-verify` of 09/09. The pre-commit lock only sees one gesture in three.
    Conditions 1 and 2 for lifting the freeze.

THE PRINCIPLE: ALLOW, DO NOT FORBID
    A blacklist is bypassed by another spelling. Here, everything that is not
    named is refused by Claude itself, before execution:
      · `--restricted` removes Bash unless `--tools` names it, ignores the user's
        settings (and so any permission rules they hold), refuses the free pass
        and protects git and settings files;
      · `--permission-prompts none`: nobody can say yes, everything that would ask
        for a permission is refused;
      · each robot gets its EXACT write paths and commands.
    No git write is allowed to any robot: commits are made by code, launched by the
    shell after them. On the author's trunk that code is a claim script that commits
    ONLY the files written by the robots of the pass — their own action journal is
    authoritative. `commit_par_zone.py` remains the fallback of the shipped package,
    where that script is not distributed.

WHAT `--restricted` CUTS, AND WHAT IS GIVEN BACK
    It ignores ~/.claude/settings.json entirely. So two things must be given back:
      · the agent definitions (`--agent <name>` is no longer found) → `--agents`,
        read from ~/.claude/agents/<name>.md;
      · the `on_fiche_write.py` hook, which masks secrets written by a robot → `--settings`.
    The other hooks (injected recall, heartbeat, capsule, lab) target a human session
    and are not given back.

MEASURED ON 2026-09-15, in a throwaway repository (haiku, 4 cents)
    Refused: `git reset --hard`, `ok.py && git reset --hard`, `ok.py; rm state/FREEZE`,
    `ok.py $(rm state/FREEZE)`, `python3 -c …`, `mv state/FREEZE …`, Edit of a hook,
    Write into .git/hooks. Allowed: the permitted command, the write into lessons/, the
    read of an added folder. Repository checked afterwards: HEAD, FREEZE and hook intact.

WHAT IT CHANGES FOR THE ROBOTS
    A robot can no longer move or rename a note (that would take `mv` or `git mv`):
    it PROPOSES it in state/a-valider.md. It no longer writes MEMORY.md: a note's place
    on the map is proposed too (ADR-0015). It can no longer touch hooks/, tools/, tests/,
    skills/, agents/, nor meta/ since 2026-09-16 (the rules and the recall vocabulary).
    It no longer calls brain_recall.py, which would count its reads as human openings.
"""
import json
import os
import re

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
AGENTS = os.path.expanduser("~/.claude/agents")
SETTINGS = os.path.expanduser("~/.claude/settings.json")
# Same key as archive_session._transcripts_key(): BOTH "/" and "." become "-", or a
# home like /Users/john.smith never finds its transcripts.
TRANSCRIPTS = os.path.join(os.path.expanduser("~/.claude/projects"),
                           os.path.expanduser("~").replace("/", "-").replace(".", "-"))

# Where knowledge is written. Paths relative to the robot's working folder, which is the Brain.
# NOT MEMORY.md (2026-09-15): ADR-0015 wants every map entry validated by a human, and the
# pre-commit refuses any commit while the map and its manifest diverge. A robot filing into
# the map would therefore block every save. It proposes, in state/a-valider.md.
# NOT meta/ (the author's decision, 2026-09-16, after the adversarial pass of 15/09 9 pm): that
# folder holds the rules sessions follow (meta/jardinage-regles.md, the gardener's "source of
# truth") and the recall engine's vocabulary (meta/familles.json, read by brain_recall.py
# and index_lecons.py). A robot writing it changes what every session finds, or
# rewrites its own law. A change to meta/ is proposed in state/a-valider.md.
SAVOIR = ["projects/**", "lessons/**", "life/**", "state/a-valider.md"]

# The capsule's pulses: agent definitions write them in two forms.
PULSES = ["python3 hooks/brain_status.py *", "python3 ~/.c-brain/trunk/hooks/brain_status.py *"]

# THE SHIP IS WHAT YOU CALL; THE MISSION IS WHAT IT DOES (2026-09-20).
# The eight original roles have not gone away: each keeps its tools, its write zone and
# its commands. What changes is the surface: Claude Code only sees four
# ships (`agents/<ship>.md`), and the mission travels in the instruction. Ship names are
# proper nouns and are never translated (ADR-0013, "an internal identifier is never
# translated"). Mission names are the English ones throughout this package: the agent
# files' `## MISSION — <mission>` headings, the launchers and this table all use them.
FAMILLE = {
    "mechanic": "nostromo",   "machinist": "nostromo",
    "distiller": "narcissus", "gardener": "narcissus",
    "challenger": "sulaco", "architect": "sulaco", "archivist": "sulaco",
    "synthesizer": "anesidora",
}
ROBOTS = {
    "distiller": {"outils": "Read,Edit,Write,Grep,Glob,Bash", "ecrit": SAVOIR,
                     "lance": ["python3 hooks/index_lecons.py"], "lit_aussi": [TRANSCRIPTS]},
    "gardener":  {"outils": "Read,Edit,Write,Grep,Glob,Bash",
                     "ecrit": SAVOIR + ["state/a-classer.md", "state/coherence.json"],
                     "lance": ["python3 hooks/brain_doctor.py --json",
                               "python3 hooks/brain_utility.py --json",
                               "python3 hooks/index_lecons.py"]},
    "architect": {"outils": "Read,Edit,Write,Grep,Glob,Bash", "ecrit": SAVOIR, "lance": []},
    "challenger":   {"outils": "Read,Write,Edit,Grep,Glob,Bash", "ecrit": ["state/challenges.json"],
                     "lance": []},
    "archivist": {"outils": "Read,Edit,Write,Grep,Glob,Bash", "ecrit": SAVOIR,
                     "lance": ["python3 hooks/brain_utility.py --json"]},
    "mechanic":  {"outils": "Read,Edit,Write,Grep,Glob,Bash", "ecrit": SAVOIR,
                     "lance": ["python3 hooks/brain_doctor.py --json"]},
}


def definition(mission):
    """The definition sent to Claude Code for THIS mission, in the format --agents expects.

    The file read is the SHIP's; the prompt returned is the ship's common header
    plus ONLY the `## MISSION — <mission>` section. Sending the whole file would cost the
    other missions on every wake-up — NARCISSUS weighs 31 KB for 19 KB of distillation —
    and sobriety is measured in bytes sent."""
    famille = FAMILLE[mission]
    texte = open(os.path.join(AGENTS, f"{famille}.md"), encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n(.*)", texte, re.S)
    entete, corps = (m.group(1), m.group(2)) if m else ("", texte)
    desc = re.search(r"^description:\s*(.*)$", entete, re.M)
    parts = re.split(r"^## MISSION — (\S+)\s*$", corps, flags=re.M)
    commun, sections = parts[0], dict(zip(parts[1::2], parts[2::2]))
    if mission not in sections:
        raise KeyError(f"{famille}.md carries no section '## MISSION — {mission}'")
    return {"description": desc.group(1).strip() if desc else famille,
            "prompt": commun.rstrip() + f"\n\n## MISSION — {mission}\n" + sections[mission],
            "tools": ROBOTS[mission]["outils"].split(",")}


def hooks_rendus(brain=BRAIN):
    """The only hook given back to the robots: on_fiche_write (secret masking), taken as is
    from the user's settings, with the Brain's path rewritten when running on a copy."""
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
    """The options to place after `claude -p --model … --output-format json`, prompt AFTER.

    `--agent` comes last on purpose: `--allowedTools` and `--add-dir` swallow every
    argument that follows, prompt included, until another option closes them
    (seen on 2026-09-15: "Input must be provided")."""
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
