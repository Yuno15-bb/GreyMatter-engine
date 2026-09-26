#!/usr/bin/env python3
"""Keep recall silent by default and useful when explicitly requested.

The test checks both search thresholds, the recorded rule, and four internal
sabotages. The former private dispatcher blind spot is gone with the v2-only
hook. This does not judge whether the thresholds themselves are optimal.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "inject_recall.py"
AUTO, DEMAND = 4.0, 1.0

NOTES = {
    "zorglub-planning": "The zorglub planning is reviewed before every measurement. " * 8,
    "zorglub-failure": "When a zorglub fails, review the planning before changing it. " * 8,
    "brain-search": "Search the brain for a note; the brain search finds a note. " * 8,
    "brain-notes": "A brain note describes how to search the brain for notes. " * 8,
}
DISTRACTORS = {
    f"other-{n}": f"Unrelated topic {n}: painting, bicycles, bread, gardens, music and photos. " * 3
    for n in range(14)
}


def trunk(parent):
    path = parent / "trunk"
    (path / "lessons").mkdir(parents=True)
    (path / "state").mkdir()
    for name, body in {**NOTES, **DISTRACTORS}.items():
        (path / "lessons" / f"{name}.md").write_text(
            f'---\nname: {name}\ndescription: "{body}"\n---\n\n{body}\n', encoding="utf-8")
    return path


def run(hook, brain, prompt, auto=False):
    env = dict(os.environ, BRAIN_HOME=str(brain))
    env.pop("BRAIN_RECALL_AUTO", None)
    if auto:
        env["BRAIN_RECALL_AUTO"] = "1"
    proc = subprocess.run([sys.executable, "-B", str(hook)],
                          input=json.dumps({"prompt": prompt, "session_id": "RECALL-TEST"}),
                          text=True, capture_output=True, env=env)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def lines(brain, name):
    path = brain / "state" / name
    return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []


def sabotaged(parent, substitutions):
    """Place a disposable hook beside links to its local imports."""
    directory = parent / "hook-copy"
    directory.mkdir(exist_ok=True)
    for source in (ROOT / "hooks").glob("*.py"):
        if source.name != HOOK.name:
            if not (directory / source.name).exists():
                (directory / source.name).symlink_to(source)
    source = HOOK.read_text(encoding="utf-8")
    for before, after in substitutions:
        assert before in source, f"sabotage target missing: {before!r}"
        source = source.replace(before, after, 1)
    hook = directory / HOOK.name
    hook.write_text(source, encoding="utf-8")
    return hook


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print("  OK", label)


def main():
    source = HOOK.read_text(encoding="utf-8")
    def value(name):
        match = re.search(rf"^{name}\s*=\s*([0-9.]+)", source, re.M)
        return float(match.group(1)) if match else None
    check((value("MIN_SCORE"), value("MIN_SCORE_DEMAND")) == (AUTO, DEMAND),
          "declared thresholds")
    with tempfile.TemporaryDirectory(prefix="recall-on-request-") as tmp:
        base = Path(tmp)
        brain = trunk(base)
        ordinary = "zorglub planning measurement review"
        out = run(HOOK, brain, ordinary)
        check("<brain-recall>" not in out, "ordinary message stays silent")
        shape = lines(brain, "query-shape.jsonl")
        check(len(shape) == 1 and shape[-1].get("threshold") == AUTO
              and shape[-1].get("requested") is False, "silent search logs its rule")
        check(not lines(brain, "recall_log.jsonl"), "nothing unseen is logged as shown")
        check("zorglub-planning" in run(HOOK, brain, ordinary, auto=True),
              "automatic mode has a real result")
        check("zorglub-planning" in run(HOOK, brain, "?brain zorglub planning"),
              "marker opens recall")
        check("zorglub-planning" in run(HOOK, brain, "search my notes for zorglub planning"),
              "English request opens recall")
        check("zorglub-planning" in run(HOOK, brain, "cherche dans le brain zorglub planning"),  # i18n-ok: input tests French requests.
              "French request opens recall")
        shape = lines(brain, "query-shape.jsonl")[-1]
        check(shape.get("threshold") == DEMAND and shape.get("requested") is True,
              "explicit request logs its lower threshold")
        check("Nothing relevant found" in run(HOOK, brain, "?brain xylophone quadrature"),
              "unanswered request says so")
        check("<brain-recall>" not in run(HOOK, brain, "xylophone quadrature", auto=True),
              "automatic mode remains silent without results")
        check(all(run(HOOK, brain, text) == "" for text in ("ok", "")),
              "short and empty prompts are harmless")

        hook = sabotaged(base, [("if results and show:", "if results:")])
        check("<brain-recall>" in run(hook, brain, ordinary),
              "sabotage 1 exposes automatic chatter")
        hook = sabotaged(base, [("query = clean_query(prompt) if requested else prompt", "query = prompt"),
                                ("threshold = MIN_SCORE_DEMAND if requested else MIN_SCORE", "threshold = MIN_SCORE")])
        out = run(hook, brain, "cherche dans le brain zorglub planning")  # i18n-ok: input tests French requests.
        check("brain-search" in out or "brain-notes" in out or "zorglub-planning" not in out,
              "sabotage 2 pollutes the French request")
        hook = sabotaged(base, [('threshold=threshold, requested=requested)',
                                 'threshold=None, requested=requested)')])
        run(hook, brain, ordinary)
        check(lines(brain, "query-shape.jsonl")[-1].get("threshold") is None,
              "sabotage 3 removes the logged rule")
        hook = sabotaged(base, [('    p = _fold(prompt)\n    if _fold(MARKER) in p:',
                                 '    if os.environ.get("BRAIN_RECALL_AUTO") == "1":\n'
                                 '        return True\n    p = _fold(prompt)\n    if _fold(MARKER) in p:')])
        run(hook, brain, ordinary, auto=True)
        check(lines(brain, "query-shape.jsonl")[-1].get("threshold") == DEMAND,
              "sabotage 4 makes automatic mode too lenient")
    print("recall on request: invariant and four sabotages passed")


if __name__ == "__main__":
    main()
