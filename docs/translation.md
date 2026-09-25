# Two branches, one engine

`main` is **English**. `fr` is **French**, and it is the branch the engine is
extracted onto.

```
~/claude-brain (French)  ──sync.sh──▶  fr  ──translation──▶  main (English)
     the living Brain                                         what people install
```

## Why this direction and not the other

The source Brain is written in French: its hooks, its agent prompts, its
comments. `sync.sh` copies from it and `generalize.py` rewrites it with rules
that **match French strings**. Neither can run against English files.

So English cannot be the sync target. It is derived from `fr`, one step later.

## The guard

`./sync.sh` **refuses to run on `main`**. Without that guard, one sync would
silently overwrite every translated file with its French original — and nothing
would catch it: no test reads prose. Only a reader would notice, much later.

```
❌ ./sync.sh runs on the `fr` branch, not on `main`.
```

`CBRAIN_ALLOW_SYNC_ON_MAIN=1` forces it, for the rare case where you know why.

## What the sync does NOT take

Some files live **only in the package** and are excluded from the sync, because
`rsync --delete` would wipe them on the first pass:

| File | Why it is not in the living Brain |
|---|---|
| `hooks/hooks.json` | the Claude Code plugin's hook manifest |
| `tests/plugin_manifest.py` | checks the package's own manifests |
| `tests/plugin_install.sh` | installs the package as a plugin, end to end |
| `tests/english_only.py` | watches the translation, on `main` only |
| `tests/update_tag_family.sh` | the tag families a user can be updated across |
| `tests/update_rollback.sh` | a bad update, and the way back |
| `tests/recall_benchmark.py` | recall speed, held to a number |
| `tests/recall_cache.py` | the recall cache invalidates when it should |
| `tests/docs_aligned.py` | has the code a doc describes moved since it was written |
| `tests/e2e_occupied_surfaces.sh` | installing over surfaces somebody else already holds |
| `capsule/test_lock_speaks.sh` | measures the package's own `capsule/main.js`, in English. The author's trunk has a French twin, `test_verrou_parle.sh`, measuring the author's own `main.js`: two benches, not one file translated, so both are excluded — one so the copy cannot overwrite the English bench, the other so `--delete` cannot erase it |
| `capsule/main.js`, `index.html`, `dock-geometry.js`, `test_dock_geometry.js` | the capsule as the package ships it, frozen on both sides |

This is the worst failure mode available here: an erased `hooks.json` does not
crash — the plugin simply **stops recording**.

**The list only grows, and every addition has to be made twice** — once as an
`rsync --exclude`, once in the fingerprint that `--check` compares. A file
excluded on one side only never moves but still counts as changed, so the drift
report stays red forever and says nothing useful about why.

## Workflow when the Brain evolves

**Two working copies, not one branch you keep switching.** `sync.sh` refuses to
run anywhere but `fr`; the working copy you edit sits on `main`; and switching
branches under someone who is mid-edit is worse than doing nothing. So `fr` gets
a working copy of its own, where the guard is already satisfied — satisfied, not
bypassed:

```bash
git worktree add ~/c-brain-fr fr     # once
```

```bash
cd ~/c-brain-fr
./sync.sh                  # copy + generalize, French
python3 leakcheck.py       # must be green
git commit -am "sync: <what moved>"

cd ~/c-brain            # the `main` working copy — no branch switching
git diff fr@{1} fr -- .    # what actually changed
# port those changes, translated, onto main
python3 leakcheck.py --history
./publish.sh v1.2.0 "..."
```

Read the diff before translating. Most syncs move a handful of lines; a blind
`git merge fr` would drag the whole French tree back onto `main`.

**The first half now runs on its own** (2026-08-15). At session end the author's
machine copies, leak-checks, commits and pushes `fr` without being asked. The
tool that does it is not in this package on purpose: it pushes, and it knows this
repository's branches. A user who added a remote to their own trunk never asked
for their private notes to be pushed at the end of every session.

**The second half — translating onto `main` — stays manual, and cannot be
automated.** It is the step that needs someone to read.

## `main` is the product, `fr` is a staging buffer (2026-08-13)

`fr` used to be a released product of its own, with a `-fr` tag family. It is not
any more. It stays exactly what it always really was: **the French landing strip
of the sync**, read by nobody but the translation step.

Two costs decided it, both measured the same day:

- **The tag families collide by sorting.** `sort -V` places `v1.27.0-fr` AFTER
  `v1.27.0`, so any "latest tag" selector scanning every tag moves an English
  install onto the French tree — no error, the tool just starts speaking another
  language. It stayed invisible only while `fr` lagged behind; bringing the two
  level is what ARMED it.
