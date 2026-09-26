#!/usr/bin/env python3
"""corpus_import — ingests raw chat exports into the trunk's COLD LAYER.

Pipeline (cf. carte-vivante-4-etages) :
  account exports  →  [THIS SCRIPT: lossless COLD layer]  →  embeddings → clusters → SELECTIVE distillation

GUARDRAIL: this script does NOT create warm notes. It normalizes each conversation into ONE cold,
lossless file under corpus/cold/ (gitignored, local only, like the out-of-repo transcripts).
Selective distillation (dense themes → warm notes) is a SEPARATE STEP, never message by message.

Auto-detected sources:
  • ChatGPT  : conversations.json with objects carrying `mapping` (a node tree).
  • Claude   : conversations.json with objects carrying `chat_messages`.
Input: an export .zip, an unpacked folder, or a conversations.json directly. Several accounts =
several imports (pass --account to label them; defaults to the file or folder name).

Zero dependencies (stdlib). Idempotent (registry corpus/.imported.json). Always exits 0.

Usage :
  corpus_import.py <chemin> [--account LABEL] [--dry-run]
  corpus_import.py ~/Desktop/chatgpt-export.zip --account perso
  corpus_import.py ~/Desktop                       # scans the Desktop, imports every export found
"""
import os, sys, re, json, zipfile, hashlib, glob, argparse, io, datetime

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
COLD = os.path.join(BRAIN, "corpus", "cold")
INDEX = os.path.join(BRAIN, "corpus", "INDEX.md")
REG = os.path.join(BRAIN, "corpus", ".imported.json")


# ───────────────────────── helpers ─────────────────────────
def slug(s, n=60):
    s = re.sub(r"[^\w\s-]", "", (s or "").strip().lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return (s or "sans-titre")[:n]


def iso(ts):
    """epoch (float) or ISO string → 'YYYY-MM-DD HH:MM'; '' when unknown."""
    if ts is None or ts == "":
        return ""
    try:
        if isinstance(ts, (int, float)):
            return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        s = str(ts).replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)[:16]


def sort_key(ts):
    try:
        if isinstance(ts, (int, float)):
            return float(ts)
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return float("inf")


# ───────────────────── extraction de texte ─────────────────────
def chatgpt_text(content):
    """content_type text/code/multimodal → readable text (lossless on text; media becomes a placeholder)."""
    if not isinstance(content, dict):
        return str(content or "")
    ct = content.get("content_type", "text")
    if ct == "text":
        return "\n".join(p for p in content.get("parts", []) if isinstance(p, str))
    if ct == "code":
        return "```\n" + (content.get("text", "") or "") + "\n```"
    parts = []
    for p in content.get("parts", []):
        if isinstance(p, str):
            parts.append(p)
        elif isinstance(p, dict):
            parts.append(f"[{p.get('content_type', ct)}]")
    return "\n".join(parts)


CLAUDE_NOISE = "This block is not supported on your current device yet."


def claude_text(msg):
    """Discours PROPRE : reconstruit depuis content[type==text] (le champ `text` top-level inclut
    le thinking + des placeholders d'artefacts → bruit). Fallback `text` pour les vieux exports."""
    parts = [b.get("text", "") for b in (msg.get("content") or [])
             if isinstance(b, dict) and b.get("type") == "text"]
    txt = "\n".join(p for p in parts if p and p.strip()).strip()
    if not txt:
        txt = (msg.get("text") or "").strip()
    return txt.replace(CLAUDE_NOISE, "").strip()


# ───────────────────── normalisation par source ─────────────────────
def parse_chatgpt(conv):
    cid = conv.get("conversation_id") or conv.get("id") or ""
    title = conv.get("title") or "(untitled)"
    created = conv.get("create_time")
    rows = []
    for node in (conv.get("mapping") or {}).values():
        m = node.get("message") if isinstance(node, dict) else None
        if not m:
            continue
        role = (m.get("author") or {}).get("role", "")
        if role not in ("user", "assistant", "system", "tool"):
            continue
        txt = chatgpt_text(m.get("content") or {}).strip()
        if not txt or txt in ("", " "):
            continue
        rows.append((sort_key(m.get("create_time")), role, txt))
    rows.sort(key=lambda r: r[0])
    return {"source": "chatgpt", "id": cid or hashlib.sha1(title.encode()).hexdigest()[:12],
            "title": title, "created": created, "msgs": [(r[1], r[2]) for r in rows]}


def parse_claude(conv):
    cid = conv.get("uuid") or conv.get("id") or ""
    title = conv.get("name") or "(untitled)"
    created = conv.get("created_at")
    rows = []
    for m in conv.get("chat_messages") or []:
        sender = m.get("sender", "")
        role = {"human": "user", "assistant": "assistant"}.get(sender, sender)
        txt = claude_text(m).strip()
        if not txt:
            continue
        rows.append((sort_key(m.get("created_at")), role, txt))
    rows.sort(key=lambda r: r[0])
    return {"source": "claude", "id": cid or hashlib.sha1(title.encode()).hexdigest()[:12],
            "title": title, "created": created, "msgs": [(r[1], r[2]) for r in rows]}


def detect_and_parse(conv):
    if not isinstance(conv, dict):
        return None
    if "mapping" in conv:
        return parse_chatgpt(conv)
    if "chat_messages" in conv:
        return parse_claude(conv)
    return None


