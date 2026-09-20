#!/usr/bin/env python3
"""capsule_runtime.py — does a fresh install leave an Electron that actually runs?

THE INVARIANT:

    After install.sh, either the capsule's runtime answers `--version`, or the
    installer says plainly that the orb will not open. Never "installed" over a
    runtime that aborts.

THE FAILURE THIS EXISTS TO PREVENT, measured on 2026-08-17 (macOS arm64, Node
v26.5.0, npm 11.17), on a genuinely empty `node_modules`:

    the archive downloads, `unzip -t` reports no error;
    electron's postinstall RUNS, finishes in ONE second, exits 0, prints nothing;
    with DEBUG=* it extracts 20 directory entries, reaches the first real file
      ("opening read stream … electron.icns") and the process simply ends;
    dist/ stays at 256 KB instead of ~250 MB, with no Frameworks/ at all,
    and path.txt — written only on success — never appears.

The binary was therefore present, executable, and died with "Library not loaded:
@rpath/Electron Framework.framework/Electron Framework". Identical on electron 42,
so it is not the electron version. The installer detected it and printed a remedy
that was `npm install` again — the very thing that had just failed.

WHAT IS TESTED HERE, AND WHAT IS NOT. Unpacking 250 MB is not a unit test. What
this holds is the MECHANISM: the repair reads the archive electron already
downloaded, replaces dist, writes path.txt the way electron writes it, and the
installer only claims success after starting the binary again. The real 250 MB
path was verified by hand on a fresh install, and the recipe records it.

WHY THE FUNCTION IS EXTRACTED FROM install.sh RATHER THAN COPIED. A copy would
test a copy. This reads the real text between `capsule_repair() {` and its closing
brace, so deleting or gutting the function fails the test.

Run:
  python3 tests/capsule_runtime.py
  python3 tests/capsule_runtime.py --check
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INSTALL = os.path.join(ROOT, "install.sh")
PLATFORM_PATH = "Electron.app/Contents/MacOS/Electron"


def extract_function(name):
    """The real function body out of install.sh, by brace depth."""
    src = open(INSTALL, encoding="utf-8").read()
    start = src.find(f"{name}() {{")
    if start == -1:
        return None
    depth, i = 0, start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    return None


def fake_electron_zip(path, version):
    """An archive shaped like electron's, small enough to be a test."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("LICENSE", "x\n")
        info = zipfile.ZipInfo(PLATFORM_PATH)
        info.external_attr = (stat.S_IFREG | 0o755) << 16
        z.writestr(info, f"#!/bin/sh\necho v{version}\n")


def build_broken_install(home, engine, version, with_zip=True):
    """A node_modules in exactly the state npm leaves behind when extraction dies."""
    ed = os.path.join(engine, "capsule", "node_modules", "electron")
    os.makedirs(os.path.join(ed, "dist", "Electron.app", "Contents", "MacOS"), exist_ok=True)
    with open(os.path.join(ed, "package.json"), "w") as f:
        f.write(f'{{"name":"electron","version":"{version}"}}')
    # the 50 KB stub that exists and aborts — the whole trap
    stub = os.path.join(ed, "dist", PLATFORM_PATH)
    with open(stub, "w") as f:
        f.write("#!/bin/sh\nexit 133\n")
    os.chmod(stub, 0o755)
    if with_zip:
        cache = os.path.join(home, "Library", "Caches", "electron", "deadbeef")
        os.makedirs(cache, exist_ok=True)
        fake_electron_zip(os.path.join(cache, f"electron-v{version}-darwin-arm64.zip"), version)
    return ed


def run_repair(home, engine):
    body = extract_function("capsule_repair")
    if body is None:
        return None, "capsule_repair is gone from install.sh"
    env = dict(os.environ, HOME=home)

    def run(trace):
        opts = "set -xu" if trace else "set -u"
        script = f'{opts}\nENGINE="{engine}"\n{body}\ncapsule_repair\n'
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                              timeout=120, env=env)

    p = run(trace=False)
    if p.returncode == 0:
        return 0, ""
    # ⚠ A RED THAT DOES NOT NAME ITS CAUSE IS UNREADABLE, and `capsule_repair`
    #   has EIGHT ways of returning 1 — not Darwin, no node_modules, no unzip,
    #   no node, no version, an architecture it does not ship, no archive in the
    #   cache, a failed unpack. Reported as a bare `1` they are indistinguishable,
    #   and on 2026-09-20 a CI runner went red on one of them with no way to tell
    #   which. So a failure is replayed under xtrace and the last command the
    #   shell ran before giving up is carried back in the report.
    t = run(trace=True)
    steps = [l.lstrip("+ ") for l in t.stderr.splitlines()
             if l.startswith("+") and "return" not in l]
    # The last TWO, because the line that fails is often an assignment whose
    # value is already gone — `ver=` says nothing, `node -p … → ver=` says
    # everything. Truncated: a trace line carries a whole temporary path.
    tail = " → ".join(x[:70] for x in steps[-2:])
    return p.returncode, (tail if tail else p.stderr.strip())


