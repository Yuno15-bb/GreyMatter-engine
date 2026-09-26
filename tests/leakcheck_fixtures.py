#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""Prove that the synthetic fixture exception has not opened a leak path.

The leak check must allow a fake key in `fiche_write_contract.py` so that test
can prove a real key is rejected. This countercheck exercises the exception:
  1. a declared decoy is allowed under tests/;
  2. the same decoy is rejected outside tests/;
  3. a nearby but undeclared value is rejected;
  4. a real key and personal path are rejected even under tests/;
  5. the marker count stays fixed.

Forbidden values are assembled at runtime. A complete literal here would
trigger the scanner on its own test and require a circular exemption.

Run: python3 tests/leakcheck_fixtures.py
"""

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("leakcheck", ROOT / "leakcheck.py")
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)

COMPILED = [(label, re.compile(motif)) for label, motif in lc.MARKERS]


def fuites(source: str, texte: str):
    """Call the real scanner without duplicating its detection logic."""
    trouve = []
    lc.scan(source, texte, COMPILED, trouve)
    return [(label, extrait) for _, label, extrait in trouve]


# Assemble values at runtime as described above.
LEURRE_CLE = "sk-" + "ant-" + "AAAABBBBCCCCDDDDEEEE"
LEURRE_CHEMIN = "/Users/" + "x/"
VRAIE_CLE = "sk-" + "ant-" + "api03" + "-9f2Kd7Qm4Xr8Tz1Lb6Vn0Yc3Hs5Wj"
VRAI_CHEMIN = "/Users/" + "exampleuser/"
AUTRE_CHEMIN = "/Users/" + "exampleuser2/"
VOISIN = "sk-" + "ant-" + "AAAABBBBCCCCDDDDEEEF"   # one extra letter, undeclared

# Assemble the assignment as well as its value. A formatted assignment with
# the keyword and quoted value on one line would match the plaintext secret
# pattern in this file. This occurred twice on 2026-08-26, even in a comment.
def _affectation(valeur: str) -> str:
    return "SECRET" + ' = "' + valeur + '"'


# Each case requires a specific marker, not merely any alert. Allowing a real
# key as a decoy once still appeared to fail because another marker caught the
# assignment shape. The targeted marker had actually been disabled.
CAS = [
    # (case name, path, text, expected marker; None means clean)
    ("declared decoy passes under tests/",
     "tests/fiche_write_contract.py", _affectation(LEURRE_CLE), None),
    ("path decoy passes under tests/",
     "tests/a1_pixel_lib.py", f'p = "{LEURRE_CHEMIN}.c-brain"', None),

    ("same decoy is blocked outside tests/",
     "cbrain/engine-lib.sh", _affectation(LEURRE_CLE), "Anthropic key"),
    ("same path decoy is blocked outside tests/",
     "install.sh", f'p = "{LEURRE_CHEMIN}.c-brain"', "personal path"),

    ("nearby undeclared value is blocked",
     "tests/fiche_write_contract.py", _affectation(VOISIN), "Anthropic key"),

    ("real key is blocked under tests/",
     "tests/fiche_write_contract.py", _affectation(VRAIE_CLE), "Anthropic key"),
    ("real personal path is blocked under tests/",
     "tests/a1_pixel_lib.py", f'p = "{VRAI_CHEMIN}.c-brain"', "personal path"),
    ("another invented user path is blocked under tests/",
     "tests/a1_pixel_lib.py", f'p = "{AUTRE_CHEMIN}.c-brain"', "personal path"),

    ("test history gets the same narrow exception",
     "history:tests/fiche_write_contract.py", _affectation(LEURRE_CLE), None),
    ("engine file history stays blocked",
     "history:install.sh", _affectation(LEURRE_CLE), "Anthropic key"),
]


def main() -> int:
    echecs = []

    for intitule, source, texte, marqueur_attendu in CAS:
        trouve = fuites(source, texte)
        labels = [l for l, _ in trouve]
        if marqueur_attendu is None:
            ok = not trouve
            attendu = "clean"
        else:
            # Require the targeted marker; another marker could mask its failure.
            ok = marqueur_attendu in labels
            attendu = f"RED for {marqueur_attendu}"
        obtenu = f"RED for {labels}" if trouve else "clean"
        marque = "✅" if ok else "❌"
        print(f"  {marque} {intitule}\n       expected {attendu}, got {obtenu}")
        if not ok:
            echecs.append(intitule)

    # No marker may be silently disabled.
    attendus = 21
    if len(lc.MARKERS) != attendus:
        print(f"  ❌ marker count changed: {len(lc.MARKERS)} instead of {attendus}")
        echecs.append("marker count")
    else:
        print(f"  ✅ all {attendus} markers remain active")

    # Keep the decoy exception limited to tests/.
    if lc.FIXTURES_DIRS != ("tests/",):
        print(f"  ❌ decoy scope widened: {lc.FIXTURES_DIRS}")
        echecs.append("decoy scope")
    else:
        print("  ✅ decoys remain confined to tests/")

    print()
    if echecs:
        print(f"⛔ {len(echecs)} countercheck(s) failed — the exception has a gap.")
        for e in echecs:
            print(f"   · {e}")
        return 1
    print("✅ Exception holds: decoys pass and other values are blocked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
