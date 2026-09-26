#!/usr/bin/env python3
"""launchd_refusal.py — the named refusal, proved on a synthetic domain.

WHAT IT PROVES. `cbrain/launchd-lib.sh` refuses to touch a launchd identity it
cannot prove it owns, and refuses BEFORE the mutation rather than apologising
after. The proof is the invocation log of a launchctl we wrote ourselves: on a
refusal it must contain no `unload`, no `load`, nothing at all.

WHY A FAKE LAUNCHCTL, AND NOT A THROWAWAY $HOME. Because $HOME does not isolate
the launchd domain — that is the whole finding this chantier came from. A test
that ran the real launchctl would reach `gui/<uid>`, the author's own domain,
and would be the very experiment that took his jobs over for 28 hours. So the
domain here is a text file, and `launchctl` is a shell script on PATH. Nothing
real is registered, unloaded or booted out, on any machine, ever.

WHAT IT THEREFORE DOES NOT PROVE. That the real `launchctl print` answers the
way our fake does — its exit codes are read from the man page, not measured.
That belongs to a run outside the author's domain, and it is A6.3's problem.

Run: python3 tests/launchd_refusal.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "cbrain", "launchd-lib.sh")

fails = []


def ok(label):
    print("  OK   %s" % label)


def ko(label, detail=""):
    print("  FAIL %s%s" % (label, ("  -- " + detail) if detail else ""))
    fails.append(label)


from _fake_launchd import FAKE, PLIST   # one definition of the fake domain



class Bench:
    """One synthetic machine: a domain, a record, a log, and no real launchctl."""

    def __init__(self, registry=(), recorded=None, lib=None):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="cbrain-launchd."))
        self.bin = os.path.join(self.tmp, "bin")
        self.state = os.path.join(self.tmp, "cb", "state")
        os.makedirs(self.bin)
        os.makedirs(self.state)
        fake = os.path.join(self.bin, "launchctl")
        with open(fake, "w") as f:
            f.write(FAKE)
        os.chmod(fake, 0o755)
        self.reg = os.path.join(self.tmp, "registry")
        self.log = os.path.join(self.tmp, "log")
        with open(self.reg, "w") as f:
            f.write("".join(l + "\n" for l in registry))
        open(self.log, "w").close()
        self.record = os.path.join(self.state, "launchd-owned")
        if recorded is not None:
            with open(self.record, "w") as f:
                f.write("".join(l + "\n" for l in recorded))
        self.lib = lib or LIB

    def plist(self, label, on_disk=True):
        p = os.path.join(self.tmp, label + ".plist")
        if on_disk:
            with open(p, "w") as f:
                f.write(PLIST % (label, "/opt/whatever/job.py"))
        return p

    def call(self, func, label, plist, **env):
        script = '. "%s"\n%s "%s" "%s"\nexit $?\n' % (self.lib, func, label, plist)
        e = dict(os.environ)
        e.update({"PATH": self.bin + os.pathsep + e["PATH"],
                  "FAKE_LOG": self.log, "FAKE_REG": self.reg,
                  "CB_LAUNCHD_RECORD": self.record})
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run(["bash", "-c", script], capture_output=True,
                           text=True, env=e)
        return r.returncode, r.stdout + r.stderr

    @property
    def invocations(self):
        with open(self.log) as f:
            return [l.strip() for l in f if l.strip()]

    def recorded(self):
        if not os.path.exists(self.record):
            return None
        with open(self.record) as f:
            return [l.strip() for l in f if l.strip()]

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def mutated(b):
    return [i for i in b.invocations
            if re.match(r"^(unload|bootout|remove|disable|stop|kickstart)\b", i)]


def claimed(b):
    return [i for i in b.invocations if re.match(r"^(load|bootstrap|enable)\b", i)]


# ── the eight sabotages ─────────────────────────────────────────────────────

def case_absent_no_record():
    b = Bench(registry=[], recorded=None)
    try:
        label = "com.claudebrain.resume"
        rc, out = b.call("cb_launchd_install", label, b.plist(label))
        if rc == 0 and claimed(b) and not mutated(b):
            ok("Label absent, no record: created, and nothing was unloaded")
        else:
            ko("Label absent, no record: not the clean creation path",
               "rc=%d, log=%s" % (rc, b.invocations))
        if b.recorded() == [label]:
            ok("  and the Label is now recorded as ours")
        else:
            ko("  the record was not written after a successful load",
               str(b.recorded()))
    finally:
        b.close()


def case_present_and_recorded():
    label = "com.claudebrain.resume"
    b = Bench(registry=[label], recorded=[label])
    try:
        rc, out = b.call("cb_launchd_install", label, b.plist(label))
        if rc == 0 and mutated(b) and claimed(b):
            ok("Label present AND recorded: mutation allowed")
        else:
            ko("a legitimate reload was refused -- the guard is a wall",
               "rc=%d, log=%s" % (rc, b.invocations))
        if b.recorded() == [label]:
            ok("  and the record was not duplicated")
        else:
            ko("  the record grew a duplicate", str(b.recorded()))
    finally:
        b.close()


def refusal_case(name, registry, recorded, label, plist_on_disk=True,
                 func="cb_launchd_install"):
    b = Bench(registry=registry, recorded=recorded)
    try:
        before = b.recorded()
        rc, out = b.call(func, label, b.plist(label, on_disk=plist_on_disk))
        if rc == 3 and not mutated(b) and not claimed(b):
            ok("%s: refused BEFORE any mutation" % name)
        else:
            ko("%s: the guard let it through" % name,
               "rc=%d, log=%s" % (rc, b.invocations))
        if label in out and ("NOTHING was changed" in out or "Left alone" in out):
            ok("  refusal names the Label and says nothing was changed")
        else:
            ko("  the refusal is not named or does not say nothing changed",
               out.strip().splitlines()[0] if out.strip() else "(silent)")
        if b.recorded() == before:
            ok("  the record was not touched")
        else:
            ko("  a refusal wrote to the record", str(b.recorded()))
    finally:
        b.close()


def case_load_fails():
    label = "com.claudebrain.resume"
    b = Bench(registry=[], recorded=None)
    try:
        rc, out = b.call("cb_launchd_install", label, b.plist(label),
                         FAKE_FAIL_LOAD=1)
        if rc == 4:
            ok("load fails: reported as a failure, not swallowed")
        else:
            ko("load fails: wrong outcome", "rc=%d, out=%s" % (rc, out.strip()))
        if b.recorded() in (None, []):
            ok("  and the Label was NOT recorded as ours")
        else:
            ko("  a failed load still claimed ownership", str(b.recorded()))
        if "load of %s failed" % label in out:
            ok("  the failure is named on stderr, not hidden by 2>/dev/null")
        else:
            ko("  the failure is silent", out.strip() or "(no output)")
    finally:
        b.close()


def case_uninstall_owned():
    label = "com.claudebrain.machiniste"
    b = Bench(registry=[label], recorded=[label])
    try:
        p = b.plist(label)
        rc, out = b.call("cb_launchd_uninstall", label, p)
        if rc == 0 and mutated(b) and not os.path.exists(p) and b.recorded() == []:
            ok("uninstall of an owned Label: unloaded, removed, forgotten")
        else:
            ko("uninstall of an owned Label did not complete",
               "rc=%d, log=%s, plist=%s, record=%s"
               % (rc, b.invocations, os.path.exists(p), b.recorded()))
    finally:
        b.close()


def case_uninstall_not_owned():
    label = "com.claudebrain.resume"
    b = Bench(registry=[label], recorded=[])
    try:
        p = b.plist(label)
        rc, out = b.call("cb_launchd_uninstall", label, p)
        if rc == 3 and not mutated(b) and os.path.exists(p):
            ok("uninstall of a Label we never registered: skipped, plist kept")
        else:
            ko("the uninstaller touched a job it did not install",
               "rc=%d, log=%s, plist still there=%s"
               % (rc, b.invocations, os.path.exists(p)))
        if label in out and "Left alone" in out:
            ok("  and it says so, by name")
        else:
            ko("  the skip is silent", out.strip() or "(no output)")
    finally:
        b.close()


# ── the counter-proof: this bench must be able to go red ────────────────────

def case_sabotage_detects():
    """Neutralise the ownership check in a COPY of the library.

    Without this, every green above could come from a bench that never looks.
    The doctored guard says "mine" to everything; the refusal case must then
    fail, and the log must show the unload it was supposed to prevent.
    """
    tmp = tempfile.mkdtemp(prefix="cbrain-sabotage.")
    try:
        doctored = os.path.join(tmp, "launchd-lib.sh")
        with open(LIB) as f:
            src = f.read()
        src = src.replace('  grep -qxF "$1" "$f" 2>/dev/null\n',
                          '  return 0   # SABOTAGE: everything looks like ours\n')
        with open(doctored, "w") as f:
            f.write(src)
        label = "com.claudebrain.resume"
        b = Bench(registry=[label], recorded=[], lib=doctored)
        try:
            rc, out = b.call("cb_launchd_install", label, b.plist(label))
            if rc != 3 and mutated(b):
                ok("sabotage: with the check neutralised the bench goes RED "
                   "(the unload happens)")
            else:
                ko("sabotage did not reproduce the defect -- this bench proves "
                   "nothing", "rc=%d, log=%s" % (rc, b.invocations))
        finally:
            b.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("== launchd_refusal -- an installer refuses what it cannot prove is its own ==")
    print("   The launchd domain is a text file. No real launchctl is invoked.")

    print("\n> what is allowed")
    case_absent_no_record()
    case_present_and_recorded()
    case_uninstall_owned()

    print("\n> what is refused, and refused BEFORE the mutation")
    refusal_case("Label present, no record at all",
                 registry=["com.claudebrain.resume"], recorded=None,
                 label="com.claudebrain.resume")
    refusal_case("ownership claimed by the plist on disk",
                 registry=["com.claudebrain.resume"], recorded=[],
                 label="com.claudebrain.resume", plist_on_disk=True)
    refusal_case("ownership claimed by the com.claudebrain.* prefix",
                 registry=["com.claudebrain.machiniste"], recorded=[],
                 label="com.claudebrain.machiniste")
    refusal_case("record holds a DIFFERENT Label",
                 registry=["com.claudebrain.resume"],
                 recorded=["com.claudebrain.machiniste"],
                 label="com.claudebrain.resume")
    case_uninstall_not_owned()

    print("\n> what must not be claimed")
    case_load_fails()

    print("\n> counter-proof")
    case_sabotage_detects()

    print("\n" + "-" * 74)
    if fails:
        print("RED -- %d failure(s)" % len(fails))
        for f in fails:
            print("   . %s" % f)
        return 1
    print("GREEN -- refusal happens before the mutation, and only a success is recorded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
