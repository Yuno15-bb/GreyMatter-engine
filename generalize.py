#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""C Brain — declarative generalization, run AFTER sync.sh has copied.

Why a script rather than hand edits: sync.sh re-copies the engine from the
living Brain on every pass. A manual fix would be silently overwritten, and the
leak would be back at the next commit. A rule replays.

Rules live in rules.json. Two families:
  · blocks       — rewriting a block of CODE (a table, a function).
  · replacements — text substitution (comments, labels, examples).

A counter dropping to 0 on an expected rule FAILS the script: it means the
source changed its wording and the rule no longer bites.

Exit 0 = generalized · Exit 1 = a rule stopped biting, or a block was not found.
"""

import base64
import binascii
import json
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RULES = ROOT / "rules.json"

# The generalization tools must not rewrite themselves. rules.json contains
# patterns that a broad JSON glob would otherwise replace inside the rule
# definition, leaving the rule apparently intact but unable to match later.
SKIP_NAMES = {"rules.json", "generalize.py", "leakcheck.py"}
PRIVATE_SALT = b"cbrain-private-markers-v1:"
WORD = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)


def private_digest(value):
    plain = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    plain = " ".join(re.findall(r"[a-z0-9]+", plain))
    return hashlib.sha256(PRIVATE_SALT + plain.encode()).hexdigest()


def rule_pattern(rule):
    """Read an ordinary pattern or an encoded source-only pattern."""
    if "pattern_b64" in rule:
        return base64.b64decode(rule["pattern_b64"], validate=True).decode("utf-8")
    return rule["pattern"]


def targets(patterns):
    """Repo files targeted by a list of globs, deduplicated and sorted."""
    seen = {}
    for g in patterns:
        for p in ROOT.glob(g):
            if (p.is_file() and ".git" not in p.parts
                    and "node_modules" not in p.parts
                    and p.name not in SKIP_NAMES):
                seen[p] = True
    return sorted(seen)


def validate(rules):
    """A malformed rule must produce a message, not a Python traceback.
    Already hit once: a substitution rule filed by mistake among the blocks —
    the script died on a KeyError, in the middle of a sync."""
    ok = True
    for r in rules.get("blocks", []):
        if "file" not in r or not ({"pattern", "pattern_b64"} & set(r)) or "replace" not in r:
            print(f"  ⛔ block '{r.get('id', '?')}' — needs file + pattern + replace"
                  f"{' (a rule with `files` belongs in replacements)' if 'files' in r else ''}")
            ok = False
        elif not valid_pattern(r):
            print(f"  ⛔ block '{r.get('id', '?')}' — invalid pattern")
            ok = False
    for r in rules.get("replacements", []):
        if "files" not in r or not ({"pattern", "pattern_b64"} & set(r)) or not ({"replace", "replace_map", "replace_map_b64", "replace_map_patterns"} & set(r)):
            print(f"  ⛔ substitution '{r.get('id', '?')}' — needs files + pattern + replace|replace_map")
            ok = False
        elif not valid_pattern(r):
            print(f"  ⛔ substitution '{r.get('id', '?')}' — invalid pattern")
            ok = False
    for r in rules.get("digest_replacements", []):
        if "files" not in r or not isinstance(r.get("digest_map"), dict):
            print(f"  ⛔ digest replacement '{r.get('id', '?')}' — needs files + digest_map")
            ok = False
    return ok


def valid_pattern(rule):
    if ("pattern" in rule) == ("pattern_b64" in rule):
        return False
    try:
        re.compile(rule_pattern(rule))
    except (binascii.Error, UnicodeDecodeError, ValueError, re.error):
        return False
    return True


def apply_blocks(rules, report):
    ok = True
    for rule in rules:
        path = ROOT / rule["file"]
        if not path.is_file():
            print(f"  ⛔ {rule['id']} — file missing: {rule['file']}")
            ok = False
            continue
        text = path.read_text(encoding="utf-8")
        new, n = re.subn(rule_pattern(rule), lambda _m: rule["replace"], text,
                         flags=re.S)
        if n == 0:
            print(f"  ⛔ {rule['id']} — block NOT FOUND in {rule['file']}")
            print("       the source changed shape; the rule must be updated")
            ok = False
            continue
        path.write_text(new, encoding="utf-8")
        report.append((rule["id"], n, rule["file"], rule["why"]))
    return ok


def apply_replacements(rules, report):
    ok = True
    for rule in rules:
        total = 0
        touched = []
        rx = re.compile(rule_pattern(rule))
        for path in targets(rule["files"]):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "replace_map_patterns" in rule:
                cases = [(re.compile(pattern), value)
                         for pattern, value in rule["replace_map_patterns"]]
                def sub(m):
                    return next((value for pattern, value in cases
                                 if pattern.fullmatch(m.group(0))), m.group(0))
                new, n = rx.subn(sub, text)
            elif "replace_map" in rule or "replace_map_b64" in rule:
                # Several phrasings around the same name: each gets its own
                # replacement, otherwise the sentence comes out lopsided.
                mapping = rule.get("replace_map")
                if mapping is None:
                    mapping = {base64.b64decode(key, validate=True).decode("utf-8"): value
                               for key, value in rule["replace_map_b64"].items()}
                def sub(m):
                    return mapping.get(m.group(0), m.group(0))
                new, n = rx.subn(sub, text)
            else:
                new, n = rx.subn(rule["replace"], text)
            if n:
                path.write_text(new, encoding="utf-8")
                total += n
                touched.append(path.relative_to(ROOT).as_posix())
        expect = rule.get("expect", 1)
        if total < expect:
            print(f"  ⛔ {rule['id']} — {total} occurrence(s), {expect} expected")
            print("       a falling counter = the source changed, NOT good news")
            ok = False
            continue
        report.append((rule["id"], total, ", ".join(touched), rule["why"]))
    return ok


def apply_digest_replacements(rules, report):
    """Replace private names using fingerprints, without storing names in rules.json."""
    ok = True
    for rule in rules:
        total = 0
        touched = []
        for path in targets(rule["files"]):
            source = path.read_text(encoding="utf-8", errors="replace")
            words = list(WORD.finditer(source))
            edits = []
            i = 0
            while i < len(words):
                found = None
                for j in range(min(i + 3, len(words)), i, -1):
                    start, end = words[i].start(), words[j - 1].end()
                    replacement = rule["digest_map"].get(private_digest(source[start:end]))
                    if replacement is not None:
                        found = (start, end, replacement, j)
                        break
                if found is None:
                    i += 1
                else:
                    edits.append(found)
                    i = found[3]
            if edits:
                updated = source
                for start, end, replacement, _ in reversed(edits):
                    updated = updated[:start] + replacement + updated[end:]
                path.write_text(updated, encoding="utf-8")
                total += len(edits)
                touched.append(path.relative_to(ROOT).as_posix())
        if total < rule.get("expect", 1):
            print(f"  ⛔ {rule['id']} — {total} occurrence(s), {rule.get('expect', 1)} expected")
            ok = False
        else:
            report.append((rule["id"], total, ", ".join(touched), rule["why"]))
    return ok


def check_json_still_valid():
    """A rule removing a block from a .json can leave an orphan comma.
    The file is still "text" — the error only surfaces at the first `npm` or the
    first `json.load`, far from here. We check right away."""
    broken = []
    for path in ROOT.rglob("*.json"):
        if {".git", "node_modules"} & set(path.relative_to(ROOT).parts):
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            broken.append((path.relative_to(ROOT).as_posix(), e))
    for rel, e in broken:
        print(f"  ⛔ {rel} — invalid JSON after generalization: {e}")
    return not broken


def check_python_still_compiles():
    """Catch replacements that break Python syntax before shipping a package."""
    broken = []
    for path in ROOT.rglob("*.py"):
        if {".git", "node_modules", "__pycache__", ".venv"} & set(path.relative_to(ROOT).parts):
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as error:
            broken.append((path.relative_to(ROOT).as_posix(), error))
    for rel, error in broken:
        print(f"  ⛔ {rel}:{error.lineno} — Python invalid after generalization: {error.msg}")
        if error.text:
            print(f"       {error.text.strip()}")
    return not broken


def main():
    if not RULES.is_file():
        sys.exit(f"❌ rules.json not found ({RULES})")
    rules = json.loads(RULES.read_text(encoding="utf-8"))

    if not validate(rules):
        print("\n⛔ malformed rules.json — nothing was applied.")
        return 1

    report = []
    ok = apply_blocks(rules.get("blocks", []), report)
    ok = apply_replacements(rules.get("replacements", []), report) and ok
    ok = apply_digest_replacements(rules.get("digest_replacements", []), report) and ok
    ok = check_json_still_valid() and ok
    ok = check_python_still_compiles() and ok

    print(f"🧹 Generalization — {len(report)} rule(s) applied, "
          f"{sum(r[1] for r in report)} replacement(s)\n")
    for rid, n, where, _why in report:
        print(f"   {n:>4}×  {rid:<28} {where}")

    if not ok:
        print("\n⛔ FAILED — at least one rule stopped biting. Nothing may ship as is.")
        return 1

    print("\n✅ Generalized. Now check: python3 leakcheck.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
