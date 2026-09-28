#!/usr/bin/env python3
# GreyMatter — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""Updates, wired to SessionStart: look every time, ASK before installing.

The contract, in five points:
  · ASK FIRST, by default (the author's decision, 2026-09-28: the agent checks
    for updates at every session start and asks the user during the session
    whether to update). Silent installing, the default from v1.28.0 to v2.1.0, is
    now an opt-in: `brain update --auto-on`. Oh My Zsh ships the same default
    ("prompt"), and Sparkle never installs silently unless the app opts in.
  · NEVER blocking — the look happens DETACHED, in the background. A session
    must not wait on the network to start.
  · A DEFERRED answer. What a session sees is what the PREVIOUS look found: the
    current one has just left. News one session late beats a session that waits.
  · WHO ASKS is the agent. The hook prints an instruction the agent reads; the
    agent asks the user in plain words and runs `brain update` on a yes. The old
    notice asked the user to type a command, and nobody typed it — that is why
    v1.28.0 went silent. Saying "yes" costs nothing; typing a command did.
  · NOT A NAG. One question per version per day at most, and none once the
    engine is on that version.

ALWAYS exits 0: a hook never breaks a session.
"""

import os
import subprocess
import sys
import time

GM = os.path.expanduser("~/.greymatter")
STATE = os.path.join(GM, "state")
RESULT = os.path.join(STATE, "last-auto-update")
OFF = os.path.join(STATE, "auto-update-off")
ON = os.path.join(STATE, "auto-update-on")          # silent installing, opted into
AVAILABLE = os.path.join(STATE, "update-available")  # "<tag>\t<commit>", the last look
ASKED = os.path.join(STATE, "update-asked")          # "<tag>\t<epoch>", the last question
ASK_EVERY = 24 * 3600


def report():
    """Show the previous pass's result, then delete it.

    Deleting is part of the contract: the file is a MESSAGE, not a state.
    Keeping it would reprint "updated to v1.28.0" at every session for weeks,
    and we would learn to stop reading it — exactly the flaw that killed the
    old notice.
    """
    try:
        with open(RESULT) as f:
            outcome, _, tag = f.read().strip().partition("\t")
    except OSError:
        return
    try:
        os.remove(RESULT)
    except OSError:
        pass

    if outcome == "ok":
        msg = (f"GreyMatter updated itself to {tag}. "
               f"Your notes were not touched.\n"
               "See docs/UPGRADING.md for what changed.")
        if not os.path.exists(ON):
            # The last silent install of a machine that never opted in: the one
            # that brought the ask-first hook. Said once, with the way back.
            msg += ("\nFrom now on GreyMatter asks before installing an update. "
                    "To keep installing on its own: `brain update --auto-on`.")
    elif outcome == "rolled-back":
        msg = (f"The automatic update to {tag} failed its selftest: GreyMatter "
               f"ROLLED BACK to the previous version on its own. "
               f"Log: ~/.greymatter/state/auto-update.log")
    elif outcome == "blocked":
        # ⚠ NO LONGER "uncommitted local changes". That was the only way an update
        # could be blocked while the engine was the user's own git clone. Since
        # 2026-08-17 the engine is a built version and an update can stop for
        # several unrelated reasons — the install owns nothing, the candidate
        # failed its own selftest, the build did not come out. Naming one cause
        # for all of them sends the reader to look for a problem they do not have;
        # the log names the real one.
        msg = (f"Update {tag} is available but was NOT applied. Nothing was "
               f"changed and GreyMatter is still running the version it was. "
               f"Why: ~/.greymatter/state/auto-update.log — or run `brain update`.")
    elif outcome == "dev":
        # A development install. Expected, and said once rather than warned about:
        # this is a configuration the developer chose by running `install.sh --dev`.
        msg = ("This is a development install (`install.sh --dev`): GreyMatter does "
               "not update its own engine here. Update it with git.")
    else:
        return
    print(f"<greymatter-update>{msg}</greymatter-update>")


def current_tag(engine):
    return os.path.basename(os.path.realpath(engine))


def probe(engine):
    """The look itself, run DETACHED: `update.sh --check`, its answer kept in a file.

    rc 10 = a version exists → AVAILABLE. rc 0 with "already up to date" → the
    file goes. Anything else (offline, no mirror, a dev install) changes nothing:
    an unanswered look is not a "no".
    """
    try:
        r = subprocess.run(
            ["bash", os.path.join(engine, "greymatter", "update.sh"), "--check"],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return
    if r.returncode == 10:
        tag = commit = ""
        for line in r.stdout.splitlines():
            if "new version available:" in line:
                tag = line.split(":", 1)[1].strip()
            elif line.strip().startswith("commit:"):
                commit = line.split(":", 1)[1].strip()
        if tag:
            tmp = AVAILABLE + ".tmp"
            with open(tmp, "w") as f:
                f.write(f"{tag}\t{commit}\n")
            os.replace(tmp, AVAILABLE)     # atomic: a reader never sees half a line
    elif r.returncode == 0 and "already up to date" in r.stdout:
        try:
            os.remove(AVAILABLE)
        except OSError:
            pass


def ask(engine):
    """Print the question for the agent, when there is one to ask."""
    try:
        with open(AVAILABLE) as f:
            tag = f.read().split("\t")[0].strip()
    except OSError:
        return
    cur = current_tag(engine)
    if not tag or tag == cur:
        return                               # already there: nothing to ask
    try:
        with open(ASKED) as f:
            last_tag, _, when = f.read().strip().partition("\t")
        if last_tag == tag and time.time() - float(when) < ASK_EVERY:
            return                           # asked about this one today already
    except (OSError, ValueError):
        pass
    try:
        with open(ASKED, "w") as f:
            f.write(f"{tag}\t{int(time.time())}\n")
    except OSError:
        pass
    print(f"<greymatter-update>GreyMatter {tag} is available; this machine runs {cur}. "
          f"Ask the user, once and in plain words, whether they want to update "
          f"GreyMatter now. If they say yes, run `brain update` and tell them what it "
          f"printed. Their notes are never touched. If they say no, do not ask again "
          f"in this session. (Updates can install on their own instead: "
          f"`brain update --auto-on`.)</greymatter-update>")


def detach(args, engine):
    # `start_new_session=True` is NOT a convenience detail: without it the
    # process stays in the session's process group and dies with it. For an
    # install, being killed between the `checkout` and `install.sh` leaves a
    # half-switched installation. Streams go to /dev/null rather than a pipe: a
    # pipe nobody reads eventually fills up and FREEZES the writer.
    try:
        with open(os.devnull, "r+b") as void:
            subprocess.Popen(args, stdin=void, stdout=void, stderr=void,
                             start_new_session=True, cwd=engine)
    except (OSError, subprocess.SubprocessError):
        pass                    # nothing here justifies getting in a start's way


def main():
    engine = os.path.join(GM, "engine")
    if not os.path.isdir(engine):
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        probe(engine)
        return 0
    report()
    silent = os.path.exists(ON) and not (
        os.environ.get("GREYMATTER_NO_AUTO_UPDATE")
        or os.environ.get("CBRAIN_NO_AUTO_UPDATE"))   # pre-rename name still honoured
    if silent:
        detach(["bash", os.path.join(engine, "greymatter", "update.sh"), "--auto"], engine)
        return 0
    ask(engine)
    detach([sys.executable, os.path.abspath(__file__), "--probe"], engine)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # a hook NEVER breaks a session
