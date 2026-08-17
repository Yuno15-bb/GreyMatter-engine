#!/usr/bin/env python3
"""update_ownership.py — may `brain update` replace THIS engine at all?

THE INVARIANT:

    An updater replaces only an engine it built itself. Anywhere else it refuses
    and changes NOTHING — not the engine link, not a version on disk, not a file
    in anybody's repository.

WHAT CHANGED ON 2026-08-17, and why this file was rewritten. The gate used to
INFER ownership from the engine's git state: clean, detached, sitting exactly on
a release tag. Inference cannot answer "whose repository is this?" and did not:
`git clone` lands on a branch, so the documented install produced an engine that
was refused for ever, while a developer's clean checkout parked on a tag was
adopted as though the installer had put it there.

There is nothing left to infer. `install.sh` BUILDS the engine under
`~/.c-brain/versions/`, and ownership is the fact that it did — recorded in
`state/engine-managed`, which names the versions root. A development engine says
so in `state/engine-dev`, written only by `install.sh --dev`. The two are
mutually exclusive and neither can be mistaken for the other.

⚠ THIS CONTRACT DOES NOT PROVE THAT `install.sh` WRITES THE MARKER. It builds
its own fixtures, so it cannot: that was the hole the checkpoint named, and it
is `tests/e2e_install_update.sh` that closes it by running the real installer.
What this file gives is the fast, exhaustive half — every shape of engine the
gate can be handed, including the ones an end-to-end run would take minutes to
reach.

WHY THE MANAGED CASE IS ALSO ASSERTED. A gate that refuses everywhere is not a
fix, it is an outage: the updater must still update a real install. That case is
the non-regression half, and it fails if the gate turns out to be a wall.

Run:
  python3 tests/update_ownership.py
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

fails = []


def ok(label):
    print("  ✅ %s" % label)


def ko(label, detail=""):
    print("  ❌ %s%s" % (label, ("  — " + detail) if detail else ""))
    fails.append(label)


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo] + list(args),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout.strip()


def build_remote(path):
    """A published history with two versions, in the shape the updater expects."""
    os.makedirs(path)
    git(path, "init", "-q", "-b", "main")
    subprocess.run(["git", "-C", path, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "t"], check=True)
    os.makedirs(os.path.join(path, "cbrain"))
    os.makedirs(os.path.join(path, "hooks"))
    shutil.copy(os.path.join(ROOT, "cbrain", "update.sh"),
                os.path.join(path, "cbrain", "update.sh"))
    shutil.copy(os.path.join(ROOT, "cbrain", "engine-lib.sh"),
                os.path.join(path, "cbrain", "engine-lib.sh"))
    with open(os.path.join(path, "cbrain", "engine-paths.txt"), "w") as f:
        f.write("hooks\n")
    # A selftest that passes, and an installer that does nothing: this contract is
    # about the GATE, and a real install would drown it in unrelated work.
    with open(os.path.join(path, "hooks", "selftest.sh"), "w") as f:
        f.write("#!/usr/bin/env bash\nexit 0\n")
    with open(os.path.join(path, "install.sh"), "w") as f:
        f.write("#!/usr/bin/env bash\nexit 0\n")
    with open(os.path.join(path, "V"), "w") as f:
        f.write("v1\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "v1")
    git(path, "tag", "-a", "v1.0.0", "-m", "v1")
    with open(os.path.join(path, "V"), "w") as f:
        f.write("v2\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "v2")
    git(path, "tag", "-a", "v1.1.0", "-m", "v2")


def manifest_of(d):
    """The same oracle engine-lib.sh writes: sha256 per file, `shasum -c` format."""
    lines = []
    for root, _dirs, files in os.walk(d):
        for fn in sorted(files):
            if fn == ".cbrain-manifest":
                continue
            full = os.path.join(root, fn)
            rel = "./" + os.path.relpath(full, d)
            with open(full, "rb") as f:
                lines.append("%s  %s" % (hashlib.sha256(f.read()).hexdigest(), rel))
    with open(os.path.join(d, ".cbrain-manifest"), "w") as f:
        f.write("\n".join(sorted(lines, key=lambda l: l.split("  ", 1)[1])) + "\n")


def make_install(home, remote, version="v1.0.0"):
    """An installation in the shape install.sh leaves behind — built, not faked
    in its SHAPE: the version really is an export of the remote at that tag, with
    a real manifest, so the immutability check has something true to check."""
    cb = os.path.join(home, ".c-brain")
    versions = os.path.join(cb, "versions")
    os.makedirs(os.path.join(cb, "state"), exist_ok=True)
    os.makedirs(versions, exist_ok=True)
    dest = os.path.join(versions, version)
    os.makedirs(dest)
    tar = subprocess.run(["git", "-C", remote, "archive", "--format=tar", version],
                         capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", dest], input=tar.stdout, check=True)
    manifest_of(dest)
    mirror = os.path.join(cb, "source.git")
    subprocess.run(["git", "clone", "--bare", "--quiet", remote, mirror], check=True)
    os.symlink(dest, os.path.join(cb, "engine"))
    return cb, versions, dest


def run_update(home, args=()):
    engine = os.path.join(home, ".c-brain", "engine")
    env = dict(os.environ, HOME=home)
    return subprocess.run(
        ["bash", os.path.join(engine, "cbrain", "update.sh")] + list(args),
        capture_output=True, text=True, env=env)


def engine_target(home):
    link = os.path.join(home, ".c-brain", "engine")
    try:
        return os.path.realpath(link) if os.path.exists(link) else "<dangling>"
    except OSError:
        return "<unreadable>"


def case(name, setup, expect_update, extra=None):
    """setup(home, cb, versions, engine) prepares one shape of engine."""
    # ⚠ realpath: on macOS every mktemp path goes through /var -> /private/var,
    # and update.sh resolves the engine with `pwd -P`. A fixture that recorded the
    # unresolved path made a legitimate install look like somebody else's
    # directory — the same trap the installer canonicalises against.
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="cbrain-own."))
    try:
        remote = os.path.join(tmp, "remote")
        build_remote(remote)
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        cb, versions, engine = make_install(home, remote)
        # ownership as install.sh records it: the versions root
        with open(os.path.join(cb, "state", "engine-managed"), "w") as f:
            f.write(versions + "\n")
        setup(home, cb, versions, engine)

        before_link = os.readlink(os.path.join(cb, "engine"))
        before_dirs = sorted(os.listdir(versions))
        r = run_update(home)
        after_link = os.readlink(os.path.join(cb, "engine"))
        after_dirs = sorted(os.listdir(versions))
        out = r.stdout + r.stderr

        if expect_update:
            if r.returncode == 0 and after_link != before_link:
                ok("%s: updated, as it should be" % name)
            else:
                ko("%s: a legitimate install was NOT updated" % name,
                   "rc=%d, engine %s" % (r.returncode, after_link))
        else:
            if r.returncode != 0 and after_link == before_link and after_dirs == before_dirs:
                ok("%s: refused, and nothing moved" % name)
            else:
                ko("%s: the gate let it through" % name,
                   "rc=%d, link %s -> %s, versions %s -> %s"
                   % (r.returncode, before_link, after_link, before_dirs, after_dirs))
            # A refusal that does not SAY nothing was changed sends a frightened
            # user looking for damage that is not there.
            if "Nothing was changed" in out or "disabled for --dev" in out:
                ok("%s: says plainly that nothing was changed" % name)
            else:
                ko("%s: the refusal does not tell the user that nothing was changed" % name,
                   out.strip().splitlines()[-1] if out.strip() else "(no output)")
        if extra:
            extra(name, home, cb, versions, out, r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("== update_ownership — an updater replaces only what it built ==")

    # ─── The non-regression half ────────────────────────────────────────────
    print("\n▸ a managed install is still updated")
    case("managed install", lambda h, c, v, e: None, expect_update=True)

    # ─── The refusals ───────────────────────────────────────────────────────
    print("\n▸ and everywhere else it refuses, touching nothing")

    def no_marker(home, cb, versions, engine):
        os.remove(os.path.join(cb, "state", "engine-managed"))
    case("no ownership marker", no_marker, expect_update=False)

    def dev_marker(home, cb, versions, engine):
        # `install.sh --dev` removes the managed marker; a hand-made state that
        # carried both would test a shape the installer cannot produce.
        os.remove(os.path.join(cb, "state", "engine-managed"))
        with open(os.path.join(cb, "state", "engine-dev"), "w") as f:
            f.write(engine + "\n")

    def dev_named(name, home, cb, versions, out, r):
        # THE POINT OF THE DEV MARKER IS THE DIAGNOSIS. Ownership alone already
        # refuses a checkout; what the marker adds is telling the developer WHY,
        # so they do not go hunting for a marker to create.
        if "Development engine detected" in out:
            ok("%s: refused BY NAME, not by a generic ownership error" % name)
        else:
            ko("%s: the developer is handed the wrong diagnosis" % name,
               out.strip().splitlines()[0] if out.strip() else "(no output)")
    case("development engine", dev_marker, expect_update=False, extra=dev_named)

    def foreign_engine(home, cb, versions, engine):
        # The engine link repointed at somebody's repository since install time.
        # The marker still exists and is still true about `versions/` — it must
        # not vouch for a directory outside it.
        outside = os.path.join(home, "my-own-checkout")
        shutil.copytree(engine, outside)
        os.remove(os.path.join(cb, "engine"))
        os.symlink(outside, os.path.join(cb, "engine"))
    case("engine outside versions/", foreign_engine, expect_update=False)

    def stale_marker(home, cb, versions, engine):
        with open(os.path.join(cb, "state", "engine-managed"), "w") as f:
            f.write(os.path.join(home, "somewhere-else") + "\n")
    case("marker naming another root", stale_marker, expect_update=False)

    def modified_version(home, cb, versions, engine):
        # An immutable version that changed. Something wrote to it — an agent
        # through the trunk's mounts, a hand, a half-finished copy. It is
        # REPORTED, never silently overwritten: overwriting is how the work that
        # got in there would be destroyed.
        with open(os.path.join(engine, "V"), "a") as f:
            f.write("tampered\n")
    case("active version modified since install", modified_version, expect_update=False)

    print()
    if fails:
        print("❌ %d failure(s) — an updater could replace what it does not own"
              % len(fails))
        return 1
    print("✅ the updater replaces what it built, and refuses everything else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
