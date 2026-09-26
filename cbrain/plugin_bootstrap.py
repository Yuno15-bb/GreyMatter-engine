#!/usr/bin/env python3
"""
plugin_bootstrap.py — makes the trunk exist when C Brain arrives as a PLUGIN.

Installing the plugin is not running install.sh. Nobody created ~/.c-brain,
nobody linked the engine into the trunk, and nobody put the `brain` command
anywhere. This runs first on every SessionStart and makes the layout true —
including the trunk's local git history, which install.sh starts and the
session-end auto-save needs.

WHY IT RUNS EVERY TIME, not once. ${CLAUDE_PLUGIN_ROOT} moves whenever the
plugin updates — the old directory is kept for a couple of weeks and then
collected. A link written once would rot into a dangling symlink the day after
an update, and every hook would fail with a file-not-found nobody can read. So
each session re-points the links at wherever the plugin lives NOW. It is a
handful of stat() calls and writes nothing when everything already agrees.

WHAT IT WILL NOT DO. It never touches a note, never replaces a real directory
with a link (a real hooks/ folder means an older standalone install — that is
someone's files, and the two layouts must not be silently merged), and always
exits 0. A memory tool that breaks the session it is trying to help is worse
than no memory at all.
"""
import json
import os
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")
CB = os.path.join(HOME, ".c-brain")
TRUNK = os.path.join(CB, "trunk")
LINKED = ("hooks", "agents", "capsule", "planet", "companion", "tests")

# The plugin's own directory. Claude Code sets this; when it is absent we are
# being run by hand from a clone, and the file's own location is the answer.
ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def relink(target, path):
    """Idempotent symlink. Returns True when it actually wrote something."""
    if os.path.islink(path):
        if os.readlink(path) == target:
            return False
        os.unlink(path)
    elif os.path.exists(path):
        return False        # a real directory: someone's content, not ours
    os.symlink(target, path)
    return True


def seed_from_skeleton():
    """Copies every skeleton file the trunk lacks. Never overwrites one."""
    skeleton = os.path.join(ROOT, "skeleton")
    if not os.path.isdir(skeleton):
        return
    for dirpath, _, filenames in os.walk(skeleton):
        dest = os.path.normpath(os.path.join(TRUNK, os.path.relpath(dirpath, skeleton)))
        os.makedirs(dest, exist_ok=True)
        for name in filenames:
            if not os.path.lexists(os.path.join(dest, name)):
                shutil.copy2(os.path.join(dirpath, name), os.path.join(dest, name))


def start_history():
    """The same local history install.sh starts: without it, the per-zone
    auto-save at session end returns early, silently, for every plugin user."""
    if os.path.exists(os.path.join(TRUNK, ".git")):
        return
    git = shutil.which("git")
    if not git:
        return
    # Apple's /usr/bin/git is a stub until the Command Line Tools are in, and
    # calling it opens Apple's install dialog — here, at every session start.
    if sys.platform == "darwin" and git == "/usr/bin/git" and subprocess.run(
            ["/usr/bin/xcode-select", "-p"], capture_output=True).returncode != 0:
        return
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=c-brain@localhost", "-c", "user.name=C Brain",
                  "commit", "-qm", "the trunk, as installed"]):
        if subprocess.run([git, "-C", TRUNK] + args, capture_output=True,
                          timeout=8).returncode != 0:
            return


def main():
    # ⚠ "THE FOLDER EXISTS" DOES NOT MEAN "THE TRUNK WAS SET UP". Claude Code
    # runs the SessionEnd hooks when `claude plugin install` itself exits — so
    # the maintenance writes state/ before any SessionStart has run. This test
    # used to be `not os.path.isdir(TRUNK)`: on a blank Mac (2026-09-26) every
    # plugin install got a trunk with no index, no config and no history, the
    # welcome line never appeared, and `brain selftest` stayed red for good.
    # A trunk with no index and no history has never been set up, whatever
    # created its folder.
    fresh = not os.path.exists(os.path.join(TRUNK, "MEMORY.md")) \
        and not os.path.exists(os.path.join(TRUNK, ".git"))
    os.makedirs(TRUNK, exist_ok=True)
    if fresh:
        seed_from_skeleton()

    for d in ("state", os.path.join("sessions", "archive")):
        os.makedirs(os.path.join(TRUNK, d), exist_ok=True)

    try:
        start_history()
    except Exception:
        pass                       # never worth failing a session over

    relink(ROOT, os.path.join(CB, "engine"))
    for d in LINKED:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            relink(src, os.path.join(TRUNK, d))

    # The version a plugin install can actually report. Without this file,
    # `brain version` answers "(unknown version)" to everyone who arrived
    # through the marketplace — and version is the first thing anyone is asked
    # for when something goes wrong. install.sh writes it; nothing else did.
    try:
        manifest = os.path.join(ROOT, ".claude-plugin", "plugin.json")
        with open(manifest, encoding="utf-8") as f:
            version = json.load(f).get("version")
        if version:
            with open(os.path.join(CB, "VERSION"), "w", encoding="utf-8") as f:
                f.write(f"{version} (plugin)\n")
    except Exception:
        pass                       # never worth failing a session over

    if fresh:
        # Said once, on the session where the trunk appears — and said where a
        # first-time user is actually looking, not in a README they have not
        # opened. An empty trunk that explains nothing is where people give up.
        #
        # ⚠ It does NOT promise the `C Brain` shortcut. That folder is created
        # by install.sh, which a plugin install never runs — so the first
        # sentence a marketplace user ever read pointed at something that was
        # not there. The path is given instead, because it is true.
        #
        # ⚠ Nor does it hand out `brain` as a terminal command. The plugin's bin/
        # goes on the PATH of Claude Code's own shell, never on the user's
        # terminal: typed there, the three commands answered "command not found"
        # (blank-Mac test, 2026-09-26). They are offered where they run.
        print("🧠 C Brain: your trunk is ready at ~/.c-brain/trunk — plain "
              "markdown files, yours.\n"
              "   To see it work, ask Claude to run: brain demo · brain recall cache "
              "· brain demo --remove\n"
              "   (`brain` runs inside Claude Code; for your own terminal too, "
              "install with install.sh)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                       # never break a session
        print(f"c-brain bootstrap skipped: {e}", file=sys.stderr)
    sys.exit(0)