# ───────────────────── file discovery ─────────────────────
def load_conversations(path):
    """Returns a list of (account_label, [conversations]) from a zip / folder / json."""
    out = []
    if path.endswith(".zip") and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for nm in z.namelist():
                bn = os.path.basename(nm)
                if bn.startswith("conversations") and bn.endswith(".json"):
                    try:
                        out.append((_label(path), json.loads(z.read(nm).decode("utf-8"))))
                    except Exception as e:
                        print(f"  ⚠ {nm}: {e}", file=sys.stderr)
    elif os.path.isdir(path):
        # `conversations*.json` also matches large split exports (conversations-000.json…)
        for cj in glob.glob(os.path.join(path, "**", "conversations*.json"), recursive=True):
            try:
                out.append((_label(os.path.dirname(cj)), json.load(open(cj, encoding="utf-8"))))
            except Exception as e:
                print(f"  ⚠ {cj}: {e}", file=sys.stderr)
        for zp in glob.glob(os.path.join(path, "*.zip")):
            out += load_conversations(zp)
    elif path.endswith(".json") and os.path.isfile(path):
        try:
            out.append((_label(path), json.load(open(path, encoding="utf-8"))))
        except Exception as e:
            print(f"  ⚠ {path}: {e}", file=sys.stderr)
    # normalize: each payload must be a list of conversations
    norm = []
    for label, payload in out:
        if isinstance(payload, dict) and "conversations" in payload:
            payload = payload["conversations"]
        if isinstance(payload, list):
            norm.append((label, payload))
    return norm


def _label(p):
    base = os.path.basename(p.rstrip("/")) or os.path.basename(os.path.dirname(p))
    base = re.sub(r"\.(zip|json)$", "", base)
    return slug(base, 40)


# ───────────────────── writing the cold layer ─────────────────────
def write_cold(c, account):
    sub = os.path.join(COLD, c["source"], account)
    os.makedirs(sub, exist_ok=True)
    date = iso(c["created"])[:10] or "0000-00-00"
    fn = f"{date}_{slug(c['title'], 50)}_{c['id'][:8]}.md"
    fp = os.path.join(sub, fn)
    lines = ["---",
             f"corpus_source: {c['source']}",
             f"account: {account}",
             f"conv_id: {c['id']}",
             f"title: {json.dumps(c['title'], ensure_ascii=False)}",
             f"created: {iso(c['created'])}",
             f"messages: {len(c['msgs'])}",
             "---", "", f"# {c['title']}", ""]
    icon = {"user": "👤 user", "assistant": "🤖 assistant", "system": "⚙ system", "tool": "🔧 tool"}
    for role, txt in c["msgs"]:
        lines.append(f"## {icon.get(role, role)}")
        lines.append(txt)
        lines.append("")
    open(fp, "w", encoding="utf-8").write("\n".join(lines))
    return os.path.relpath(fp, BRAIN), date


# ───────────────────── orchestration ─────────────────────
def run(paths, account_override, dry):
    reg = {}
    if os.path.exists(REG):
        try:
            reg = json.load(open(REG, encoding="utf-8"))
        except Exception:
            reg = {}
    stats = {}          # (source,account) -> [imported, skipped, msgs]
    index_rows = []
    for path in paths:
        for label, convs in load_conversations(path):
            account = account_override or label
            for raw in convs:
                c = detect_and_parse(raw)
                if not c or not c["msgs"]:
                    continue
                key = f"{c['source']}:{c['id']}"
                src_acc = (c["source"], account)
                stats.setdefault(src_acc, [0, 0, 0])
                if key in reg:
                    stats[src_acc][1] += 1
                    continue
                stats[src_acc][0] += 1
                stats[src_acc][2] += len(c["msgs"])
                if not dry:
                    rel, date = write_cold(c, account)
                    reg[key] = rel
                    index_rows.append((date, c["source"], account, c["title"], len(c["msgs"]), rel))
    # rapport
    print(f"\n{'🔬 DRY-RUN — nothing written' if dry else '🧊 cold-layer import'}:")
    tot_i = tot_s = tot_m = 0
    for (src, acc), (i, s, m) in sorted(stats.items()):
        print(f"  • {src:8} [{acc}] : {i} new ({m} msgs), {s} already imported")
        tot_i += i; tot_s += s; tot_m += m
    if not stats:
        print("  (no conversation found — check the path and the export format)")
    print(f"  ─ total: {tot_i} new · {tot_m} messages · {tot_s} skipped (already there)")
    if dry:
        return
    json.dump(reg, open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    _update_index(index_rows)
    print(f"\n  → couche froide : {os.path.relpath(COLD, BRAIN)}/  ·  registre : {len(reg)} conversations")
    print("  Next step: corpus embeddings → clusters → selective distillation.")


def _update_index(new_rows):
    header = ("# 🧊 Corpus froid — 4 ans de discussions (lossless, local-only)\n\n"
              "> Index of the COLD layer. One line = one conversation normalized into `corpus/cold/`.\n"
              "> The distilled layer (warm notes) is SEPARATE and selective. Gitignored.\n\n"
              "| date | source | compte | titre | msgs | fichier |\n|---|---|---|---|---|---|\n")
    existing = ""
    if os.path.exists(INDEX):
        txt = open(INDEX, encoding="utf-8").read()
        i = txt.find("\n|---")
        existing = txt[txt.find("\n", i + 1) + 1:] if i != -1 else ""
    rows = "".join(f"| {d} | {s} | {a} | {t[:60].replace('|', '/')} | {m} | {f} |\n"
                   for d, s, a, t, m, f in sorted(new_rows, reverse=True))
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    open(INDEX, "w", encoding="utf-8").write(header + rows + existing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--account", default=None, help="account label (defaults to the file name)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    paths = [os.path.realpath(os.path.expanduser(p)) for p in a.paths]
    run(paths, a.account, a.dry_run)


if __name__ == "__main__":
    main()
    sys.exit(0)
