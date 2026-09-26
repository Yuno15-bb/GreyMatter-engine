#!/usr/bin/env python3
"""An invented name proves the fingerprint matcher remains active."""

import importlib.util
import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("leakcheck", ROOT / "leakcheck.py")
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)

INVENTED_NAME = "Zorblax Quentel"
TEST_FINGERPRINTS = {"invented name": (lc.fingerprint("zorblax quentel"),)}


def check(fingerprints):
    found = {label for label, _, _ in lc.hashed_matches(
        "sample.txt", f"A note mentions {INVENTED_NAME} here.", fingerprints)}
    return "invented name" in found


def check_private_path():
    invented = "life/example-private-note"
    digest = lc.fingerprint(" ".join(lc.normalized_words(invented)))
    lc.PRIVATE_NOTE_PATH_DIGESTS.add(digest)
    try:
        found = list(lc.private_path_matches(f"See {invented}."))
        lc.PRIVATE_NOTE_PATH_DIGESTS.remove(digest)
        missed = list(lc.private_path_matches(f"See {invented}."))
        return len(found) == 1 and not missed
    finally:
        lc.PRIVATE_NOTE_PATH_DIGESTS.discard(digest)


def check_encoded_rule():
    """A decoded rule value is scanned, and removing its digest disables detection."""
    encoded = base64.b64encode(INVENTED_NAME.encode()).decode()
    rule = {"pattern_b64": encoded, "why": "An invented fixture."}
    compiled = [(label, re.compile(pattern)) for label, pattern in lc.MARKERS]
    digest = lc.fingerprint("zorblax quentel")
    values = list(lc.decoded_rule_values(rule))
    assert INVENTED_NAME in values
    lc.FINGERPRINTS["private project"].append(digest)
    try:
        found = []
        for value in values:
            lc.scan("rules.json", value, compiled, found)
    finally:
        lc.FINGERPRINTS["private project"].remove(digest)
    missed = []
    for value in values:
        lc.scan("rules.json", value, compiled, missed)
    return any(label == "private project" for _, label, _ in found) and not missed


if __name__ == "__main__":
    fingerprints = {} if "--sabotage" in sys.argv else TEST_FINGERPRINTS
    if not check(fingerprints) or not check_private_path() or not check_encoded_rule():
        print("Fingerprint check failed: the invented name was missed.")
        sys.exit(1)
    print("Fingerprint check passed.")
