# Capsule — the menu bar pill

A small pill in the macOS menu bar that shows, **in real time**, what the agents
are doing: `idle`, `distilling`, `filing`, `gardening`, `committing`… with an
animated orb whose colour and motion follow the kind of work. Click it and a
panel drops down with the current activity and its detail.

The pill reflects **real** operations: the hooks write `state/status.json` on
every action, and the pill reads it. It is a native Swift program
(`capsule/macos`), built on your Mac by the installer. Until 2.2 the capsule was
an Electron window; that version is retired, and the installer stops it if an
older install left it running.

## Running it

```bash
brain capsule           # open it
brain capsule stop      # close it
brain capsule status    # is it running, is it drawing, is it built
```

The installer builds the pill and starts it once. After a reboot the hooks start
it again at the next session. Launching it twice does not put a second pill in
the menu bar: a lock file (`state/capsule-natif.lock`) keeps it to one.

To keep it off for good (light mode):

```bash
touch ~/.greymatter/trunk/state/no-capsule
```

## Building it

It needs Swift, which comes with Apple's Command Line Tools
(`xcode-select --install`) — no Xcode, no Homebrew, no Node. Without them, the
installer skips only the capsule and says so; everything else works.

The installer builds it for you. By hand:

```bash
cd capsule/macos && swift build -c release && .build/release/Capsule
```

An installed version is never modified after the fact, so the installer builds
into `~/.greymatter/runtime/capsule-native-<hash>/` and the version only holds a
link to it (`capsule/macos/.build`). Two versions with the same sources share
one build; a source that does not compile leaves no binary behind.

## How it works

```
hooks (on_fiche_write / auto_maintain) ──write──▶ ~/.greymatter/trunk/state/status.json
                                                              │
                                                  the pill ───┘  ──▶ orb + label
```

`status.json`: `{ state:"busy"|"idle", activity, detail, source:"agent"|"you", ts, activity_ts }`.

How long the status stays current is defined once, in
`hooks/status_freshness.json`, and read by both the pill and `brain_status.py`:

- no tool call for 30 s (`ts`) → the pill goes back to `idle`;
- no new activity label for 120 s (`activity_ts`) → the pill shows `working`
  and drops the detail, instead of a label that is no longer true.

While its panel is on screen the pill touches `state/capsule-alive` every 5 s.
The hooks rely on that heartbeat, not on the process, to know it is really
drawing.

## Looking at it without a session

```bash
B=capsule/macos/.build/release/Capsule
$B --check                               # what it reads, as one JSON line — no window
$B --image working /tmp/orb.png          # the orb alone, 4× larger, as a PNG
$B --panel-demo working 600 300        # the panel at (600, 300) for 8 s
```

And to walk the real pill through a few states:

```bash
python3 ~/.greymatter/trunk/hooks/brain_status.py busy distilling "extracting <project>"
python3 ~/.greymatter/trunk/hooks/brain_status.py busy filing "filing lessons/pwa-cache"
python3 ~/.greymatter/trunk/hooks/brain_status.py idle
```

## Settings (environment variables)

| Variable | Effect |
|---|---|
| `CAPSULE_BRAIN` | the trunk to read (set by the installer and the hooks) |
| `CAPSULE_VERRE=flou` | use the older blur instead of Liquid Glass on macOS 26 |
| `CAPSULE_TOURNAGE=1` | filming mode: the panel shows a neutral sample, not your live diff |
| `CAPSULE_PASTILLE_SEULE=1` | the panel never opens by itself |
| `CAPSULE_CADENCE=<fps>` | forces the frame rate (benches) |
| `BANC_DUREE=<s>` | runs a bench for that many seconds, prints one JSON line, exits |

## Tests

```bash
python3 tests/capsule_runtime.py    # builds it twice, checks --check, a broken source leaves nothing
python3 tests/capsule_liveness.py   # the pill uses the canonical freshness windows
```

Both need macOS and Swift; elsewhere they say "skipped".
