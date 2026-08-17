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
    script = f'set -u\nENGINE="{engine}"\n{body}\ncapsule_repair\n'
    p = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       timeout=120, env=dict(os.environ, HOME=home))
    return p.returncode, p.stderr


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
        print(f"  repair returns                   {rc}")
        print(f"  runtime answers after repair     {'yes' if after_ok else 'NO'}")
        if rc is None:
            trouble.append(err)
        elif not after_ok:
            trouble.append("after the repair the runtime still does not answer: a fresh "
                           "install would ship a capsule whose window never opens")

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
    ignored = subprocess.run(["git", "-C", ROOT, "check-ignore", "capsule/node_modules"],
                             capture_output=True, text=True).returncode == 0
    print(f"  node_modules ignored by git      {'yes' if ignored else 'NO'}")
    if not ignored:
        trouble.append("capsule/node_modules is not gitignored: the repair would leave the "
                       "engine dirty, and `brain update` refuses on a dirty engine — the "
                       "capsule fix would block every update from then on")

    if trouble:
        print("\n❌ a fresh install can still ship a capsule that cannot start:")
        for t in trouble:
            print(f"     {t}")
        return 1

    print("\n✅ a broken Electron is repaired, and success is claimed only after it answers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
