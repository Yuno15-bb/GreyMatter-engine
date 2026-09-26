#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""The anonymizer must not be able to disable itself silently.

`generalize.py` replaces patterns in package files, and `rules.json` stores those
patterns. A previous broadening of JSON coverage caused the rules to rewrite their own
definitions: each pattern became its replacement, leaving a live counter but no action.

Two guards prevent that failure. A pattern equal to its replacement is a no-op, and no
glob may select the marker-carrying tools `rules.json`, `generalize.py`, or `leakcheck.py`.
The tests below cover both conditions.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class ReglesNonMuettes(unittest.TestCase):

    def setUp(self):
        with open(os.path.join(ROOT, "rules.json"), encoding="utf-8") as f:
            self.rules = json.load(f)

    def test_aucune_regle_ne_cherche_ce_qu_elle_ecrit(self):
        import generalize
        muettes = [r.get("id", "?") for r in self.rules.get("replacements", [])
                   if "replace" in r and generalize.rule_pattern(r) == r["replace"]]
        self.assertEqual(
            muettes, [],
            "rule(s) became a no-op: the search pattern equals its replacement, "
            f"so nothing is anonymized: {muettes}")

    def test_les_outils_qui_portent_les_marqueurs_ne_sont_jamais_reecrits(self):
        import generalize
        vises = {p.name for p in generalize.targets(["**/*.json", "**/*.py"])}
        for interdit in ("rules.json", "generalize.py", "leakcheck.py"):
            # Avoid dumping the full target set into the failure message.
            self.assertTrue(
                interdit not in vises,
                f"{interdit} is selected by a rule although it carries the "
                "markers by design; it could rewrite itself and disable the rule")


if __name__ == "__main__":
    unittest.main(verbosity=1)
