# Verification recipe

Replay this **before every published tag**. Everything happens inside an isolated
`HOME`: no step touches the real machine.

The order matters: each step assumes the previous one is green.

## 0. The extraction chain (on the `fr` branch)

```bash
cd ~/c-brain-fr        # the `fr` working copy — `git worktree add ~/c-brain-fr fr`
./sync.sh --check      # rc=0 → the package matches the living Brain
./sync.sh              # copy + generalization, chained
python3 leakcheck.py --history
```

**Expected**: `✅ CLEAN`. A single marker and nothing ships.

> The positive control matters as much as the green: modify a file in the source
> Brain, re-run `./sync.sh --check`, it must exit 1. A green that can never turn
> red proves nothing.

> On `main`, `sync.sh` refuses to run — see [`translation.md`](translation.md).

## 1. Install from a real CLONE

**Never from a copied folder.** Cloning is what reveals what `.gitignore`
swallows — an unanchored pattern once made the whole trunk skeleton disappear,
which was invisible when copying.

```bash
T=/tmp/iso-c-brain; rm -rf $T; mkdir -p $T/.claude $T/Desktop
git clone https://github.com/Yuno15-bb/c-brain $T/dev-c-brain
HOME=$T bash $T/dev-c-brain/install.sh --no-launchd
```

**Expected**: `✅ selftest OK`, `✅ doctor — tree consistent`, `✅ C Brain installed.`
followed by `▸ Your trunk is empty.` — and *only* on a genuinely empty trunk. On a
re-install over notes it must read `▸ Your trunk is already growing.` instead. That
line had no test at all until 2026-08-16: it announced an empty trunk to somebody
holding 23 notes, and then offered `brain demo`, which writes into a live trunk.

## 2. Non-destructive and idempotent

Write a `settings.json` holding a model, a theme and a personal hook, then:

```bash
HOME=$T bash $T/dev-c-brain/install.sh      # second pass
```

**Expected**: "already linked" everywhere, `settings.json — nothing to do`. The
personal hook, the model and the theme are all still there.

## 3. The full life cycle

```bash
echo "test note" > $T/.c-brain/trunk/lessons/test.md
HOME=$T bash $T/dev-c-brain/uninstall.sh --yes
```

**Expected**: the note still exists, `settings.json` is **identical to its
original state**, the engine symlinks are gone.

## 4. Every CLI command

```bash
for c in version status doctor audit review next "recall memory" coherence utility \
         credit demo "demo --remove" selftest; do
  HOME=$T bash -c "PATH=\$HOME/.local/bin:\$PATH; brain $c" >/dev/null || echo "FAILED: $c"
done
```

**Expected**: nothing printed. Then read the output of `brain audit` and
`brain review` with your eyes — French strings without accents slip past every
grep, and only reading catches them.

> `demo` and `demo --remove` go together, in that order. `demo` alone leaves its
> notes in the trunk, and every later step would then be measuring a trunk this
> recipe filled itself.

## 5. Capsule

⚠️ **The procedure that used to be written here did not exist.** It told you to
`touch /tmp/cap_shot_req` and read `/tmp/cap.png`; grepping the whole tree on
2026-08-17 found that string in this file and nowhere else. The documented way to
verify the capsule could not be run, and nobody noticed because nobody ran it.
What follows is the mechanism that was then built, and exercised.

```bash
export CBRAIN_PROBE_OUT=$T/probe.json      # opt-in; nothing is written without it
HOME=$T "$ENGINE/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" \
  "$ENGINE/capsule" --user-data-dir=$T/electron-data &
HOME=$T python3 $T/.c-brain/trunk/hooks/brain_status.py busy distilling "test"
sleep 6; cat $T/probe.json
```

**Expected**: `state_text: "DISTILLING..."`, `detail_text: "test"`,
`state_visible: true`, `renderer_ready: "complete"`, and `engine_dir` pointing
under `~/.c-brain/versions/`. Set `idle` and both texts go empty with
`state_visible: false` — measured, and that difference is what makes the probe a
sensor rather than a constant.

> ⚠️ **This is the RENDERER's opinion, not the screen.** It says what the DOM
> holds. A renderer can be certain it is drawing an orb nobody can see, and — the
> trap this whole section exists for — a screenshot can show an orb no renderer
> is drawing, because macOS keeps ghost layers. The two observables do not
> substitute for one another. The pixel half is `tests/a1_capsule_pixel.sh`, and
> it refuses to run until it has proved its own sensor can see.

