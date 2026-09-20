#!/usr/bin/env python3
"""Banc du journal par agent (state/agents.jsonl) — chantier MAGI, 19/09/2026.

Ce que le journal doit garantir, et que les trois journaux existants ne garantissent
pas : une ligne NOMINATIVE par passage d'agent, avec son verdict et SON coût.
status.json n'a qu'un état global écrasé au passage suivant, upkeep.json ne compte que
des totaux, cost.jsonl porte le coût sans nom d'agent.

Deux pièges que ce banc tient, tous deux VUS le 19/09 :
  1. cost.jsonl est un journal PARTAGÉ. Prendre « la dernière ligne » attribue à
     l'agent de veille le coût d'une distillation voisine. Scénario C ci-dessous remet
     ce défaut et le banc DOIT rougir — sans ça, il ne protégerait de rien.
  2. subprocess.run ne lève rien sur un code de sortie non nul : le journal écrivait
     « ok » pour un agent qui venait d'échouer. Un panneau nourri par ce verdict-là
     aurait menti en vert.

Usage : python3 tests/banc_journal_agents.py   → 0 si tout est vert.
"""
import os, sys, json, shutil, tempfile

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")


def scenario(muet, defaut, bac, bin_dir):
    """Rejoue un passage de veille dans un Brain jetable et rend les lignes écrites."""
    os.environ["BRAIN_HOME"] = bac
    for sous in ("state", "sessions"):
        os.makedirs(os.path.join(bac, sous), exist_ok=True)
    for f in (os.path.join(bac, "state", "agents.jsonl"),
              os.path.join(bac, "sessions", "cost.jsonl")):
        if os.path.exists(f):
            os.remove(f)
    for mod in [m for m in list(sys.modules) if m.startswith("brain_")]:
        del sys.modules[mod]
    sys.path.insert(0, HOOKS)
    import brain_upkeep as U

    if defaut:
        def _defaut(offset):
            o = {}
            for l in open(U.COST):
                try:
                    o = json.loads(l)
                except Exception:
                    pass
            return {"cout_usd": round(o.get("total_cost_usd") or 0, 4)} if o else {}
        U._cout_du_segment = _defaut

    U.regen_sensors = lambda agents: None
    U.decide = lambda now=None: {"chosen": "architecte",
                                 "agents": {"architecte": {"reason": "banc"}}}
    U.cooldown_ok = lambda a, now: True
    U.record_run = lambda a, now: None
    U.guard = None
    faux = type(sys)("robots_permissions")
    faux.drapeaux = lambda agent, brain: []
    sys.modules["robots_permissions"] = faux
    U.TASKS = dict(U.TASKS)
    U.TASKS["architecte"] = "rien"
    outil = "claude-muet" if muet else "claude-repond"
    U.shutil = type(U.shutil.__class__.__name__, (), {})  # garde-fou : pas de vrai claude
    U.shutil.which = lambda n: os.path.join(bin_dir, outil) if n == "claude" else None

    # une DISTILLATION VOISINE écrit sa ligne de coût juste avant le passage
    with open(U.COST, "a") as f:
        f.write(json.dumps({"total_cost_usd": 99.99, "session_id": "VOISINE",
                            "usage": {"output_tokens": 1}}) + "\n")
    U.run("banc")
    with open(os.path.join(bac, "state", "agents.jsonl")) as f:
        return [json.loads(l) for l in f]


def main():
    racine = tempfile.mkdtemp(prefix="banc-journal-agents-")
    bin_dir = os.path.join(racine, "bin")
    os.makedirs(bin_dir)
    for nom, corps in (("claude-repond",
                        '#!/bin/sh\necho \'{"total_cost_usd":0.1234,'
                        '"session_id":"FAUX-AGENT","usage":{"output_tokens":777}}\'\n'),
                       ("claude-muet", "#!/bin/sh\nexit 1\n")):
        chemin = os.path.join(bin_dir, nom)
        with open(chemin, "w") as f:
            f.write(corps)
        os.chmod(chemin, 0o755)
    bac = os.path.join(racine, "brain")

    vert = True

    def v(nom, cond):
        nonlocal vert
        vert = vert and cond
        print(("  VERT  " if cond else "  ROUGE ") + nom)

    print("A — l'agent répond")
    l = scenario(False, False, bac, bin_dir)
    v("début + fin, tous deux nommés architecte",
      len(l) == 2 and l[0]["phase"] == "debut" and all(x["agent"] == "architecte" for x in l))
    v("le coût est celui du passage (0.1234)", l[-1].get("cout_usd") == 0.1234)
    v("la session du passage est retenue", l[-1].get("session_id") == "FAUX-AGENT")

    print("B — l'agent échoue sans rien écrire")
    l = scenario(True, False, bac, bin_dir)
    v("aucun coût attribué", "cout_usd" not in l[-1])
    v("le verdict dit l'échec", l[-1].get("verdict") == "echec-code-1")

    print("C — contre-épreuve : on remet le défaut « dernière ligne » (doit ROUGIR)")
    l = scenario(True, True, bac, bin_dir)
    rougit = l[-1].get("cout_usd") == 99.99
    v("le défaut réapparaît bien, donc le banc B sait le voir", rougit)

    shutil.rmtree(racine, ignore_errors=True)
    print("VERT" if vert else "ROUGE")
    return 0 if vert else 1


if __name__ == "__main__":
    sys.exit(main())
