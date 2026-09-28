#!/usr/bin/env python3
"""capsule_runtime.py — does a fresh install leave a menu bar pill that actually runs?

THE INVARIANT:

    After install.sh, either the pill's binary exists and answers `--check`, or
    the installer says plainly that the pill is skipped and names the next step
    (`xcode-select --install`). Never "installed" over a binary that is not there.

WHY THIS BENCH CHANGED SHAPE (2026-09-28). Until 2.2 the capsule was Electron,
and this file held the repair for an Electron that npm reported as installed and
never extracted. The capsule is now a native Swift program (capsule/macos). What
can go wrong moved with it:

    a version directory is IMMUTABLE (sha256 manifest), so the build must not
      land inside it — it lands in the shared runtime root and the version only
      holds a link, `capsule/macos/.build`;
    a build that FAILS must not leave a binary behind that the installer would
      then start and call a success;
    a second install of the same sources must not rebuild (30 s, 120 MB scratch);
    sources that CHANGE must get their own build, not the previous binary.

WHY THE FUNCTIONS ARE SOURCED RATHER THAN COPIED. A copy would test a copy. This
sources the real greymatter/engine-lib.sh, so gutting build_capsule fails here.

WHAT IS NOT TESTED HERE. Pixels. The pill in the menu bar needs a logged-in
screen; `--check` proves the binary loads AppKit, finds its trunk and reads the
status with the canonical freshness windows, which is what an install can break.

Run:
  python3 tests/capsule_runtime.py
  python3 tests/capsule_runtime.py --check
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(ROOT, "greymatter", "engine-lib.sh")
INSTALL = os.path.join(ROOT, "install.sh")
SRC = os.path.join(ROOT, "capsule", "macos")


def fake_version(base, name):
    """A version directory holding only what the build needs: Package.swift + Sources."""
    eng = os.path.join(base, "versions", name)
    os.makedirs(os.path.join(eng, "capsule"))
    shutil.copytree(SRC, os.path.join(eng, "capsule", "macos"),
                    ignore=shutil.ignore_patterns(".build", ".swiftpm"))
    return eng


def build(eng, runtime, log):
    t = time.time()
    r = subprocess.run(["bash", "-c", 'source "$1"; build_capsule "$2" "$3" "$4"',
                        "_", LIB, eng, runtime, log], capture_output=True, text=True)
    return r.returncode, time.time() - t


def main():
    if sys.platform != "darwin":
        print("Capsule runtime — skipped (the pill is a macOS program)")
        return 0
    if not shutil.which("swift") or subprocess.run(["xcode-select", "-p"],
                                                    capture_output=True).returncode:
        print("Capsule runtime — skipped (no Swift: xcode-select --install)")
        return 0

    trouble = []
    base = tempfile.mkdtemp(prefix="capsule-runtime-")
    runtime = os.path.join(base, "runtime")
    try:
        # ---------- 1. a clean build lands OUTSIDE the version ----------
        eng = fake_version(base, "v1")
        rc, dt = build(eng, runtime, os.path.join(base, "build1.log"))
        link = os.path.join(eng, "capsule", "macos", ".build")
        binary = os.path.join(link, "release", "Capsule")
        ok = rc == 0 and os.path.islink(link) and os.access(binary, os.X_OK)
        print(f"  first build        rc={rc}  {dt:5.1f}s  binary through the link: {'yes' if ok else 'NO'}")
        if not ok:
            trouble.append("build_capsule did not leave an executable pill behind the "
                           "version's .build link — see build1.log")
            print(open(os.path.join(base, "build1.log"), errors="replace").read()[-1500:])
            raise SystemExit
        target = os.path.realpath(link)
        inside = target.startswith(os.path.realpath(eng) + os.sep)
        print(f"  build lands in     {os.path.relpath(target, base)}  (inside the version: {'YES' if inside else 'no'})")
        if inside:
            trouble.append("the build landed inside the immutable version directory")
        leftovers = [n for n in os.listdir(runtime) if ".building." in n]
        size = os.path.getsize(binary) / 1e6
        print(f"  scratch removed    {'yes' if not leftovers else 'NO ' + str(leftovers)}   binary {size:.1f} MB")
        if leftovers:
            trouble.append(f"the ~120 MB scratch build was left behind: {leftovers}")

        # ---------- 2. the binary answers, and reads with the canonical windows ----------
        trunk = os.path.join(base, "trunk")
        os.makedirs(os.path.join(trunk, "state"))
        os.makedirs(os.path.join(trunk, "hooks"))
        shutil.copy(os.path.join(ROOT, "hooks", "status_freshness.json"),
                    os.path.join(trunk, "hooks"))
        now = time.time()
        cases = (  # (status.json, expected state, expected detail, why)
            ({"state": "busy", "ts": now, "activity": "distilling", "activity_ts": now,
              "detail": "notes"}, "distilling", "notes", "fresh label"),
            ({"state": "busy", "ts": now, "activity": "distilling", "activity_ts": now - 500,
              "detail": "notes"}, "working", "", "stale label → working, detail dropped"),
            ({"state": "busy", "ts": now - 40, "activity": "distilling", "activity_ts": now},
             "idle", "", "no tool for 40 s → idle"),
        )
        cfg = json.load(open(os.path.join(ROOT, "hooks", "status_freshness.json")))
        for status, want, want_detail, why in cases:
            json.dump(status, open(os.path.join(trunk, "state", "status.json"), "w"))
            r = subprocess.run([binary, "--check"], capture_output=True, text=True, timeout=20,
                               env=dict(os.environ, CAPSULE_BRAIN=trunk))
            try:
                got = json.loads(r.stdout.strip().splitlines()[-1])
            except Exception:
                got = {}
            ok = (got.get("state") == want and got.get("detail") == want_detail
                  and got.get("liveness_s") == cfg["liveness_stale_seconds"]
                  and got.get("activity_s") == cfg["activity_stale_seconds"])
            print(f"  --check            {why:40} → {got.get('state')!s:10} {'yes' if ok else 'NO'}")
            if not ok:
                trouble.append(f"--check on '{why}' answered {got or r.stderr.strip()[:200]!r}")

        # ---------- 2b. it finds ITS trunk, never the user's ----------
        # Found on 2026-09-28: with HOME=<temp> and no CAPSULE_BRAIN, the pill read the REAL
        # ~/.greymatter/trunk. It resolved the `.build` link (into the runtime, outside any
        # trunk) before walking up, then fell back on NSHomeDirectory(), which ignores $HOME.
        # Any bench isolating a pill with HOME=<temp> was reading the author's live trunk.
        home = os.path.join(base, "home")
        t2 = os.path.join(home, ".greymatter", "trunk")
        os.makedirs(os.path.join(t2, "state"))
        os.makedirs(os.path.join(t2, "capsule", "macos"))
        os.symlink(target, os.path.join(t2, "capsule", "macos", ".build"))
        env = {k: v for k, v in os.environ.items() if k not in ("CAPSULE_BRAIN", "CAPSULE_STATUT_HOME")}
        env["HOME"] = home
        for why, exe in (("launched through the trunk's link", os.path.join(t2, "capsule", "macos", ".build", "release", "Capsule")),
                         ("launched from the runtime, HOME=<temp>", os.path.join(target, "release", "Capsule"))):
            r = subprocess.run([exe, "--check"], capture_output=True, text=True, timeout=20, env=env)
            try:
                got = json.loads(r.stdout.strip().splitlines()[-1]).get("trunk", "")
            except Exception:
                got = ""
            ok = os.path.realpath(got or "/nonexistent") == os.path.realpath(t2)
            print(f"  its trunk          {why:40} → {'yes' if ok else 'NO: ' + (got or r.stderr.strip()[:80])}")
            if not ok:
                trouble.append(f"{why}, the pill read {got or 'nothing'!r} instead of its own trunk")

        # ---------- 3. same sources: no rebuild ----------
        eng2 = fake_version(base, "v2")
        rc, dt = build(eng2, runtime, os.path.join(base, "build2.log"))
        same = os.path.realpath(os.path.join(eng2, "capsule", "macos", ".build")) == target
        print(f"  same sources       rc={rc}  {dt:5.1f}s  shares the build: {'yes' if same else 'NO'}")
        if rc or not same or dt > 5:
            trouble.append(f"a second version with the same sources rebuilt ({dt:.0f} s) "
                           "or linked elsewhere")

        # ---------- 4. a broken source: no binary, a non-zero exit ----------
        # The sabotage the installer must survive: it starts the pill only on rc 0.
        eng3 = fake_version(base, "v3")
        main_swift = os.path.join(eng3, "capsule", "macos", "Sources", "Capsule", "main.swift")
        with open(main_swift, "a") as f:
            f.write("\nlet cassé: Int = \"not an int\"\n")
        log3 = os.path.join(base, "build3.log")
        rc, dt = build(eng3, runtime, log3)
        bin3 = os.path.join(eng3, "capsule", "macos", ".build", "release", "Capsule")
        other = os.path.realpath(os.path.join(eng3, "capsule", "macos", ".build")) != target
        refused = rc != 0 and not os.path.exists(bin3) and other
        said = "error" in open(log3, errors="replace").read()
        print(f"  broken source      rc={rc}  {dt:5.1f}s  no binary, own dir: {'yes' if refused else 'NO'}"
              f"   log names the error: {'yes' if said else 'NO'}")
        if not refused:
            trouble.append("a source that does not compile still produced — or borrowed — a "
                           "binary: the installer would start the previous pill and call it new")
        if not said:
            trouble.append("the build log of a failed build does not contain the compiler error")
        leftovers = [n for n in os.listdir(runtime) if ".building." in n]
        if leftovers:
            trouble.append(f"a failed build left its scratch behind: {leftovers}")

        # ---------- 5. the installer names the next step when Swift is missing ----------
        src = open(INSTALL, encoding="utf-8").read()
        names = "xcode-select --install" in src and "build_capsule" in src
        print(f"  install.sh         names xcode-select --install, calls build_capsule: {'yes' if names else 'NO'}")
        if not names:
            trouble.append("install.sh no longer builds the pill through build_capsule, or no "
                           "longer names `xcode-select --install` when Swift is missing")
    except SystemExit:
        pass
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    if trouble:
        print("❌ the capsule's install path is broken:")
        for t in trouble:
            print("   -", t)
        return 1
    print("✅ the pill builds outside the version, answers, and a broken build leaves nothing to start")
    return 0


if __name__ == "__main__":
    sys.exit(main())
