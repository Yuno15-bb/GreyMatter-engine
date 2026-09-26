# Orb verification bench

Look at the render; never infer it from the code. These scripts lived in `/tmp`
during the 2026-08-03 session — they would have vanished on the next reboot,
while being the only honest way to judge a change to the orb.

## The scripts

| Script | What it does |
|---|---|
| `planche.cjs` | captures `orbe.html` state by state, over three backgrounds |
| `silhouette.cjs` | reads the mesh bounds off the alpha channel, state by state |
| `cadence.cjs` | real frame intervals per state — median AND worst case |
| `film.cjs` | films the README demo — see its three traps at the top of the file |
| `glisse.cjs` | proves the drag chain without moving a real mouse |
| `cycle.sh` | walks the **live** orb through its 13 states, to watch it on the real desktop |

All of them run with the Electron in the parent folder:

```sh
cd ~/.c-brain/trunk/capsule
./node_modules/.bin/electron banc/planche.cjs
```

## The traps that cost time

- **Glass cannot be judged on a black background.** A transparent object is
  indistinguishable from an opaque one there. `planche.cjs` therefore lays down
  a gradient and some text behind it — and a near-WHITE background too, the one
  case where a light label disappears.
- **Bounds come out in SCREEN pixels, not CSS pixels**: capture is retina 2×, so
  a 150 px window renders a 300 px bitmap. Reading them raw places an element at
  twice the intended distance.
- **Wait 2.6 s after a state change**: the mechanic cross-fade lasts 1.4 s, and
  capturing earlier freezes an in-between shape that never really exists.
- **A requested frame rate is not the rate you get.** `cadence.cjs` measures the
  intervals: `setTimeout` followed by `requestAnimationFrame` adds both waits,
  which once turned a requested 60 fps into an actual 32.
- **Kill by full path AND check the count** before any measurement:
  `pgrep -f "c-brain/trunk/capsule" | xargs kill -9`, then count again. A loose
  pattern fails silently and you end up measuring a stale instance.

## The 20/09 trap — the state is SHARED by every Claude session
`film.cjs` and `cycle.sh` drive the orb through `state/status.json`. But every open
Claude session (four in parallel that day) stamps `busy / working` into it on each of
its tool calls, through the `brain_battement.py` hook. One shoot got polluted at 13.7 s:
WORKING barged into the three seconds of rest. "Run nothing meanwhile" is therefore not
enough — the other sessions are not ours to control. **Film in a mirror trunk**:
`HOME=<mirror> BRAIN_HOME=<mirror>/claude-brain`, where the mirror symlinks the whole
trunk except `state/`, which is ours. `orbe.html` resolves everything through
`os.homedir()` and `brain_status.py` through `BRAIN_HOME`: both follow, and the author's
desktop no longer even flickers.
