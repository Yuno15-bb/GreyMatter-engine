# Companion — live change tracking, inside the session

**No window.** Two surfaces only:

1. **The session's bottom bar** (the second line of the status line) — permanently
   in the session: number of files touched, cumulative `+`/`−`, the last file
   modified with its balance and age, the app's state, the age of the last reload.
2. **Your browser tab** — reloaded automatically after each burst of
   modifications: that is where you see the **real rendering**, not just the code.

History: a first version displayed an Electron panel glued under the Terminal
window. Abandoned — unreadable, and two sessions produced two floating panels
that covered the work. The code remains in the git history.

---

## Behaviour

| Point | Detail |
|---|---|
| Trigger | `Write` / `Edit` / `MultiEdit` / `NotebookEdit`, in every project |
| Bar | `✎ 9f +879 −239 │ status_part.py +183 −0 2min │ app :3000 │ ↻ 4s` |
| Aggregation | incremental by byte cursor, cached in `agg/<sid>.json` — the bar never re-reads the whole stream |
| Browser | Chrome then Safari, the tab whose URL contains `localhost:<port>`; 1.2 s of silence as debounce, a `mkdir` lock (one reloader only), never steals focus (`open -g`, not `activate`) |
| First launch | if no tab shows the app, it opens **exactly one** (remembered per port), and after that it only reloads |
| Ports probed | `3000 · 5173 · 4321 · 8080 · 8000 · 4200` |
| Session end | an `end` event in the stream, before-images and totals cleaned up |

## Safety and robustness

- **Never blocking**: every hook is wrapped in `try/except` + `sys.exit(0)`, with 5–8 s timeouts; the reloader runs detached. A broken companion leaves your session intact.
- **Secrets**: `.env`, `secrets/`, `*.pem`, `*.key`, `credentials`, `.npmrc`… → the modification is reported, the content is **never displayed**. Elsewhere, any line that looks like a secret is masked value by value.
- **Caps**: diffs truncated at 500 lines, files over 2 MB are not diffed; the stream is purged after 7 days.
- **Append-only**: the event stream is never rewritten wholesale.

## Files

```
companion/
  status_part.py           the second line of the bar (imported by ~/.claude/statusline.py)
  hooks/companion_lib.py   paths, secret masking, stream writing
  hooks/pre_snapshot.py    PreToolUse  → the file's before-image (the diff's "before")
  hooks/post_diff.py       PostToolUse → the real diff + wakes the reloader
  hooks/browser_reload.py  detached     → debounce, then reload the tab
  hooks/session_close.py   SessionEnd  → marks the end, purges streams older than 7 days
```

Runtime state lives in `~/.claude/companion/`: `sessions/<sid>.jsonl` (the
stream), `snap/<sid>/` (before-images), `agg/<sid>.json` (the bar's totals),
`reload.json` (last reload), `port.json` (probe cache).

## Known limits

- **No images in Terminal.app**: there is no inline image protocol. Seeing the rendering *inside* the terminal requires iTerm2 or kitty. Hence the browser.
- **First reload**: macOS asks once for permission to automate Chrome/Safari. If refused, the reload fails silently — the bar stays accurate.
- **Modifications outside the editing tools** (`Bash` with `sed`, `git checkout`, a script): invisible. That would need folder watching.
- The tracker **shows** the change, it does not **validate** it: verification is still the tests and your eyes.

## Disabling it

- The bar: remove the `status_part` block from `~/.claude/statusline.py` (backup at `statusline.py.bak-*`).
- The hooks: remove the three `companion/hooks/*.py` entries from `~/.claude/settings.json` (`PreToolUse`, `PostToolUse`, `SessionEnd`). Backup: `settings.json.bak-c-brain-*`. Or simply run `uninstall.sh`.
