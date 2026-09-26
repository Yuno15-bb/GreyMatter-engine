#!/usr/bin/env python3
"""launchd_template_migration.py — a semantic change to a launchd template is a
RELEASE DECISION, not a diff.

WHY THIS GUARD EXISTS. Fixing the ownership hole (A6.1-A6.3) opened a window
nobody chose. A machine installed before `state/launchd-owned` existed can only
be adopted while its plist still matches the template this installation renders.
The comparison uses the normal form in `cbrain/plist_normalise.py`, so prose and
indentation drift freely — MEASURED on 2026-08-20: rewording a comment, deleting
a whole comment, and retabbing the file all still adopt. A real configuration
change does not: `StartInterval` 300 -> 600 refuses, and so does removing a key.

So the first release that changes a template SEMANTICALLY shuts the adoption
window, for good, on every machine that has not adopted yet. That is a decision
about other people's running systems. It must be taken deliberately, and this
guard is what stops it from being taken by accident, six months from now, by
somebody editing a plist template for a good reason.

WHAT IT DOES NOT DO. It does not keep a history of published renderings — that
mechanism (option b) is deliberately NOT built: today no published change needs
it, and it would cost a compatibility surface, a template versioning policy, an
artefact to maintain per release, and its own proofs. This guard only makes sure
the decision cannot be forgotten at the moment it becomes necessary.

HOW A CHANGE IS DECLARED. `cbrain/launchd-template-baseline.json` holds, per
template, the sha256 of its normal form and the migration decision that was
taken when that form last changed. Publishing a semantic change means updating
BOTH: the hash, and the decision text saying what happens to machines that have
not adopted. Updating only the hash keeps this test red — the previous baseline
comes from `git show HEAD:`, so a stale decision is visible.

Run: python3 tests/launchd_template_migration.py
"""
import glob
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "cbrain"))
from plist_normalise import normalise   # ONE definition of "the same plist"

BASELINE = os.path.join(ROOT, "cbrain", "launchd-template-baseline.json")

fails = []
calibration_fails = []


def ok(label):
    print("  OK   %s" % label)


def ko(label, detail="", bucket=None):
    print("  FAIL %s%s" % (label, ("  -- " + detail) if detail else ""))
    (bucket if bucket is not None else fails).append(label)


def form(text):
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


# ── the rule ────────────────────────────────────────────────────────────────

def check(templates, baseline, previous):
    """templates: {name: text} · baseline/previous: {name: {sha, decision}}"""
    problems = []
    for name, text in sorted(templates.items()):
        entry = baseline.get(name)
        if entry is None:
            problems.append("%s: no baseline entry -- a launchd template must "
                            "declare its normal form" % name)
            continue
        if entry["normal_form_sha256"] != form(text):
            problems.append("%s: the baseline no longer describes the template "
                            "(edit it, and say what the change means for "
                            "machines that have not adopted)" % name)
            continue
        old = (previous or {}).get(name)
        if old and old["normal_form_sha256"] != entry["normal_form_sha256"]:
            if old.get("migration_decision") == entry.get("migration_decision"):
                problems.append("%s: a SEMANTIC change is being published and "
                                "the migration decision is unchanged -- the "
                                "adoption window closes for every machine that "
                                "has not adopted yet" % name)
    for name in sorted(baseline):
        if name not in templates:
            problems.append("%s: baseline entry for a template that no longer "
                            "exists" % name)
    return problems


# ── calibration ─────────────────────────────────────────────────────────────

TPL = ("<plist><dict>\n"
       "  <!-- a long explanation of why this job exists -->\n"
       "  <key>Label</key><string>com.claudebrain.demo</string>\n"
       "  <key>StartInterval</key><integer>300</integer>\n"
       "</dict></plist>\n")
NAME = "com.claudebrain.demo.plist.template"


def base(text, decision="none needed"):
    return {NAME: {"normal_form_sha256": form(text), "migration_decision": decision}}


def calibrate():
    print("\n> calibration -- syntax drifts freely, meaning does not")
    cases = [
        ("nothing changed", {NAME: TPL}, base(TPL), base(TPL), 0),
        ("a comment reworded",
         {NAME: TPL.replace("why this job exists", "why this job is here")},
         base(TPL), base(TPL), 0),
        ("a whole comment deleted",
         {NAME: TPL.replace("  <!-- a long explanation of why this job exists -->\n", "")},
         base(TPL), base(TPL), 0),
        ("indentation and blank lines changed",
         {NAME: TPL.replace("  ", "\t") + "\n\n"},
         base(TPL), base(TPL), 0),
        ("StartInterval changed, baseline untouched",
         {NAME: TPL.replace("300", "600")}, base(TPL), base(TPL), 1),
        ("semantic change, hash updated, decision STALE",
         {NAME: TPL.replace("300", "600")},
         base(TPL.replace("300", "600")), base(TPL), 1),
        ("semantic change, hash and decision both updated",
         {NAME: TPL.replace("300", "600")},
         base(TPL.replace("300", "600"), "legacy plists no longer adopt: the "
              "refusal names the manual procedure"),
         base(TPL), 0),
        ("a new template with no baseline entry",
         {NAME: TPL, "com.claudebrain.other.plist.template": TPL},
         base(TPL), base(TPL), 1),
        ("a baseline entry whose template is gone", {}, base(TPL), base(TPL), 1),
    ]
    for name, templates, baseline, previous, expected in cases:
        got = check(templates, baseline, previous)
        if len(got) == expected:
            ok("%s: %d problem(s)" % (name, len(got)))
        else:
            ko("%s: %d problem(s), expected %d" % (name, len(got), expected),
               "; ".join(got), bucket=calibration_fails)


# ── the verdict on the real package ─────────────────────────────────────────

def previous_baseline():
    r = subprocess.run(["git", "-C", ROOT, "show",
                        "HEAD:cbrain/launchd-template-baseline.json"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None            # first commit of the baseline: nothing to compare
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def audit():
    print("\n> the package")
    templates = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "hooks", "*.plist.template"))):
        with open(p, encoding="utf-8", errors="replace") as f:
            templates[os.path.basename(p)] = f.read()
    if not os.path.exists(BASELINE):
        ko("cbrain/launchd-template-baseline.json is missing")
        return
    with open(BASELINE) as f:
        baseline = {k: v for k, v in json.load(f).items()
                    if not k.startswith("_")}
    prev = previous_baseline()
    if prev is None:
        print("  ..   no baseline in HEAD yet -- nothing to compare against")
    prev = {k: v for k, v in (prev or {}).items() if not k.startswith("_")}
    problems = check(templates, baseline, prev)
    for p in problems:
        ko(p)
    if not problems:
        ok("%d launchd template(s), all declared, no undecided semantic change"
           % len(templates))


def main():
    print("== launchd_template_migration -- changing a job definition is a decision ==")
    calibrate()
    audit()
    print("\n" + "-" * 74)
    if calibration_fails:
        print("INSTRUMENT NOT CALIBRATED -- %d failure(s). The verdict is void."
              % len(calibration_fails))
        return 2
    if fails:
        print("RED -- %d undeclared change(s) to a launchd template" % len(fails))
        for f in fails:
            print("   . %s" % f)
        return 1
    print("GREEN -- every launchd template's normal form is declared and decided.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