> `--user-data-dir` is mandatory: without it the second instance quits silently
> because of the single-instance lock, and you think the capsule is broken.

> If Electron will not start, do **not** reach for `npm install` again — that is
> the step that fails. Measured on 2026-08-17 (Node 26, npm 11): the archive
> downloads intact, the postinstall runs, ends in one second, exits 0, and
> extracts 20 directory entries before stopping at the first real file. `dist/`
> stays at 256 KB with no `Frameworks/`, and `path.txt` never appears. The binary
> then aborts with *Library not loaded: Electron Framework*.
> `install.sh` now unpacks the downloaded archive itself and only reports success
> after the binary answers `--version`. Re-running the installer is the remedy.

**Do not stop at "the process started".** A half-extracted Electron starts too.
The chain to check, in order:

- [ ] `…/Electron.app/Contents/MacOS/Electron --version` answers;
- [ ] `dist/` is ~250 MB and `Frameworks/Electron Framework.framework` exists;
- [ ] `path.txt` reads exactly `Electron.app/Contents/MacOS/Electron`, **no newline**
      (electron compares it with a strict `!==`; a stray `\n` makes every later
      `npm install` redo the extraction that fails);
- [ ] the process is alive;
- [ ] the **renderer** loaded and built its DOM — not just the main process.

> ⚠️ **Screenshots of the orb are not a reliable sensor.** macOS keeps ghost
> layers of these transparent always-on-top windows: a capture taken after every
> capsule process was killed still showed an orb. Verify the renderer's own DOM,
> and keep the pixel check for a clean graphics session.

## 6. Planet

```bash
HOME=$T bash $T/.c-brain/trunk/planet/launch.sh 8799 &
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8799/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8799/graph.json
```

**Expected**: `200` twice. For visual proof, a headless capture (Chromium
`--use-gl=angle --use-angle=swiftshader`) must show the globe, the starfield and
the agent legend — **and no French text**. Two strings without accents once
survived every grep and were only caught on a rendered screenshot.

## 7. Companion

```bash
J='{"session_id":"t","tool_input":{"file_path":"'$T'/demo.py"}}'
echo "$J" | HOME=$T python3 $T/.c-brain/trunk/companion/hooks/pre_snapshot.py
# … modify the file …
echo "$J" | HOME=$T python3 $T/.c-brain/trunk/companion/hooks/post_diff.py
echo '{"session_id":"t","model":{"display_name":"X"},"workspace":{"current_dir":"/tmp"}}' \
  | HOME=$T python3 $T/.claude/statusline.py
```

**Expected**: **two** lines, the second showing the file count and the `+`/`−`
balance.

## 7 bis. The local history — prove the observable, not `.git`

A fresh install must leave a trunk whose changes are recorded, or say plainly that
they are not. Checking that `.git/` exists proves nothing: what is promised is that
a note you wrote can be read back.

```bash
HOME=$T bash install.sh --no-launchd --no-capsule | grep "history"
# write a note in $T/.c-brain/trunk/lessons/, then:
python3 $T/.c-brain/trunk/hooks/commit_par_zone.py
git -C $T/.c-brain/trunk show HEAD:lessons/<your-note>.md
```

- [ ] the installer states the history is **ON** (or **OFF**, with the reason);
- [ ] writing a note produces a commit;
- [ ] `git show` returns the note's **text** — recovering it is the promise;
- [ ] on a trunk with no git, the save says so and exits **0** (nothing is lost);
- [ ] `brain backup` on such a trunk **explains**, instead of `fatal: not a git repository`.

> ⚠️ It is a **history**, not a backup: one disk, no remote, and the package pushes
> nowhere. And **trunk git is not engine git** — `brain update` must never look at it.

## 8. Updates — the test that matters most

Set up a local bare remote, publish two tags, install the first, write a note,
then update.

```bash
git init --bare /tmp/remote.git
# … push v1.0.0, install, write a note …
# … push v1.1.0 with a migration and a visible change …
HOME=$T brain update
```

**Expected, in this order**:

- [ ] the user's note is **intact**;
- [ ] the code change **arrived** (symlinks propagate instantly);
- [ ] the migration ran **exactly once** and is in the log;
- [ ] `brain version` returns the new tag;
- [ ] a second `brain update` says "already up to date" and does **not** replay the migration;
- [ ] `brain update --rollback` returns to the previous version, selftest green, note still there.