def main():
    check = "--check" in sys.argv
    trouble = []
    version = "33.4.11"

    if os.uname().machine != "arm64" or os.uname().sysname != "Darwin":
        print("Capsule runtime — skipped (the repair ships for macOS arm64)")
        return 0

    print("Capsule runtime — the repair for an Electron that never finished extracting\n")

    # 1. The repair turns a broken runtime into one that answers.
    with tempfile.TemporaryDirectory() as tmp:
        home, engine = os.path.join(tmp, "home"), os.path.join(tmp, "engine")
        os.makedirs(home)
        ed = build_broken_install(home, engine, version)
        binary = os.path.join(ed, "dist", PLATFORM_PATH)

        # A repair that leaves NO binary at all must read as a failure, not as a
        # Python traceback: a red that only shows a stack tells the next person
        # nothing about what broke. Seen when a sabotage removed the unpack step.
        def answers(path):
            if not os.path.exists(path):
                return False
            return subprocess.run([path], capture_output=True).returncode == 0

        before = answers(binary)
        rc, err = run_repair(home, engine)
        after_ok = answers(binary)

        print(f"  broken runtime answers first     {'yes' if before else 'no'}")
        print(f"  repair returns                   {rc}"
              + (f"   (gave up on: {err})" if rc else ""))
        print(f"  runtime answers after repair     {'yes' if after_ok else 'NO'}")
        if rc is None:
            trouble.append(err)
        elif not after_ok:
            trouble.append("after the repair the runtime still does not answer: a fresh "
                           "install would ship a capsule whose window never opens"
                           + (f" — the repair gave up on `{err}`" if err else ""))

        # 2. path.txt exactly as electron writes it. A trailing newline makes
        #    electron's own isInstalled() disagree and re-run the broken download
        #    on every later npm install — the bug would come back by itself.
        pt = os.path.join(ed, "path.txt")
        content = open(pt).read() if os.path.exists(pt) else None
        print(f"  path.txt                         {content!r}")
        if content != PLATFORM_PATH:
            trouble.append(f"path.txt is {content!r}, electron compares it to "
                           f"{PLATFORM_PATH!r} with a strict !=: any difference makes the "
                           "next npm install redo the extraction that fails")

    # 3. With nothing to unpack, the repair must FAIL rather than half-succeed.
    with tempfile.TemporaryDirectory() as tmp:
        home, engine = os.path.join(tmp, "home"), os.path.join(tmp, "engine")
        os.makedirs(home)
        build_broken_install(home, engine, version, with_zip=False)
        rc, _ = run_repair(home, engine)
        print(f"  no archive to unpack             refuses: {'yes' if rc else 'NO'}")
        if not rc:
            trouble.append("the repair reports success with no archive to unpack: the "
                           "installer would announce a working capsule over nothing")

    # 4. The installer must not CLAIM the repair worked without starting the binary.
    src = open(INSTALL, encoding="utf-8").read()
    gated = re.search(r"capsule_repair\s*&&\s*capsule_ok", src)
    print(f"  success gated on the binary      {'yes' if gated else 'NO'}")
    if not gated:
        trouble.append("install.sh announces the repaired capsule without re-checking the "
                       "binary: the same false 'installed' as before, one layer down")

    # 5. The repair writes ~250 MB into the engine repo. If those paths were
    #    tracked, every install would leave the engine dirty — and the ownership
    #    gate added for `brain update` refuses on a dirty engine, absolutely. The
    #    capsule fix would then block every future update, silently and for good.
    #    The two worksites only stay independent because git ignores this path.
    #    ⚠ ASKED ABOUT A FILE, NOT ABOUT THE DIRECTORY, and the difference is not
    #    cosmetic. The rule in .gitignore is `capsule/node_modules/`, and a pattern
    #    ending in a slash only matches a DIRECTORY — which `git check-ignore` can
    #    only recognise by looking at the disk. Measured 2026-09-20 in a throwaway
    #    repo: with nothing on disk, `capsule/node_modules` does NOT match while
    #    `capsule/node_modules/electron/package.json` does; create the directory
    #    and both match. The old probe therefore answered "not ignored" on every
    #    fresh clone — the very situation it exists to protect — and answered it
    #    in the same words it would use if the rule had been deleted. It was green
    #    here only because this author's own clone has the runtime installed, and
    #    it went red the first time a CI runner ran it. The probe is now the path
    #    the repair actually writes, which is a file and needs no disk.
    probe = f"capsule/node_modules/electron/dist/{PLATFORM_PATH}"
    ignored = subprocess.run(["git", "-C", ROOT, "check-ignore", probe],
                             capture_output=True, text=True).returncode == 0
    print(f"  what the repair writes, ignored  {'yes' if ignored else 'NO'}")
    if not ignored:
        trouble.append("capsule/node_modules is not gitignored: the repair would leave the "
                       "engine dirty, and `brain update` refuses on a dirty engine — the "
                       "capsule fix would block every update from then on")

    # 6. THE CRASH TRACE MUST NOT REACH THE READER — and the check must still fail.
    #
    #    "Abort trap: 6" is not written by the binary. Bash writes it, about a job
    #    it has just reaped, to the stderr bash held at that moment. No redirection
    #    placed on the command can reach it. Measured 2026-09-20: the subshell that
    #    was shipped as the fix made the trace LONGER (77 bytes -> 94), because bash
    #    runs a lone command inside `( )` in the subshell process itself, so the
    #    subshell IS the job the outer shell reports on.
    #
    #    THE CALIBRATION IS THE POINT. A stub that merely exits non-zero makes this
    #    pass without proving anything. So the bare probe is run FIRST and must be
    #    NOISY; only then does silence from the real function mean something.
    with tempfile.TemporaryDirectory() as tmp:
        engine = os.path.join(tmp, "engine")
        binary = os.path.join(engine, "capsule", "node_modules", "electron",
                              "dist", PLATFORM_PATH)
        os.makedirs(os.path.dirname(binary))
        with open(binary, "w") as f:
            f.write("#!/bin/sh\nkill -ABRT $$\n")   # dies of SIGABRT, like the real one
        os.chmod(binary, 0o755)

        def run(body_or_probe, call):
            script = 'set -u\nENGINE="%s"\n%s\n%s\n' % (engine, body_or_probe, call)
            p = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                               timeout=60)
            return p.returncode, p.stderr

        nu = ('nu() {\n'
              '  local bin="$ENGINE/capsule/node_modules/electron/dist/%s"\n'
              '  [ -x "$bin" ] && "$bin" --version >/dev/null 2>&1\n'
              '}' % PLATFORM_PATH)
        # WHICH bash, written into the report. This case measures a line the
        # SHELL writes about a job it has reaped, not anything the binary prints,
        # so the shell is half the instrument and an unnamed instrument makes the
        # measurement unreadable. macOS ships bash 3.2 at /bin/bash while a build
        # runner may well put a 5.x first on PATH, and `run()` resolves `bash`
        # through PATH like everybody else.
        shell = shutil.which("bash") or "bash"
        sv = subprocess.run([shell, "--version"], capture_output=True, text=True).stdout
        m = re.search(r"version (\S+)", sv)
        shell_id = f"{shell} {m.group(1) if m else '?'}"
        print(f"  the shell that reports the crash {shell_id}")

        rc_nu, err_nu = run(nu, "nu")
        print(f"  unguarded probe is noisy         {'yes' if err_nu.strip() else 'NO'}"
              f" ({len(err_nu)} B)")
        if not err_nu.strip():
            trouble.append(f"{shell_id} said nothing at all about a job it reaped on a "
                           "signal, so this case cannot tell a working guard from a missing "
                           "one: the CALIBRATION failed, and nothing here judges capsule_ok")

        body = extract_function("capsule_ok")
        if body is None:
            trouble.append("capsule_ok is gone from install.sh")
        else:
            rc_ok, err_ok = run(body, "capsule_ok")
            print(f"  guarded probe is silent          {'yes' if not err_ok.strip() else 'NO'}"
                  f" ({len(err_ok)} B)")
            print(f"  broken binary still refused      {'yes' if rc_ok else 'NO'}")
            if err_ok.strip():
                trouble.append("capsule_ok lets the shell print %r: a fresh install shows a "
                               "crash trace one line before announcing success"
                               % err_ok.strip()[:80])
            if not rc_ok:
                trouble.append("capsule_ok returns success over a binary that aborts: "
                               "silencing the trace must not silence the verdict")

    if trouble:
        print("\n❌ a fresh install can still ship a capsule that cannot start:")
        for t in trouble:
            print(f"     {t}")
        return 1

    print("\n✅ a broken Electron is repaired, and success is claimed only after it answers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
