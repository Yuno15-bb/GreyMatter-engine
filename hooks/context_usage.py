#!/usr/bin/env python3
# Written with Codex
"""Fail-open reading of the context footprint of a Claude Code transcript."""

import json
import os


def usage_tokens(usage):
    """Sum of the tokens that make up the context re-read by the current call."""
    if not isinstance(usage, dict):
        return None
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def read_context_tokens(transcript_path):
    """Return the transcript's last usage, or ``None`` when unavailable."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    last = None
    try:
        with open(transcript_path, encoding="utf-8") as transcript:
            for line in transcript:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                usage = (obj.get("message") or {}).get("usage")
                if usage:
                    last = usage
    except OSError:
        return None
    return usage_tokens(last)
