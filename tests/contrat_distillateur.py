#!/usr/bin/env python3
"""Executable provenance contract for the distiller prompt.

The prompt cannot be tested as a function, but its output format can. These
synthetic sources cover the kinds of authority it may carry. E1 requires an
exact source excerpt except when the origin is unknown.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from provenance_invariants import controler  # noqa: E402


def bloc_provenance(case, write=True, excerpt=True):
    """Build the canonical provenance and authority blocks for a source."""
    if not write:
        return ""
    kind = case["kind"]
    ref = case.get("ref", "")
    scope = case.get("scope", "repository")
    lines = ["provenance:", f"  kind: {kind}"]
    if kind != "unknown":
        lines.append(f'  ref: "{ref}"')
        lines.append(f"  captured_at: {case['captured_at']}")
        if excerpt:
            lines.append(f'  extrait: "{case["extrait"]}"')
    if case.get("derived_from"):
        lines.append(f"  derived_from: [{case['derived_from']}]")
    validated = ((kind == "user_decision" and bool(ref))
                 or (kind == "internal_experience" and bool(case.get("command"))))
    lines += ["authority:", f"  validated: {'true' if validated else 'false'}",
              f"  scope: {scope}", f"  confidence: {case.get('confidence', 'medium')}"]
    if validated and kind == "internal_experience":
        lines += ["validation:", "  method: deterministic_replay",
                  f'  command: "{case["command"]}"', "  result: pass",
                  f"  at: {case['captured_at']}"]
    return "\n".join(lines)


CASES = [
    {"name": "web source", "kind": "web", "ref": "https://example.test/post",
     "extrait": "The cache stays warm for 30 seconds.",
     "captured_at": "2026-08-16", "derived_from": "web-source",
     "confidence": "low", "expected_validated": False},
    {"name": "owner decision", "kind": "user_decision",
     "ref": "the owner, 2026-08-16: retain BM25", "captured_at": "2026-08-16",
     "extrait": "Retain BM25.", "scope": "project", "confidence": "high",
     "expected_validated": True},
    {"name": "reproducible internal experience", "kind": "internal_experience",
     "ref": "tests/golden_recall.py", "captured_at": "2026-08-16",
     "extrait": "P@1 0.67 · P@3 0.87 · MRR 0.77",
     "command": "python3 tests/golden_recall.py --check",
     "confidence": "high", "expected_validated": True},
    {"name": "unknown origin", "kind": "unknown", "captured_at": "2026-08-16",
     "confidence": "low", "expected_validated": False},
    {"name": "internal experience without replay", "kind": "internal_experience",
     "ref": "observed in a session", "captured_at": "2026-08-16",
     "extrait": "The hook refused the commit without printing anything.",
     "confidence": "medium", "expected_validated": False},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--sans-provenance", action="store_true",
                        help="SABOTAGE: omit provenance")
    parser.add_argument("--sans-extrait", action="store_true",
                        help="SABOTAGE: name the source without quoting it")
    args = parser.parse_args()
    write = not args.sans_provenance
    excerpt = not args.sans_extrait
    title = ("  SABOTAGE: no provenance" if not write else
             "  SABOTAGE: no excerpt" if not excerpt else "")
    print(f"Distiller contract — {len(CASES)} sources{title}\n")
    failures = 0
    for case in CASES:
        block = bloc_provenance(case, write, excerpt)
        faults = controler(block) if block else ["no provenance block produced"]
        if block and case["kind"] != "unknown" and 'extrait: "' not in block:
            faults.append("E1: the named source has no exact excerpt")
        validated = "validated: true" in block
        if validated is not case["expected_validated"]:
            faults.append(f"validated={validated}, expected {case['expected_validated']}")
        failures += bool(faults)
        print(f"  {'PASS' if not faults else 'FAIL'} {case['name']:36} "
              f"{case['kind']:22} validated={str(validated).lower()}")
        for fault in faults:
            print(f"        {fault}")
    print(f"\n  {len(CASES) - failures}/{len(CASES)} sources produce a valid block")
    if args.check and failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
