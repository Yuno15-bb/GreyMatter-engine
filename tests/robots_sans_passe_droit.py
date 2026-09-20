#!/usr/bin/env python3
"""robots_sans_passe_droit.py — aucun robot du Brain ne se lance avec le passe-droit.

CE QUI EST ARRIVÉ. Jusqu'au 2026-09-15, `auto_maintain.py` et `brain_upkeep.py` lançaient
les robots avec `--dangerously-skip-permissions` : aucune commande ne leur était refusée.
Le 08/09, un `git reset --hard` ; le 09/09, un `--no-verify`. Le verrou du pre-commit ne
voit ni l'un ni l'autre. Les droits vivent désormais dans `hooks/robots_permissions.py`.

CE QUE LE BANC VÉRIFIE, SANS APPELER CLAUDE (gratuit, déterministe) :
  1. aucun fichier de hooks/ ne contient le passe-droit, hors la doc de robots_permissions ;
  2. les deux lanceurs passent bien par `drapeaux()` ;
  3. pour chaque robot : `--restricted` et `--permission-prompts none` présents, aucune
     règle d'autorisation qui nomme git, rm, mv ou un Bash sans commande ;
  4. `--agent` ferme la liste des autorisations (sinon le prompt est avalé) ;
  5. aucun robot n'écrit MEMORY.md ni le manifeste de carte (ADR-0015 : validés par un humain).
  6. aucun robot n'écrit meta/ (décision de l'auteur, 2026-09-16) : les règles des sessions et le
     vocabulaire du moteur de rappel s'y trouvent ; une retouche se propose dans state/a-valider.md.

CE QU'IL NE VÉRIFIE PAS. Que Claude refuse vraiment : ça, c'est l'épreuve dynamique du
2026-09-15 dans une copie du Brain (les deux lanceurs, 9 gestes refusés sur 9, contre-épreuve
rouge), rangée dans ~/.c-brain/trunk-sauvegarde-hors-arbre/2026-09-15-reparation-carte/.

Sabotage vérifié à l'écriture : remettre le passe-droit dans brain_upkeep.py, ou ajouter
"Bash(git *)" à un robot, fait sortir le banc en code 1. Le 2026-09-16 : remettre "meta/**"
dans SAVOIR fait sortir le banc en code 1 (les 5 robots qui écrivent le savoir), le retirer
le ramène à 0.

Run: python3 tests/robots_sans_passe_droit.py --check
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
sys.path.insert(0, HOOKS)

PASSE_DROIT = "--dangerously-skip-permissions"
INTERDITS = ("git", "rm ", "mv ", "python3 -c", "sh ", "bash ")


def defauts():
    d = []
    for nom in sorted(os.listdir(HOOKS)):
        if nom.endswith(".py") and nom != "robots_permissions.py":
            if PASSE_DROIT in open(os.path.join(HOOKS, nom), encoding="utf-8").read():
                d.append(f"{nom} contient encore {PASSE_DROIT}")
    for lanceur in ("auto_maintain.py", "brain_upkeep.py"):
        if "drapeaux(" not in open(os.path.join(HOOKS, lanceur), encoding="utf-8").read():
            d.append(f"{lanceur} ne passe pas par robots_permissions.drapeaux()")
    import robots_permissions as rp
    for agent in rp.ROBOTS:
        try:
            f = rp.drapeaux(agent)
        except Exception as e:
            d.append(f"{agent} : les droits ne se construisent pas ({e})")
            continue
        if PASSE_DROIT in f or "bypassPermissions" in f:
            d.append(f"{agent} : passe-droit dans ses options")
        if "--restricted" not in f:
            d.append(f"{agent} : --restricted absent")
        if "--permission-prompts" not in f or f[f.index("--permission-prompts") + 1] != "none":
            d.append(f"{agent} : --permission-prompts none absent")
        if "--allowedTools" not in f or "--agent" not in f or f.index("--agent") < f.index("--allowedTools"):
            d.append(f"{agent} : --agent ne ferme pas la liste des autorisations")
            continue
        for regle in f[f.index("--allowedTools") + 1:f.index("--agent")]:
            if regle in ("Bash", "Edit", "Write", "Bash(*)", "Edit(**)"):
                d.append(f"{agent} : règle trop large « {regle} »")
            if regle.startswith("Bash(") and any(regle[5:].startswith(x) for x in INTERDITS):
                d.append(f"{agent} : commande interdite autorisée « {regle} »")
            if regle.startswith("Edit(") and ("MEMORY.md" in regle or "tools/" in regle):
                d.append(f"{agent} : écriture de la carte autorisée « {regle} »")
            if regle.startswith("Edit(") and "meta/" in regle:
                d.append(f"{agent} : écriture des règles autorisée « {regle} »")
    return d


if __name__ == "__main__":
    trouves = defauts()
    for t in trouves:
        print("❌", t)
    if not trouves:
        print("✅ robots sans passe-droit : 2 lanceurs, 6 robots, aucune écriture git autorisée")
    sys.exit(1 if trouves else 0)
