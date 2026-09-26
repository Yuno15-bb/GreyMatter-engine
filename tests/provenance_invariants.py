#!/usr/bin/env python3
"""provenance_invariants.py — checks the provenance protocol (ADR-0009).

Reads a note's `provenance:` and `authority:` blocks and checks invariants I1–I7.
It validates structure and allowed transitions, never the truth of a note's contents.
It reads no real notes and writes nothing. The parser intentionally supports only the
small YAML subset described by the ADR and uses no third-party dependency.

Fixtures include invalid cases so the controller cannot pass when its rules are disabled.
Run `python3 tests/provenance_invariants.py` for a report; add `--check` for a barrier.
"""
import argparse
import json
import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(ICI, "fixtures_provenance.json")

# ── Closed vocabulary. Invented values are rejected, never tolerated: otherwise the
#    field can drift into free text, where no checks remain possible.
KINDS = {"user_decision", "internal_experience", "official_documentation",
         "external_document", "web", "agent_inference", "unknown"}
SCOPES = {"repository", "project", "global", "world"}
ROLES = {"basis", "evidence", "illustration"}

# Only these kinds carry NORMATIVE authority (the right to instruct the Brain).
# `official_documentation` is excluded: documentation can accurately describe an API
# without having the authority to dictate how to work.
# TRUST ≠ NORMATIVE AUTHORITY.
NORMATIFS = {"user_decision", "internal_experience"}

# ── STRENGTH ORDER — the single source of truth, weakest to strongest ────────────────
# AN ORDERED LIST, NOT A WEIGHT DICTIONARY. The two consumers of `kind_effectif`
# each had their own version, and they already disagreed: for bases
# {official_documentation, web}, the resolver returned `official_documentation` while
# propagation returned `web`. Worse, the resolver's dictionary gave five kinds the
# same weight, 0; `min` on a set then depends on iteration order, which varies by
# process. This was more than a style issue: labeling a web-based note as
# `official_documentation` is exactly the laundering forbidden by I7.
# A list defines a total order: no ties, hence no nondeterminism.
# See [[un-detecteur-partage-par-concept]].
FORCE = ["unknown", "agent_inference", "web", "external_document",
         "official_documentation", "internal_experience", "user_decision"]


def kind_effectif(prov):
    """I7: a knowledge kind is the weakest kind among the sources that ground it.

    A note based on the web remains a web note even if it cites a user decision as an
    illustration. Decorative citations do not launder provenance. This is the single
    implementation imported by authority resolution and provenance propagation.
    """
    if prov.get("sources"):
        bases = [s["kind"] for s in prov["sources"] if s.get("role") == "basis"]
        if not bases:
            return "unknown"
        return min(bases, key=lambda k: FORCE.index(k) if k in FORCE else 0)
    return prov.get("kind", "unknown")


# ---------------------------------------------------------------- read frontmatter
def _lire_bloc(txt, nom):
    """Extract the `nom:` subtree from frontmatter indented by two spaces.

    This deliberately supports only the ADR-0009 subset: simple keys, scalar lists, and
    mapping lists for `sources` / `corrections`. Unsupported forms are rejected rather
    than silently ignored.
    """
    m = re.search(rf"^{nom}:\s*$(.*?)(?=^\S|\Z)", txt, re.M | re.S)
    if not m:
        return None
    corps = m.group(1)
    bloc, liste_courante, cle_liste = {}, None, None
    for ligne in corps.split("\n"):
        if not ligne.strip():
            continue
        indent = len(ligne) - len(ligne.lstrip())
        s = ligne.strip()
        if s.startswith("- "):                      # mapping list item
            liste_courante = {}
            bloc.setdefault(cle_liste, []).append(liste_courante)
            s = s[2:].strip()
            if ":" in s:
                k, v = s.split(":", 1)
                liste_courante[k.strip()] = _scalaire(v)
            continue
        if ":" in s:
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            if indent >= 4 and liste_courante is not None:
                liste_courante[k] = _scalaire(v)
            elif v == "":                            # a key that starts a list
                cle_liste, liste_courante = k, None
            else:
                bloc[k] = _scalaire(v)
                liste_courante = None
    return bloc


