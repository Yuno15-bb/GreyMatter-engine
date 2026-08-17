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

```bash
HOME=$T CAPSULE_DEV=1 <repo>/capsule/node_modules/.bin/electron <repo>/capsule \
  --user-data-dir=$T/electron-data &
HOME=$T python3 $T/.c-brain/trunk/hooks/brain_status.py busy distilling "test"
sleep 3; touch /tmp/cap_shot_req; sleep 3   # → /tmp/cap.png
```

**Expected**: the capture shows `DISTILLING` plus the detail. Switch back to
`idle` and the next capture shows `IDLE`.

> `--user-data-dir` is mandatory: without it the second instance quits silently
> because of the single-instance lock, and you think the capsule is broken.

> If Electron will not start: its downloader sometimes leaves a truncated
> archive while still exiting successfully. `install.sh` now detects this and
> says so. Remedy: delete `capsule/node_modules/electron` and reinstall.

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

An updater does destructive git: it checks out a release tag over your engine. It
is allowed to do that **only** on an engine the installer owns, recorded in
`state/engine-managed` and written only from a clean checkout detached on a
release tag. Anywhere else it must refuse and change nothing at all.

Point `~/.c-brain/engine` at a repository you work in, and check each refusal:

- [ ] **uncommitted changes** → refuses, names the files, discards nothing;
- [ ] **on a branch** → refuses; a managed install sits detached on its tag;
- [ ] **no marker**, and not on a release tag → refuses;
- [ ] **marker naming another engine** → refuses.

After each one, the repository must be **bit-identical** — HEAD, branch, working
tree and index:

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