- **`fr` cannot ship without a clean sync.** Publishing from `fr` requires the
  author's living Brain to match the package. Unfinished work on that machine
  therefore blocks a release that has nothing to do with it.

`publish.sh` now refuses to tag from `fr` (`CBRAIN_ALLOW_TAG_ON_FR=1` forces it,
for the rare case where you know why). Published tags stay published — moving one
breaks the fetch of anyone still on it — so the `-fr` family simply stops growing
at `v1.27.0-fr`.

**What does NOT change**: the direction of the pipeline. The living Brain is
French and `generalize.py` matches French strings, so the sync still lands on
`fr` first and `main` is still translated from it by a human reading a diff.
`fr` is a step, no longer a destination.

## Tags

| Branch | Tags | Who installs it |
|---|---|---|
| `main` | `v1.2.0` | everyone, by default |
| `fr` | `v1.2.0-fr` | French speakers who ask for it |

⚠ **This used to be stated the wrong way round, and it was a real bug.** The
earlier text claimed each install stayed in its own language "as long as each
clone tracks its own branch". That reasoning does not hold: `update.sh` never
looked at a branch. It ran `git tag -l 'v*' | sort -V | tail -1`, and **tags are
not scoped to a branch** — so it saw both families at once. Since `sort -V`
places `v1.18.0-fr` **after** `v1.18.0`, the global maximum was the French tag,
and an English installation would have moved onto the French tree the moment
`fr` caught up. No error: the tag exists, the checkout succeeds, the tool just
starts speaking another language.

It stayed invisible only because `fr` lagged eight versions behind. Bringing it
level is what armed it.

`update.sh` now reads the family off what is installed — the suffix of the
checked-out tag, or the tracked branch when there is none — and filters the tag
list to that family before sorting. `tests/update_tag_family.sh` builds a
throwaway repository with both branches and holds it down in CI.

## What is not translated, on purpose

Three files are **byte-identical on both branches** and stay French:

| File | Why |
|---|---|
| `sync.sh` | it reads the author's living, French Brain |
| `rules.json` | the French patterns are what it matches, and its prose documents them |
| `.sync-manifest` | a fingerprint of the SOURCE, not of the package |

`rules.json` is inert on `main`; it is kept there so the repo stays complete and
auditable, and identical so that porting it is a plain `git checkout fr --`.

⚠ This section used to claim the `why` fields were in English. They are not, and
never were: 23 of the 29 carry French accents. `tests/english_only.py` skips the
whole file, so nothing contradicted the claim — a documented fact that no check
reads is a fact that rots.

## The glossary — what the translation renames

The engine is translated, and so is the vocabulary it writes to disk. A port
that renames one side and not the other leaves the branch reading a file nobody
writes. These are the pairs; extend the table rather than deciding again.

| on `fr` | on `main` | what it is |
|---|---|---|
| `base_sur` / `contredit` / `remplace` | `based_on` / `contradicts` / `replaces` | typed relations in a note's front matter |
| `recall-utilite.json` | `recall-utility.json` | state written by `recall_feedback.py` |
| `souvent-proposee-jamais-ouverte.json` | `often-suggested-never-opened.json` | state, same writer |
| `inacheves.json` | `unfinished.json` | state written by `brain_guard.py` |
| `a-revalider.json` | `to-revalidate.json` | state written by `fraicheur_fiches.py` |
| `SEUIL_JOURS` | `THRESHOLD_DAYS` | environment variable |
| `brain_guard.py inacheves --reenfiler` | `brain_guard.py unfinished --requeue` | subcommand |

**What is NOT renamed**: hook FILE names (`fraicheur_fiches.py`, `on_fiche_write.py`
— `sync.sh` copies them by name and `hooks/hooks.json` lists them), and the front
matter keys that were already English (`name`, `description`, `born_from`,
`redirectsTo`, `last_validated`). Agent files ARE renamed
(`jardinier.md` → `gardener.md`).

## Two tools, one guarantee — and the gap between them

`generalize.py` REWRITES what should not ship; `leakcheck.py` REFUSES what still
should not. They are not redundant, and neither covers the other:

- A rewrite rule can damage what it touches. The owner-name safety net, a bare
  `Dylan`, turned two Apache copyright headers into `(c) 2026 l'auteur Peellaert`.
  leakcheck could not see it — it exempts copyright lines from that very marker.
  The pattern is now `Dylan(?! Peellaert)`, and leakcheck covers what the
  negative lets through anywhere else.
- **Removing a rule leaves no red trace.** `banc-chemins-shell` was dropped, and
  `capsule/banc/cycle.sh` immediately shipped with `$HOME/claude-brain/` again —
  the author's private path. No test reads a path inside a comment, no counter
  moves. When you delete a rule, check by hand what it was holding.