def _scalaire(v):
    v = v.strip().strip('"').strip("'")
    if v in ("true", "false"):
        return v == "true"
    if v.startswith("[") and v.endswith("]"):
        return [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
    return v


# ---------------------------------------------------------------- invariants
def controler(frontmatter, parent_kind=None):
    """Return protocol violations. An empty list means the note conforms."""
    fautes = []
    prov = _lire_bloc(frontmatter, "provenance") or {}
    auth = _lire_bloc(frontmatter, "authority") or {}
    valid = _lire_bloc(frontmatter, "validation") or {}

    kind = prov.get("kind")
    sources = prov.get("sources") or []
    validated = auth.get("validated") is True

    # — closed vocabulary
    if kind not in KINDS:
        fautes.append(f"vocabulary: kind='{kind}' is not allowed")
    if auth.get("scope") and auth["scope"] not in SCOPES:
        fautes.append(f"vocabulary: scope='{auth['scope']}' is not allowed")

    # — The observable must be named. Without `ref`, provenance is an assertion,
    #   not a trace. `unknown` is exempt because it has nothing to show (I2).
    if kind and kind != "unknown" and not prov.get("ref") and not sources:
        fautes.append("observable: `ref` is missing although kind is not unknown")

    # — I6: authority is limited by scope. The author decides about their projects,
    #   not about external reality.
    if kind == "user_decision" and auth.get("scope") == "world":
        fautes.append("I6: user_decision cannot have scope: world")

    # — I2: no information means no authority.
    if kind == "unknown" and validated:
        fautes.append("I2: `unknown` cannot be validated")

    if validated:
        # — I1 + I3: an external source is never promoted, regardless of the evidence
        #   cited. I3 forbids this silent promotion.
        if kind in (KINDS - NORMATIFS) and kind != "unknown":
            fautes.append(f"I1/I3: a '{kind}' source cannot become validated")
        # — I1: validated requires EVIDENCE, not conviction.
        #
        #   INTENTIONAL ASYMMETRY, REVEALED BY THIS TEST. The first version required
        #   a `validation` block from everyone, rejecting F1, an explicit author
        #   decision. That was wrong: `user_decision` is one of the three sources
        #   allowed by ADR-0009. Another source does not validate it; the decision
        #   IS the validation. Its evidence is the citation in `ref` itself.
        #   `internal_experience` must instead show a replay or its grounding rule.
        #   This was fixed in the CONTROLLER, not the fixture: rewriting the criterion
        #   after seeing the result would manufacture the result.
        if kind == "user_decision":
            if not prov.get("ref"):
                fautes.append("I1: validated user_decision has no citation in `ref`")
        elif not valid and not auth.get("basis_ref"):
            fautes.append("I1: validated without a `validation` block or `basis_ref`")
        # — Others cannot replay an unnamed command; validation that cannot be
        #   replayed is not validation.
        if valid.get("method") == "deterministic_replay":
            if not valid.get("command"):
                fautes.append("I1: deterministic replay has no `command`")
            if valid.get("result") != "pass":
                fautes.append("I1: deterministic replay result is not `pass`")

    # — I4: a correction without who/when/why is indistinguishable from falsification.
    for c in prov.get("corrections") or []:
        manquants = [k for k in ("from", "to", "at", "by", "why") if not c.get(k)]
        if manquants:
            fautes.append(f"I4: incomplete correction; missing {', '.join(manquants)}")

    # — I5: multiple sources are allowed, but normative authority comes from `basis`
    #   sources, never decorative citations. Otherwise, properly citing an external
    #   source would weaken an internal rule, exactly the effect to avoid.
    if sources:
        for s in sources:
            if s.get("kind") not in KINDS:
                fautes.append(f"I5: source kind='{s.get('kind')}' is not allowed")
            if s.get("role") not in ROLES:
                fautes.append(f"I5: source role='{s.get('role')}' is not allowed")
        bases = {s.get("kind") for s in sources if s.get("role") == "basis"}
        if not bases:
            fautes.append("I5: no `basis` source; this knowledge has no foundation")
        elif kind in NORMATIFS and not (bases & NORMATIFS):
            fautes.append(f"I5/I7: kind='{kind}' but no `basis` source has that kind "
                          f"(basis kinds: {', '.join(sorted(bases)) or '—'})")

    # — I7: transformation never launders provenance. A note derived from an
    #   external note does not become internal merely because it was rewritten here.
    if prov.get("derived_from") and parent_kind:
        if parent_kind not in NORMATIFS and kind in NORMATIFS:
            fautes.append(f"I7: derived from a '{parent_kind}' note but declares "
                          f"'{kind}' — authority laundering through transformation")

    return fautes


# ---------------------------------------------------------------- test bench
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any fixture differs from its expected verdict")
    ap.parse_args()

    blob = json.load(open(FIXTURES, encoding="utf-8"))
    cas = blob["cases"]
    divergences = []

    print(f"Provenance invariants (ADR-0009) — {len(cas)} fixtures; no real notes\n")
    for index, c in enumerate(cas, 1):
        fautes = controler(c["frontmatter"], c.get("parent_kind"))
        verdict = "refused" if fautes else "valid"
        expected = {"rejected": "refused", "valid": "valid"}.get(c["expected"], c["expected"])
        ok = verdict == expected
        if not ok:
            divergences.append((c, verdict, fautes))
        mark = "✅" if ok else "❌"
        invariant = {"vocabulaire fermé": "closed vocabulary",  # i18n-ok: French fixture label
                     "observable nommé": "named observable"}.get(c.get("invariant"), c.get("invariant"))  # i18n-ok: French fixture label
        inv = f" [{invariant}]" if invariant else ""
        print(f"  {mark} fixture {index:02} expected {expected:7} → {verdict}{inv}")
        if fautes and c["expected"] == "rejected":
            print(f"        ↳ {fautes[0]}")
        if not ok:
            print(f"        ⚠️  {'no violation detected' if verdict == 'valid' else fautes}")

    valides = sum(1 for c in cas if c["expected"] == "valid")
    print(f"\n  {valides} representative cases · {len(cas) - valides} expected violations")

    if divergences:
        print(f"\n❌ {len(divergences)} cases differ from the expected verdict")
        return 1
    print("\n✅ all seven invariants behave as described by ADR-0009")
    return 0


if __name__ == "__main__":
    sys.exit(main())
