#!/usr/bin/env python3
"""launchd_ownership.py — may this installer touch a launchd job it did not create?

THE INVARIANT:

    Before mutating an EXISTING launchd service, the installer must demonstrate
    that the identity it is about to touch belongs to THIS installation.

    A plist on disk does not demonstrate it. $HOME does not demonstrate it. The
    Label alone does not demonstrate it. The live launchd registry and the file
    on disk are two different things, and only the registry decides who runs.

WHY THIS FILE EXISTS. On 2026-08-18 a test install running under a throwaway
$HOME took over the author's jobs. `launchctl` indexes by Label inside the
per-user domain (gui/<uid>), not by $HOME and not by the path of the plist, so
`launchctl unload <path>` frees whatever is registered under the Label written
INSIDE that file — including a job another installation loaded from a different
directory. The plists on the author's disk never changed: the substitution was
invisible to ls, cat and shasum, and visible only through the live registry.
About 28 hours of the author's `com.claudebrain.resume` and `.machiniste` ran
somebody else's code, and nothing said so.

THE MECHANISM IS STILL IN THE PRODUCT: install.sh unloads unconditionally, and
so does uninstall.sh.

WHAT THIS FILE IS, AND WHAT IT IS NOT. It is STATIC. It reads shell sources and
never invokes launchctl, never writes a plist, never touches a running job —
because the dynamic proof is exactly the experiment that caused the incident,
and it must not be run again until the guard exists. So it cannot prove that a
guard WORKS at runtime; it proves only that every mutation site is covered by
one, and that the guard is not a file-existence test wearing a guard's name.
The runtime half belongs to a later step, run outside the author's domain.

IT IS EXPECTED TO FAIL TODAY. Nothing in the package implements the guard yet.
A green run here would mean the detector is broken, which is why the
calibration section runs first and is reported separately: an instrument states
its own calibration before it delivers a verdict.

Run:
  python3 tests/launchd_ownership.py
"""
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
# `--root` points the audit at a COPY of the package. It is what makes the green
# half reachable without editing the real installer: a check that can only ever
# be red is a wall, not an instrument -- the same reason update_ownership.py
# keeps a non-regression case next to its refusals.
for _i, _a in enumerate(sys.argv):
    if _a == "--root" and _i + 1 < len(sys.argv):
        ROOT = Path(sys.argv[_i + 1]).resolve()

# The name this contract nominates for the guard. It does not exist yet; naming
# it is what makes the check falsifiable rather than a matter of taste.
GUARD = "cb_launchd_owned"

# Verbs that take an identity AWAY from whoever currently holds it. These are
# the ones that require proof of ownership.
MUTATION_VERBS = ("unload", "bootout", "remove", "disable", "stop", "kickstart")

# Verbs that CLAIM an identity. A bare claim is believed to be refused when the
# Label is already held — believed, not measured here — so they are reported,
# not asserted on. The theft in the incident needed the unload first.
CLAIM_VERBS = ("load", "bootstrap", "enable")

# A guard body must consult a RECORDED FACT of ownership, the way the engine
# gate already does with state/engine-managed (see tests/update_ownership.py:
# "There is nothing left to infer"). These are the tokens that count as one.
OWNERSHIP_FACTS = ("launchd-owned", "engine-managed", "MANIFEST", "manifest.txt")

# Tests that only establish that a file is there. The incident is precisely a
# case where the file was there, correct, and owned by somebody else.
EXISTENCE_ONLY = re.compile(r"^\s*(\[\[?|test)\s+-[efLrsd]\s")

SHELL_SOURCES = ["install.sh", "uninstall.sh", "sync.sh", "publish.sh"]

fails = []
calibration_fails = []


def ok(label):
    print("  OK   %s" % label)


def ko(label, detail="", bucket=None):
    print("  FAIL %s%s" % (label, ("  -- " + detail) if detail else ""))
    (bucket if bucket is not None else fails).append(label)


def note(label):
    print("  ..   %s" % label)


# ── the detector ────────────────────────────────────────────────────────────

