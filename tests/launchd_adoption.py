#!/usr/bin/env python3
"""launchd_adoption.py — adopting a legacy job needs proof AND permission.

THE CONTRACT UNDER TEST (cbrain/adopt-launchd.sh):

    TECHNICAL CONCORDANCE OBSERVED
  + EXPLICIT HUMAN AUTHORISATION
  = OWNERSHIP RECORDED FROM NOW ON.

Neither half substitutes for the other, and the order matters: the proofs are
established BEFORE anyone is asked. A confirmation is permission to act, not
proof of what is being acted upon — asking first and checking after is how an
identity gets handed over by someone who was never shown what they were giving.

WHAT IS PROVED HERE. That the two concordances are required, that a failure of
either refuses without even offering the question, that a refusal writes
nothing, that a decline writes nothing, and that adoption never unloads
anything to "prove" itself.

WHAT IS NOT. That the real `launchctl print` reports a program and a path the
way our fake does. Its shape is transcribed from the man page, not captured.
Until that is measured on a domain that is not the author's, every green here
carries that assumption — see tests/_fake_launchd.py.

Run: python3 tests/launchd_adoption.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fake_launchd import FAKE   # one definition of the fake domain

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADOPT = os.path.join(ROOT, "cbrain", "adopt-launchd.sh")
LIB = os.path.join(ROOT, "cbrain", "launchd-lib.sh")

fails = []


def ok(label):
    print("  OK   %s" % label)


def ko(label, detail=""):
    print("  FAIL %s%s" % (label, ("  -- " + detail) if detail else ""))
    fails.append(label)


class Bench:
    """One synthetic machine, with a HOME of its own and no real launchctl."""

    def __init__(self, script=None, tpl_dir=None):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="cbrain-adopt."))
        self.home = os.path.join(self.tmp, "home")
        self.bin = os.path.join(self.tmp, "bin")
        self.cb = os.path.join(self.home, ".c-brain")
        self.agents = os.path.join(self.home, "Library", "LaunchAgents")
        for d in (self.bin, self.agents, os.path.join(self.cb, "state")):
            os.makedirs(d)
        fake = os.path.join(self.bin, "launchctl")
        with open(fake, "w") as f:
            f.write(FAKE)
        os.chmod(fake, 0o755)
        self.reg = os.path.join(self.tmp, "registry")
        self.log = os.path.join(self.tmp, "log")
        open(self.reg, "w").close()
        open(self.log, "w").close()
        self.script = script or ADOPT
        self.tpl_dir = tpl_dir or os.path.join(ROOT, "hooks")
        self.record = os.path.join(self.cb, "state", "launchd-owned")
        self.audit = os.path.join(self.cb, "state", "launchd-adoptions.log")

    # what this installation WOULD write for this HOME
    def rendered(self, label):
        tpl = os.path.join(self.tpl_dir,
                           "%s.plist.template" % label)
        with open(tpl) as f:
            return f.read().replace("__HOME__", self.home)

    def program(self, label):
        block = re.search(r"<key>ProgramArguments</key>\s*<array>(.*?)</array>",
                          self.rendered(label), re.S)
        return re.findall(r"<string>([^<]*)</string>", block.group(1))[-1]

    def plist_path(self, label):
        return os.path.join(self.agents, label + ".plist")

    def put_plist(self, label, text=None):
        p = self.plist_path(label)
        with open(p, "w") as f:
            f.write(text if text is not None else self.rendered(label))
        return p

    def register(self, label, program=None, path=None):
        with open(self.reg, "a") as f:
            f.write("%s\t%s\t%s\n" % (label, program or "", path or ""))

    def env(self):
        e = dict(os.environ)
        e.update({"HOME": self.home, "CB": self.cb,
                  "PATH": self.bin + os.pathsep + e["PATH"],
                  "FAKE_LOG": self.log, "FAKE_REG": self.reg})
        return e

    def adopt(self, label, answer=""):
        r = subprocess.run(["bash", self.script, label], input=answer,
                           capture_output=True, text=True, env=self.env())
        return r.returncode, r.stdout + r.stderr

    def call_lib(self, func, label, plist):
        script = '. "%s"\n%s "%s" "%s"\nexit $?\n' % (LIB, func, label, plist)
        r = subprocess.run(["bash", "-c", script], capture_output=True,
                           text=True, env=self.env())
        return r.returncode, r.stdout + r.stderr

    @property
    def invocations(self):
        with open(self.log) as f:
            return [l.strip() for l in f if l.strip()]

    def mutations(self):
        return [i for i in self.invocations
                if re.match(r"^(unload|load|bootout|remove|disable|stop)\b", i)]

    def recorded(self):
        if not os.path.exists(self.record):
            return None
        with open(self.record) as f:
            return [l.strip() for l in f if l.strip()]

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


LABEL = "com.claudebrain.resume"
OTHER = "com.claudebrain.machiniste"


def refusal(name, build, label=LABEL, answer="y\n", expect_rc=3):
    """A refusal writes nothing, mutates nothing, and never asks the question."""
    b = Bench()
    try:
        build(b)
        rc, out = b.adopt(label, answer)
        if rc == expect_rc:
            ok("%s: refused (rc=%d)" % (name, rc))
        else:
            ko("%s: wrong outcome" % name,
               "rc=%d -- %s" % (rc, out.strip().splitlines()[-1] if out.strip() else ""))
        if "Adopt " not in out:
            ok("  the question was never asked")
        else:
            ko("  it asked for confirmation before the proofs held")
        if b.recorded() is None and not os.path.exists(b.audit):
            ok("  nothing was recorded")
        else:
            ko("  a refusal wrote to the record", str(b.recorded()))
        if not b.mutations():
            ok("  no launchd mutation")
        else:
            ko("  a refusal touched launchd", str(b.invocations))
    finally:
        b.close()


def case_adopted():
    b = Bench()
    try:
        b.put_plist(LABEL)
        b.register(LABEL, b.program(LABEL), b.plist_path(LABEL))
        rc, out = b.adopt(LABEL, "y\n")
        if rc == 0 and b.recorded() == [LABEL]:
            ok("live matches + plist matches + confirmation: adopted")
        else:
            ko("a legitimate adoption was refused -- the gate is a wall",
               "rc=%d -- %s" % (rc, out.strip()))
        for piece, what in ((LABEL, "the label"),
                            (b.program(LABEL), "the live program"),
                            (b.plist_path(LABEL), "the plist path"),
                            ("plist_normalise.py", "the template match"),
                            (b.cb, "the installation asking")):
            if piece in out:
                ok("  evidence shown: %s" % what)
            else:
                ko("  evidence NOT shown: %s" % what)
        if not b.mutations():
            ok("  and nothing was unloaded or reloaded to prove it")
        else:
            ko("  adoption mutated launchd to justify itself", str(b.invocations))
        if os.path.exists(b.audit):
            with open(b.audit) as f:
                line = f.read().strip()
            if LABEL in line and "adopted" in line:
                ok("  an audit line was written")
            else:
                ko("  the audit line does not say what happened", line)
        else:
            ko("  no audit trail was written")
        # the guard must now let the ordinary operation through
        rc2, _ = b.call_lib("cb_launchd_owned", LABEL, "")
        if rc2 == 0:
            ok("  state/launchd-owned now recognises the Label as ours")
        else:
            ko("  the record was written but the guard does not read it")
    finally:
        b.close()


def case_declined():
    b = Bench()
    try:
        b.put_plist(LABEL)
        b.register(LABEL, b.program(LABEL), b.plist_path(LABEL))
        rc, out = b.adopt(LABEL, "n\n")
        if rc == 1 and b.recorded() is None and not os.path.exists(b.audit):
            ok("proofs good, human declines: nothing changed")
        else:
            ko("a decline left a trace", "rc=%d, record=%s" % (rc, b.recorded()))
        if not b.mutations():
            ok("  and launchd was not touched")
        else:
            ko("  a decline touched launchd", str(b.invocations))
    finally:
        b.close()


def case_no_input():
    b = Bench()
    try:
        b.put_plist(LABEL)
        b.register(LABEL, b.program(LABEL), b.plist_path(LABEL))
        rc, out = b.adopt(LABEL, "")
        if rc == 1 and b.recorded() is None:
            ok("no answer at all: treated as a decline")
        else:
            ko("silence was read as consent", "rc=%d, record=%s" % (rc, b.recorded()))
    finally:
        b.close()


def case_adopt_one_mutate_another():
    b = Bench()
    try:
        b.put_plist(LABEL)
        b.register(LABEL, b.program(LABEL), b.plist_path(LABEL))
        b.register(OTHER, "/opt/elsewhere/job.py", "/opt/elsewhere/other.plist")
        rc, _ = b.adopt(LABEL, "y\n")
        if rc != 0:
            ko("setup: the first adoption did not go through")
            return
        rc2, out2 = b.call_lib("cb_launchd_install", OTHER, b.plist_path(OTHER))
        if rc2 == 3 and not [i for i in b.invocations if i.startswith("unload")]:
            ok("adopting one Label grants nothing on another: refused")
        else:
            ko("adoption of one Label leaked to another",
               "rc=%d, log=%s" % (rc2, b.invocations))
        if b.recorded() == [LABEL]:
            ok("  and the record still holds only the adopted Label")
        else:
            ko("  the record grew", str(b.recorded()))
    finally:
        b.close()


def case_no_automatic_caller():
    """An adoption a machine can trigger on its own is not an adoption."""
    callers = []
    for rel in ("install.sh", "uninstall.sh", "cbrain/update.sh",
                "cbrain/check_update.py", "bin/brain", "sync.sh"):
        p = os.path.join(ROOT, rel)
        if os.path.exists(p) and "adopt-launchd" in open(p, errors="replace").read():
            callers.append(rel)
    if not callers:
        ok("no install / update / uninstall path calls the adoption command")
    else:
        ko("an automatic path can trigger adoption", ", ".join(callers))


def case_sabotage_detects():
    """Neutralise proof B in a COPY, and the mismatched plist must be adopted.

    Without this, every refusal above could come from a bench that refuses
    everything, and the greens would prove nothing.
    """
    tmp = tempfile.mkdtemp(prefix="cbrain-adopt-sab.")
    try:
        pkg = os.path.join(tmp, "pkg")
        shutil.copytree(os.path.join(ROOT, "cbrain"), os.path.join(pkg, "cbrain"))
        os.makedirs(os.path.join(pkg, "hooks"))
        for f in os.listdir(os.path.join(ROOT, "hooks")):
            if f.endswith(".plist.template"):
                shutil.copy(os.path.join(ROOT, "hooks", f),
                            os.path.join(pkg, "hooks", f))
        doctored = os.path.join(pkg, "cbrain", "adopt-launchd.sh")
        src = open(doctored).read()
        src = src.replace('if ! diff -q <(python3 "$NORM" < "$PLIST") \\',
                          'if false && ! diff -q <(python3 "$NORM" < "$PLIST") \\')
        open(doctored, "w").write(src)
        b = Bench(script=doctored, tpl_dir=os.path.join(pkg, "hooks"))
        try:
            b.put_plist(LABEL, text="<plist>not ours at all</plist>\n")
            b.register(LABEL, b.program(LABEL), b.plist_path(LABEL))
            rc, out = b.adopt(LABEL, "y\n")
            if rc == 0:
                ok("sabotage: with proof B neutralised the mismatched plist IS "
                   "adopted -- the bench can go red")
            else:
                ko("sabotage did not reproduce the defect -- this bench proves "
                   "nothing", "rc=%d" % rc)
        finally:
            b.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("== launchd_adoption -- concordance AND authorisation, never one alone ==")
    print("   The launchd domain is a text file. No real launchctl is invoked.")

    print("\n> what is adopted")
    case_adopted()

    print("\n> what is refused, before anyone is asked")
    refusal("live matches, plist differs",
            lambda b: (b.put_plist(LABEL, "<plist>something else</plist>\n"),
                       b.register(LABEL, b.program(LABEL), b.plist_path(LABEL))))
    refusal("plist matches, live points elsewhere",
            lambda b: (b.put_plist(LABEL),
                       b.register(LABEL, "/opt/elsewhere/job.py",
                                  b.plist_path(LABEL))))
    refusal("plist matches, live loaded from another file",
            lambda b: (b.put_plist(LABEL),
                       b.register(LABEL, b.program(LABEL),
                                  "/Library/LaunchDaemons/com.claudebrain.resume.plist")))
    refusal("the Label alone is identical",
            lambda b: (b.put_plist(LABEL, "<plist>foreign</plist>\n"),
                       b.register(LABEL, "/opt/elsewhere/job.py",
                                  "/opt/elsewhere/other.plist")))
    refusal("the com.claudebrain.* prefix alone",
            lambda b: b.register("com.claudebrain.somebodyelse",
                                 "/opt/elsewhere/job.py", "/opt/x.plist"),
            label="com.claudebrain.somebodyelse")
    refusal("a confirmation offered with no proofs at all",
            lambda b: None)

    print("\n> what is not written")
    case_declined()
    case_no_input()

    print("\n> what adoption does not grant")
    case_adopt_one_mutate_another()
    case_no_automatic_caller()

    print("\n> counter-proof")
    case_sabotage_detects()

    print("\n" + "-" * 74)
    if fails:
        print("RED -- %d failure(s)" % len(fails))
        for f in fails:
            print("   . %s" % f)
        return 1
    print("GREEN -- proof before permission, and permission before the record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
