#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""Automatic updates, wired to SessionStart.

The contract, in four points:
  · NEVER blocking — the update leaves DETACHED, in the background. A session
    must not wait on the network to start, and certainly not on a `git checkout`
    followed by a selftest.
  · Every session start. No 24 h window: that throttle made sense while the hook
    only PRINTED a line people eventually stopped reading. An update that
    applies itself has no reason to wait until tomorrow.
  · A DEFERRED report. What you see at session start is the result of the
    PREVIOUS pass: the current one has just left and has nothing to say yet.
    That is the price of being non-blocking, and it is an honest one — better
    news that is one session late than a session that waits.
  · It can be turned off. `brain update --auto-off`, or CBRAIN_NO_AUTO_UPDATE=1:
    you then fall back to the old behaviour, report without applying.

ALWAYS exits 0: a hook never breaks a session.
"""

import os
import subprocess
import sys

CB = os.path.expanduser("~/.c-brain")
STATE = os.path.join(CB, "state")
RESULT = os.path.join(STATE, "last-auto-update")
OFF = os.path.join(STATE, "auto-update-off")


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
        msg = (f"C Brain updated itself to {tag}. "
               f"Your notes were not touched.")
    elif outcome == "rolled-back":
        msg = (f"The automatic update to {tag} failed its selftest: C Brain "
               f"ROLLED BACK to the previous version on its own. "
               f"Log: ~/.c-brain/state/auto-update.log")
    elif outcome == "blocked":
        # ⚠ NO LONGER "uncommitted local changes". That was the only way an update
        # could be blocked while the engine was the user's own git clone. Since
        # 2026-08-17 the engine is a built version and an update can stop for
        # several unrelated reasons — the install owns nothing, the candidate
        # failed its own selftest, the build did not come out. Naming one cause
        # for all of them sends the reader to look for a problem they do not have;
        # the log names the real one.
        msg = (f"Update {tag} is available but was NOT applied. Nothing was "
               f"changed and C Brain is still running the version it was. "
               f"Why: ~/.c-brain/state/auto-update.log — or run `brain update`.")
    elif outcome == "dev":
        # A development install. Expected, and said once rather than warned about:
        # this is a configuration the developer chose by running `install.sh --dev`.
        msg = ("This is a development install (`install.sh --dev`): C Brain does "
               "not update its own engine here. Update it with git.")
    else:
        return
    print(f"<c-brain-update>{msg}</c-brain-update>")


def main():
    engine = os.path.join(CB, "engine")
    if not os.path.isdir(engine):
        return 0

    report()

    if os.path.exists(OFF) or os.environ.get("CBRAIN_NO_AUTO_UPDATE"):
        # The previous behaviour, kept word for word for whoever turned
        # automatic updates off: look, report, apply nothing.
        try:
            r = subprocess.run(
                ["bash", os.path.join(engine, "cbrain", "update.sh"), "--check"],
                capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return 0            # offline, no git, slow link: stay quiet
        if r.returncode == 10:
            tag = ""
            for line in r.stdout.splitlines():
                if "new version available" in line:
                    tag = line.split(":")[-1].strip()
            print(f"<c-brain-update>A new version of C Brain is available"
                  f"{' (' + tag + ')' if tag else ''}. "
                  f"Run `brain update` whenever it suits you — your notes will not be touched."
                  f"</c-brain-update>")
        return 0

    # ─── The detached launch ──────────────────────────────────────────────
    # `start_new_session=True` is NOT a convenience detail: without it the
    # process stays in the session's process group and dies with it. And what it
    # does in the middle is replace the engine — being killed between the
    # `checkout` and `install.sh` leaves a half-switched installation. Detaching
    # is what makes the operation safe to interrupt: the session can close, the
    # update still finishes.
    #
    # Streams go to /dev/null rather than a pipe: a pipe nobody reads eventually
    # fills up and FREEZES the writer. The script writes its own log, it needs
    # nothing else.
    try:
        with open(os.devnull, "r+b") as void:
            subprocess.Popen(
                ["bash", os.path.join(engine, "cbrain", "update.sh"), "--auto"],
                stdin=void, stdout=void, stderr=void,
                start_new_session=True,
                cwd=engine,
            )
    except (OSError, subprocess.SubprocessError):
        pass                    # nothing here justifies getting in a start's way
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # a hook NEVER breaks a session
