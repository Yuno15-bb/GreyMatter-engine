#!/usr/bin/env python3
"""Check that each visible GMTR keyboard hint has a listener on that page."""
from pathlib import Path
import importlib.util
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
ZONE = ROOT / "gmtr"
KEYS = {"esc": "escape", "escape": "escape", "tab": "tab", "enter": "enter",
        "space": " ", "shift": "shift", "ctrl": "control", "alt": "alt", "cmd": "meta"}
SRC = re.compile(r"<script[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)
INLINE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.I | re.S)
STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.I | re.S)
CSS = re.compile(r"<link[^>]*\bhref=[\"']([^\"']+\.css)[\"']", re.I)
HINT = re.compile(r"<b>([^<]{1,8})</b>")
LISTEN = re.compile(r"\.key\s*[!=]==?\s*[\"']([^\"']+)[\"']")
INCLUDES = re.compile(r"[\"']([A-Za-z]{2,12})[\"']\s*\.includes\(\s*\w+\.key")


def resolve(page, href):
    href = href.split("?")[0].split("#")[0]
    if href.startswith(("http://", "https://", "//", "data:")):
        return None
    base = ZONE if href.startswith("/") else page.parent
    target = (base / href.lstrip("/")).resolve()
    return target if target.is_file() and (ZONE == target or ZONE in target.parents) else None


def hidden_ids(styles):
    hidden = set()
    for text in styles:
        for selector, block in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
            compact = block.replace(" ", "")
            if "display:none" in compact or "visibility:hidden" in compact:
                hidden.update(re.findall(r"#([A-Za-z][-\w]*)", selector))
    return hidden


def main():
    spec = importlib.util.spec_from_file_location("gmtr_builder", ZONE / "carte" / "fabriquer.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.fabriquer()
    failures, checked, pages = [], 0, 0
    for page in sorted(ZONE.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        pages += 1
        scripts = {page: html}
        for source in SRC.findall(html):
            path = resolve(page, source)
            if path:
                scripts[path] = path.read_text(encoding="utf-8")
        styles = STYLE.findall(html)
        for href in CSS.findall(html):
            path = resolve(page, href)
            if path:
                styles.append(path.read_text(encoding="utf-8"))
        heard = set()
        for text in INLINE.findall(html) + [s for p, s in scripts.items() if p != page]:
            heard.update(key.lower() for key in LISTEN.findall(text))
            for group in INCLUDES.findall(text):
                heard.update(key.lower() for key in group)
        hidden = hidden_ids(styles)
        for path, text in scripts.items():
            for match in HINT.finditer(text):
                word = match.group(1).strip().lower()
                key = word if len(word) == 1 and word.isalpha() else KEYS.get(word)
                if key is None:
                    continue
                near = text[max(0, match.start() - 500):match.start()]
                ids = re.findall(r"\bid=[\"']([A-Za-z][-\w]*)[\"']", near)
                if ids and ids[-1] in hidden:
                    continue
                checked += 1
                if key not in heard:
                    failures.append(f"{path.relative_to(ROOT)}: {page.relative_to(ROOT)} promises {word} without a listener")
    if failures:
        print("RED — " + "\nRED — ".join(failures))
        return 1
    print(f"PASS — {checked} visible keyboard hints across {pages} GMTR pages have listeners")
    return 0


if __name__ == "__main__":
    sys.exit(main())