def _sites(text, verbs):
    """Every `launchctl <verb>` in the text, with the line it sits on."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.split("#", 1)[0]
        for m in re.finditer(r"\blaunchctl\s+(?:-\S+\s+)*([a-z]+)", stripped):
            if m.group(1) in verbs:
                out.append((i, m.group(1), line.rstrip(), m.start()))
    return out


def _conditions_open_at(lines, target_line):
    """The conditions of the if/while/until/case blocks enclosing a line.

    A deliberately small shell reader: enough to answer "is this call reached
    only when something was checked first", which is the whole question. It
    tracks openers and closers, not the language.
    """
    stack = []
    for i, raw in enumerate(lines, 1):
        if i >= target_line:
            break
        line = raw.split("#", 1)[0]
        s = line.strip()
        if re.match(r"^(if|while|until)\b", s):
            stack.append(s)
        elif re.match(r"^elif\b", s) and stack:
            stack[-1] = s
        elif re.match(r"^case\b", s):
            stack.append(s)
        elif re.match(r"^(fi|done|esac)\b", s) and stack:
            stack.pop()
    return stack


def unguarded(text):
    """Mutation sites NOT covered by the named guard, with the reason."""
    lines = text.splitlines()
    bad = []
    for line_no, verb, raw, col in _sites(text, MUTATION_VERBS):
        # same line: `guard "$label" && launchctl unload ...`
        before_on_line = raw.split("#", 1)[0][:col]
        if GUARD in before_on_line:
            continue
        # enclosing blocks: `if guard "$label"; then ... unload ... fi`
        if any(GUARD in c for c in _conditions_open_at(lines, line_no)):
            continue
        bad.append((line_no, verb, raw.strip()))
    return bad


def guard_definition(text):
    """(defined, body) for the nominated guard, if this file defines it."""
    m = re.search(r"^\s*(?:function\s+)?%s\s*\(\)\s*\{" % re.escape(GUARD),
                  text, re.M)
    if not m:
        return False, ""
    body = []
    depth = 0
    for raw in text[m.start():].splitlines():
        depth += raw.count("{") - raw.count("}")
        body.append(raw)
        if depth <= 0 and len(body) > 1:
            break
    return True, "\n".join(body)


def guard_is_real(body):
    """A guard must read a recorded fact, and must not be a file test alone."""
    if not any(tok in body for tok in OWNERSHIP_FACTS):
        return False, "consults no recorded ownership fact"
    meat = [l for l in body.splitlines()[1:-1]
            if l.strip() and not l.strip().startswith("#")]
    if meat and all(EXISTENCE_ONLY.match(l) or l.strip() in ("return 0", "return 1")
                    for l in meat):
        return False, "reduces to a file-existence test"
    return True, ""


# ── calibration: the detector must go red on shapes, not on filenames ───────

FIXTURES = [
    ("bare unload", True, '''
for t in resume machiniste; do
  out="$HOME/Library/LaunchAgents/com.claudebrain.$t.plist"
  launchctl unload "$out" 2>/dev/null || true
  launchctl load "$out"
done
'''),
    ("guard placed AFTER the unload", True, '''
launchctl unload "$out" 2>/dev/null || true
if cb_launchd_owned "$label"; then
  :
fi
'''),
    ("guard that only checks the plist exists", True, '''
if [ -f "$out" ]; then
  launchctl unload "$out"
fi
'''),
    ("a second mutation path, unguarded", True, '''
if cb_launchd_owned "$label"; then
  launchctl unload "$out"
fi
launchctl bootout "gui/$(id -u)/com.claudebrain.machiniste"
'''),
    ("guard on the same line", False, '''
cb_launchd_owned "$label" && launchctl unload "$out"
'''),
    ("guard enclosing the mutation", False, '''
if cb_launchd_owned "$label"; then
  launchctl unload "$out"
  launchctl load "$out"
fi
'''),
    # The negative control. Without it, a detector that always says "red" would
    # pass every case above and look calibrated.
    ("no launchctl at all", False, '''
sed "s|__HOME__|$HOME|g" "$tpl" > "$out"
note file "$out"
'''),
]

GUARD_FIXTURES = [
    ("guard reading the ownership record", True, '''
cb_launchd_owned() {
  grep -qxF "$1" "$CB/state/launchd-owned" 2>/dev/null
}
'''),
    ("guard that is a file test in disguise", False, '''
cb_launchd_owned() {
  [ -f "$HOME/Library/LaunchAgents/$1.plist" ]
}
'''),
    ("guard that trusts $HOME", False, '''
cb_launchd_owned() {
  case "$1" in com.claudebrain.*) return 0 ;; esac
  return 1
}
'''),
]


def calibrate():
    print("\n> calibration -- the detector reacts to SHAPE, on synthetic text")
    for name, should_flag, text in FIXTURES:
        flagged = bool(unguarded(text))
        if flagged == should_flag:
            ok("%s: %s" % (name, "flagged" if flagged else "clean"))
        else:
            ko("%s: detector said %s" % (name, "flagged" if flagged else "clean"),
               "expected %s" % ("flagged" if should_flag else "clean"),
               bucket=calibration_fails)

    print("\n> calibration -- a guard is judged on what it reads")
    for name, should_pass, text in GUARD_FIXTURES:
        defined, body = guard_definition(text)
        if not defined:
            ko("%s: the fixture's guard was not even found" % name,
               bucket=calibration_fails)
            continue
        real, why = guard_is_real(body)
        if real == should_pass:
            ok("%s: %s" % (name, "accepted" if real else "rejected (%s)" % why))
        else:
            ko("%s: judged %s" % (name, "real" if real else "fake"),
               why or "expected the opposite", bucket=calibration_fails)


# ── the verdict on the real product ─────────────────────────────────────────

def audit_product():
    print("\n> the product -- every mutation site must prove ownership first")
    seen_guard = False
    for rel in SHELL_SOURCES:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        defined, body = guard_definition(text)
        if defined:
            seen_guard = True
            real, why = guard_is_real(body)
            (ok if real else ko)("%s defines %s%s"
                                 % (rel, GUARD, "" if real else " -- " + why))
        bad = unguarded(text)
        sites = _sites(text, MUTATION_VERBS)
        if not sites:
            note("%s: no launchd mutation" % rel)
            continue
        for line_no, verb, raw in bad:
            ko("%s:%d mutates a launchd identity with no proof of ownership"
               % (rel, line_no), "%s -- %s" % (verb, raw))
        if not bad:
            ok("%s: %d mutation site(s), all guarded" % (rel, len(sites)))
    if not seen_guard:
        ko("no file defines %s: there is nothing to prove ownership with" % GUARD)


# ── what the guard will have to overcome, reported not asserted ─────────────

def observations():
    print("\n> observations -- context for the fix, not conditions of this test")
    for tpl in sorted((ROOT / "hooks").glob("*.plist.template")):
        text = tpl.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"<key>Label</key>\s*<string>([^<]+)</string>", text)
        if not m:
            continue
        label = m.group(1)
        varies = any(tok in label for tok in ("__HOME__", "__UID__", "__INSTALL"))
        note("%s: Label %s is a %s -- two installs on one machine collide"
             % (tpl.name, label, "constant" if not varies else "per-install name"))
    for rel in SHELL_SOURCES:
        p = ROOT / rel
        if not p.exists():
            continue
        for line_no, verb, raw, _ in _sites(p.read_text(encoding="utf-8",
                                                        errors="replace"),
                                            MUTATION_VERBS + CLAIM_VERBS):
            if "2>/dev/null" in raw and "|| true" in raw:
                note("%s:%d the outcome of `%s` is discarded: it cannot be "
                     "observed, let alone contested" % (rel, line_no, verb))


def main():
    print("== launchd_ownership -- an installer touches only the jobs it owns ==")
    print("   STATIC ONLY: no launchctl is invoked, no plist is written.")
    calibrate()
    audit_product()
    observations()

    print("\n" + "-" * 74)
    if calibration_fails:
        print("INSTRUMENT NOT CALIBRATED -- %d failure(s). The verdict below is void."
              % len(calibration_fails))
        return 2
    print("instrument calibrated: %d shapes, negative control clean"
          % len(FIXTURES))
    if fails:
        print("RED -- %d unguarded launchd mutation(s). Expected until the guard "
              "exists." % len(fails))
        for f in fails:
            print("   . %s" % f)
        return 1
    print("GREEN -- every launchd mutation is preceded by a proof of ownership.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
