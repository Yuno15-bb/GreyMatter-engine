#!/usr/bin/env python3
"""i2_dependencies — what a verdict actually depends on, observed rather than declared.

I-2 asks a question that neither I-1 nor I-3 asks:
    "Does a normative verdict depend on external state, local state, or execution order
     that is not declared in the experiment's identity?"

METHOD — inspect what the code OPENS instead of interrogating its source.
`sys.addaudithook` captures every `open()` in this process: path and mode. This gives
the actual files read and written, including accesses hidden by imports, caches, and
paths built by concatenation.

CLASSES
    I2-A  versioned / intrinsic to the experiment
    I2-B  external but explicitly injected
    I2-C  external, intentionally local, ANNOUNCED
    I2-D  external and SILENTLY influencing the verdict     <- red
    I2-E  side effect from another test / order dependency  <- red
    I2-F  unknown

KNOWN LIMIT: the audit hook sees only this process. A test that launches a child process
(verifier -> golden_recall) hides that child's file accesses. This limitation is stated
here rather than discovered later.

Usage: i2_dependencias.py <script.py> [args...]     trace an instrument
"""
import json
import os
import sys

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME")
                         or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

TRACE = {"read": set(), "written": set()}


def _hook(event, args):
    if event != "open":
        return
    path, mode = args[0], args[1]
    if not isinstance(path, str) or not path.startswith("/"):
        return
    # Interpreter bytecode caches are not verdict dependencies: they are reconstructible,
    # content-independent, and polluted the I2-D class with 4 to 19 entries per instrument.
    # An instrument that reports noise will eventually be ignored.
    NOISE = ("/lib/python", "site-packages", "/usr/", "encodings",
             "Library/Caches/com.apple.python", "__pycache__", ".pyc")
    if any(item in path for item in NOISE):
        return
    (TRACE["written"] if mode and any(char in str(mode) for char in "wax+")
     else TRACE["read"]).add(path)


def classify(path, tracked):
    rel = os.path.relpath(path, BRAIN) if path.startswith(BRAIN + "/") else None
    if rel and rel in tracked:
        return "I2-A"
    if rel and rel.startswith("state/"):
        return "I2-D"                      # outside git but inside the measured tree
    if path.startswith(os.path.expanduser("~")) and not path.startswith(BRAIN):
        return "I2-D"
    if rel:
        return "I2-F"                      # in the repository but untracked: generated or missed
    return "I2-C"                          # outside repository and home: temporary or system


def main():
    target = sys.argv[1]
    sys.argv = sys.argv[1:]
    import subprocess
    tracked = set(subprocess.run(["git", "-C", BRAIN, "ls-files"],
                                 capture_output=True, text=True).stdout.split())
    state_dir = os.path.join(BRAIN, "state")
    before_state = set(os.listdir(state_dir)) if os.path.isdir(state_dir) else set()
    sys.addaudithook(_hook)
    code = 0
    try:
        import runpy
        runpy.run_path(target, run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
    except BaseException as exc:
        code = type(exc).__name__
    after_state = set(os.listdir(state_dir)) if os.path.isdir(state_dir) else set()

    result = {"instrument": os.path.relpath(target, BRAIN), "code": code,
              "created_in_state": sorted(after_state - before_state), "read": {}, "written": {}}
    for key in ("read", "written"):
        for path in sorted(TRACE[key]):
            result[key].setdefault(classify(path, tracked), []).append(
                os.path.relpath(path, BRAIN) if path.startswith(BRAIN + "/") else path)
    print("§§I2§§" + json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
