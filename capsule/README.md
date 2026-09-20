# 🥚 Capsule — the trunk's Tamagotchi

A small floating window (Electron, always on top) that **animates in real time**
what the agents are doing: distilling ⚗️, correcting ✏️, filing 📁, pruning 🌿,
updating the map 🗺️.

The animation reflects **real** operations: the hooks write `state/status.json` on
every action, and the capsule reads it twice a second.

## Running it

```bash
brain capsule           # open it
brain capsule stop      # close it
brain capsule status    # is it running, and from where
```

`brain capsule` starts the Electron binary directly, so it works whether or not
`npm` is on your PATH. Launching it twice does not put a second orb on screen:
the one already running is brought back instead.

The installer does the `npm install` for you. By hand, if you need it:

```bash
cd ~/.c-brain/trunk/capsule && npm install && npm start
```

- The creature **sleeps** (zzz) when nothing is happening.
- It **wakes up** with a green halo as soon as the agents work.
- `⌘⇧B`: show / hide the capsule. Drag it anywhere. Hover → an × button.

> If `npm install` returns successfully but Electron will not start, its
> downloader left a truncated archive. Remove `node_modules/electron` and
> reinstall. `install.sh` checks the binary itself and warns you about this.

## How it works

```
hooks (on_fiche_write / auto_maintain) ──write──▶ ~/.c-brain/trunk/state/status.json
                                                              │
                                          capsule (poll 400ms) ┘  ──▶ animation
```

`status.json`: `{ state:"busy"|"idle", activity, detail, source:"agent"|"you", ts }`.

## Testing the animation by hand

```bash
python3 ~/.c-brain/trunk/hooks/brain_status.py busy distilling "extracting <project>"
python3 ~/.c-brain/trunk/hooks/brain_status.py busy filing "filing lessons/pwa-cache"
python3 ~/.c-brain/trunk/hooks/brain_status.py idle
```

Or walk through every activity in one pass:

```bash
python3 ~/.c-brain/trunk/capsule/test_anim.py
```
