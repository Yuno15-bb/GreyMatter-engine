#!/usr/bin/env python3
"""Exercise the per-agent journal with an isolated Brain and fake CLI.

The cost log is shared: reading its last line can assign a neighboring run's
cost to an agent. A nonzero CLI exit must also produce a failed verdict.
"""
import json
import os
import shutil
import sys
import tempfile

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")


def scenario(silent, faulty, brain, bin_dir):
    """Run one watch pass and return the two journal entries."""
    os.environ["BRAIN_HOME"] = brain
    for subdir in ("state", "sessions"):
        os.makedirs(os.path.join(brain, subdir), exist_ok=True)
    for path in (os.path.join(brain, "state", "agents.jsonl"),
                 os.path.join(brain, "sessions", "cost.jsonl")):
        if os.path.exists(path):
            os.remove(path)
    for module in [m for m in list(sys.modules) if m.startswith("brain_")]:
        del sys.modules[module]
    sys.path.insert(0, HOOKS)
    import brain_upkeep as upkeep

    if faulty:
        def last_line_cost(offset):
            result = {}
            for line in open(upkeep.COST):
                try:
                    result = json.loads(line)
                except ValueError:
                    pass
            return {"cost_usd": round(result.get("total_cost_usd") or 0, 4)} if result else {}
        upkeep._cout_du_segment = last_line_cost

    upkeep.regen_sensors = lambda agents: None
    upkeep.decide = lambda now=None: {"chosen": "architect",
                                        "agents": {"architect": {"reason": "bench"}}}
    upkeep.cooldown_ok = lambda agent, now: True
    upkeep.record_run = lambda agent, now: None
    upkeep.guard = None
    permissions = type(sys)("robots_permissions")
    permissions.drapeaux = lambda agent, root: []
    sys.modules["robots_permissions"] = permissions
    upkeep.TASKS = dict(upkeep.TASKS)
    upkeep.TASKS["architect"] = "nothing"
    cli = "claude-silent" if silent else "claude-responds"
    upkeep.shutil = type(upkeep.shutil.__class__.__name__, (), {})
    upkeep.shutil.which = lambda name: os.path.join(bin_dir, cli) if name == "claude" else None

    with open(upkeep.COST, "a") as log:
        log.write(json.dumps({"total_cost_usd": 99.99, "session_id": "NEIGHBOR",
                              "usage": {"output_tokens": 1}}) + "\n")
    upkeep.run("bench")
    with open(os.path.join(brain, "state", "agents.jsonl")) as log:
        return [json.loads(line) for line in log]


def main():
    root = tempfile.mkdtemp(prefix="bench-agent-journal-")
    try:
        bin_dir = os.path.join(root, "bin")
        os.makedirs(bin_dir)
        for name, body in (("claude-responds",
                            '#!/bin/sh\necho \'{"total_cost_usd":0.1234,'
                            '"session_id":"FAKE-AGENT","usage":{"output_tokens":777}}\'\n'),
                           ("claude-silent", "#!/bin/sh\nexit 1\n")):
            path = os.path.join(bin_dir, name)
            with open(path, "w") as script:
                script.write(body)
            os.chmod(path, 0o755)
        brain = os.path.join(root, "brain")
        good = True

        def verify(label, condition):
            nonlocal good
            good = good and condition
            print(("  PASS  " if condition else "  FAIL  ") + label)

        print("A — the agent responds")
        entries = scenario(False, False, brain, bin_dir)
        verify("start and end name the architect", len(entries) == 2
               and entries[0]["phase"] == "start"
               and all(entry["agent"] == "architect" for entry in entries))
        verify("cost belongs to this run", entries[-1].get("cost_usd") == 0.1234)
        verify("session belongs to this run", entries[-1].get("session_id") == "FAKE-AGENT")

        print("B — the agent fails without output")
        entries = scenario(True, False, brain, bin_dir)
        verify("no cost is attributed", "cost_usd" not in entries[-1])
        verify("verdict records failure", entries[-1].get("verdict") == "failed-code-1")

        print("C — restore the faulty last-line reader")
        entries = scenario(True, True, brain, bin_dir)
        verify("the fault reappears and case B can catch it", entries[-1].get("cost_usd") == 99.99)
        print("PASS" if good else "FAIL")
        return 0 if good else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
