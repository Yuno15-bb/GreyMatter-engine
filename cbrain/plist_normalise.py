#!/usr/bin/env python3
"""plist_normalise.py — the ONE normal form for comparing two plists.

SPECIFIED HERE, BEFORE ANY BENCH USES IT, so that "equivalent" cannot be
widened later to make an awkward case pass. The whole rule:

  1. XML comments are removed. The templates carry long explanatory comments;
     a file rendered by an older release differs from today's in its prose and
     in nothing else, and prose is not configuration.
  2. Every line is stripped of leading and trailing whitespace.
  3. Empty lines are dropped.

NOTHING ELSE. No reordering of keys, no case folding, no collapsing of
whitespace inside a value, no ignoring of a key we find inconvenient. A
difference that survives this is a REAL difference, and it must refuse.

Used by cbrain/adopt-launchd.sh on both sides of the comparison, so the two
sides can never drift apart into two definitions of the same word.
"""
import re
import sys


def normalise(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return "\n".join(l.strip() for l in text.splitlines() if l.strip())


if __name__ == "__main__":
    sys.stdout.write(normalise(sys.stdin.read()) + "\n")