> Remember: it is the **installed** updater that runs. A fix in `update.sh` only
> protects users already on that version or later. Think twice before publishing
> a change to the updater itself.

### What it must REFUSE — the other half of the test

An updater replaces the engine. It is allowed to do that **only** on an engine
the installer BUILT — a directory under `~/.c-brain/versions/`, recorded in
`state/engine-managed`. Anywhere else it must refuse and change nothing at all.

⚠️ This used to read "it checks out a release tag over your engine", and the
refusals below used to be about git state — dirty, on a branch, not on a tag.
That was the old model, and inferring ownership from git state is what made the
documented install permanently un-updatable (chantier #9, 2026-08-17). There is
no longer any git command in the update path that names a directory a user made.
See [install-model.md](install-model.md).

Point `~/.c-brain/engine` at a repository you work in, and check each refusal:

- [ ] **no marker** → refuses; there is no adoption path any more;
- [ ] **engine outside `versions/`** → refuses, even with a valid marker;
- [ ] **marker naming another root** → refuses;
- [ ] **`state/engine-dev` present** → refuses **by name**: "Development engine
      detected", not a generic ownership error — a developer sent looking for a
      marker to create is being handed the wrong problem;
- [ ] **the active version no longer matches its `.cbrain-manifest`** → refuses,
      and does **not** repair it: something wrote to a frozen tree, and
      overwriting it would destroy whatever that was.

And the half that matters just as much — a gate that refuses everywhere is an
outage, not a fix:

- [ ] a **real managed install** still updates, switches, and rolls back.

### The conversion, on an installation that predates versions/

An installation from v1.28.1 or earlier arrives with `~/.c-brain/engine` pointing
at the user's own clone and leaves with it pointing at a built version — inside
an automatic update nobody watched. Point `engine` at a checkout, run the
installer, and check that it **says so**:

```bash
ln -s /path/to/a/checkout ~/.c-brain/engine     # in a THROWAWAY $HOME
HOME=$T bash install.sh --core-only | grep -A3 converted
```

- [ ] it names what the checkout **was**, what the engine **is now**, and that
      `brain update` will not touch the checkout again;
- [ ] the checkout itself is bit-identical afterwards;
- [ ] running the installer a **second** time says nothing — a conversion notice
      that fires on every re-install is noise, and noise is not read.

And the warning that goes with it: [UPGRADING.md](UPGRADING.md) is the one-time
notice about what the OLDER updater does on its last run. Check the detection
line it gives actually discriminates:

- [ ] `git -C ~/.c-brain/engine status --short` **lists files** on a checkout
      engine with uncommitted changes;
- [ ] the same command answers `fatal: not a git repository` on a managed engine
      — there, the error is the good news, and the note must say so.

`tests/update_ownership.py` runs all of the above in seconds;
`tests/e2e_install_update.sh` runs the whole chain for real, from `git clone` to
rollback, and is the only one that proves `install.sh` writes the marker itself.

After each refusal, the repository must be **bit-identical** — HEAD, branch,
working tree and index:

```bash
git -C <engine> rev-parse HEAD; git -C <engine> rev-parse --abbrev-ref HEAD
git -C <engine> write-tree;     git -C <engine> status --porcelain
```

> Why this half exists: on 2026-08-17 an update run from a sandbox install whose
> engine pointed at the development repo rewound it past four commits and detached
> HEAD, and an earlier version discarded uncommitted work under `hooks/` outright.
> `tests/update_ownership.py` now holds all of it on five real repositories.

## 9. Publish

```bash
./publish.sh v1.2.3 "what this version changes"
```

It refuses to push if the package has drifted, if the tree is dirty, if the leak
check is red, or if the tag already exists. **Never bypass it** — that guard
exists precisely because a leak check once ran at the end of a pipe, where `tail`
always succeeds and the exit code tested was the wrong one.

It also **refuses** when a document has not been reviewed since the code it
describes moved:

```bash
python3 tests/docs_aligned.py
```

Prose has no test, so it never fails — it keeps rendering while describing a
program that stopped behaving that way. This check does not read the prose and
does not judge whether a sentence is true; it asks whether a watched path moved
after the document was last edited. Re-aligning is not a command: you open the
document and edit it, and that commit is the new baseline.
