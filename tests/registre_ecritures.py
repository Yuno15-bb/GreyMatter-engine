
"""Verify that file writes are recorded accurately."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

ICI = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(ICI), "hooks", "registre_ecritures.py")


def charger(brain):
    """Verify that file writes are recorded accurately."""
    os.environ["BRAIN_HOME"] = brain
    spec = importlib.util.spec_from_file_location("registre_ecritures_%d" % time.time_ns(), HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tronc():
    d = tempfile.mkdtemp(prefix="banc-registre-")
    for z in ("projects", "lessons", "meta", "life", "skills", "state"):
        os.makedirs(os.path.join(d, z), exist_ok=True)
    return d


def lignes(brain):
    p = os.path.join(brain, "state", "note-writes.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]


def ecrire(brain, rel, texte):
    """Verify that file writes are recorded accurately."""
    p = os.path.join(brain, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(texte)


def scenario(mod, brain):
    """Verify that file writes are recorded accurately."""
    mod.main({"session_id": "SID-A", "tool_name": "Bash"})          
    time.sleep(1.05)
    ecrire(brain, "lessons/fixture-one.md", "# one\ntext\n")
    n1 = mod.main({"session_id": "SID-A", "tool_name": "Bash"})
    time.sleep(1.05)
    ecrire(brain, "projects/fixture-two.md", "# two\ntext\n")
    n2 = mod.main({"session_id": "SID-B", "tool_name": "Write"})
    return n1, n2, lignes(brain)


def conforme(n1, n2, entrees):
    """Verify that file writes are recorded accurately."""
    return (n1 == 1 and n2 == 1 and len(entrees) == 2
            and entrees[0]["path"] == "lessons/fixture-one.md"
            and entrees[0]["sid"] == "SID-A" and entrees[0]["tool"] == "Bash"
            and entrees[1]["path"] == "projects/fixture-two.md"
            and entrees[1]["sid"] == "SID-B" and entrees[1]["tool"] == "Write"
            and all(e["attribution"] == "coincidence" for e in entrees)
            
            
            and all(0 <= e["gap_s"] <= 5 for e in entrees))


def main():
    echecs = []

    
    brain = tronc()
    try:
        mod = charger(brain)
        n1, n2, entrees = scenario(mod, brain)
        print("Positive proof — two independent writes outside a tracked tool")
        for e in entrees:
            print("   %s  sid=%-6s tool=%-5s %s" % (e["ts"], e["sid"], e["tool"], e["path"]))
        ok = conforme(n1, n2, entrees)
        print("   %s path, session, tool, and elapsed time match; one entry per write"
              % ("✅" if ok else "❌"))
        if not ok:
            echecs.append("preuve positive")
        
        b2 = tronc()
        m2 = charger(b2)
        ecrire(b2, "lessons/before.md", "# before\n")
        m2.main({"session_id": "S", "tool_name": "Bash"})
        vide = lignes(b2) == []
        print("   %s first pass arms the checkpoint and writes no entry" % ("✅" if vide else "❌"))
        if not vide:
            echecs.append("premier passage bruyant")
        shutil.rmtree(b2, ignore_errors=True)
    finally:
        shutil.rmtree(brain, ignore_errors=True)

    
    print("\nCOUNTERTEST — does the check fail when its mechanism is broken?")
    sabotages = [
        ("the scan no longer sees writes",
         lambda m: setattr(m, "fiches_modifiees", lambda depuis: [])),
        ("no zone is covered",
         lambda m: setattr(m, "ZONES", ())),
        ("the checkpoint never advances",
         lambda m: setattr(m, "_jalon_ecrit", lambda t: None)),
        ("the scan reports a fabricated mtime (wrong elapsed time)",
         lambda m: setattr(m, "fiches_modifiees",
                           lambda depuis: [("lessons/fixture-one.md", 0.0)])),
    ]
    for nom, casser in sabotages:
        b = tronc()
        try:
            m = charger(b)
            casser(m)
            try:
                n1, n2, entrees = scenario(m, b)
                rouge = not conforme(n1, n2, entrees)
            except Exception:
                rouge = True
            print("   %s %s" % ("✅" if rouge else "❌ STILL PASSES —", nom))
            if not rouge:
                echecs.append("silent sabotage: " + nom)
        finally:
            shutil.rmtree(b, ignore_errors=True)

    
    print("\nDeclared scope (these omissions are intentional)")
    b = tronc()
    try:
        m = charger(b)
        m.main({"session_id": "S", "tool_name": "Bash"})
        time.sleep(1.05)
        ecrire(b, "tools/outside-scope.md", "# outside scope\n")
        n = m.main({"session_id": "S", "tool_name": "Bash"})
        print("   %s a write outside the five knowledge zones is not logged"
              % ("✅" if n == 0 else "❌"))
        if n != 0:
            echecs.append("scope exceeded")
    finally:
        shutil.rmtree(b, ignore_errors=True)

    print()
    if echecs:
        print("❌ TEST FAILED: " + " · ".join(echecs))
        return 1
    print("✅ TEST PASSED — the ledger sees writes outside tracked tools, "
          "and all four sabotages make it fail.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
