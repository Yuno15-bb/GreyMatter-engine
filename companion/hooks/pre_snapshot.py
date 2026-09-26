#!/usr/bin/env python3
"""PreToolUse (Write|Edit|MultiEdit|NotebookEdit) — stores the file's before-image.

Without that before-image, a `Write` overwriting an existing file would look like
"everything added": we would lose the BEFORE, the only thing that makes the diff verifiable.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    from companion_lib import (MAX_FILE_BYTES, ensure_dirs, read_hook_input,
                               snap_path, target_path)

    data = read_hook_input()
    sid = data.get("session_id")
    fpath = target_path(data.get("tool_input"))
    if not sid or not fpath:
        return

    ensure_dirs()
    dest = snap_path(sid, fpath)
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    if not os.path.exists(fpath):
        open(dest + ".new", "w").close()      # marker: the file was created from scratch
        open(dest, "w").close()
        return
    try:
        if os.path.getsize(fpath) > MAX_FILE_BYTES:
            open(dest + ".big", "w").close()
            return
        shutil.copyfile(fpath, dest)
        for flag in (".new", ".big"):
            if os.path.exists(dest + flag):
                os.remove(dest + flag)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass          # a broken companion must NEVER get in the way of a session
    sys.exit(0)
