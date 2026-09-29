# Contributing

Thanks for looking. One thing about this repository is not obvious from the
outside, and getting it wrong costs you a rejected patch — so it comes first.

[Where to make your change](#the-one-thing-to-know-first) ·
[Before you open a pull request](#before-you-open-a-pull-request) ·
[What gets in](#what-gets-in-and-what-does-not) ·
[Style](#style) · [Licence](#licence)

## The one thing to know first

```
the author's living Brain
   │  scripts/sync.sh                      whitelist — refuses to run anywhere but `fr`
   ▼
this repo, branch `fr`                     the source, in French
   │  scripts/generalize.py + rules.json   depersonalisation
   │  scripts/leakcheck.py                 21 markers, blocking
   ▼
branch `main`                              the translation, by hand
   ▼
scripts/publish.sh vX.Y.Z "message"        the only sanctioned path to a push
```

**`main` is a translation. `fr` is the source.** GreyMatter is extracted from a
real, personal, French knowledge trunk, and the chain runs one way — so where
you make a change decides whether it survives.

| Where | Edit by hand? | Why |
|---|---|---|
| **`main`** | **Yes — open your pull request here** | `main` is the translation: nothing upstream overwrites it |
| `fr`, an engine file | No — add a rule to `scripts/rules.json` | `scripts/sync.sh` overwrites it from the author's Brain on the next pass, and your change disappears without a trace |
| `fr`, anything else | Only when you are fixing the French branch itself | |

<details>
<summary><b>Which files count as engine files on <code>fr</code></b></summary>

Everything under `hooks/`, `agents/`, `capsule/`, `planet/`, `companion/` and
`tests/`, plus the `brain` script and `statusline.py`. That is what
`scripts/sync.sh` carries over from the author's Brain; the exact list it works
from is `scripts/.sync-manifest`.

</details>

## Before you open a pull request

- [ ] `python3 scripts/leakcheck.py` says **CLEAN** — it blocks publication otherwise.
- [ ] `python3 tests/english_only.py` passes — `main` only: no French in user-visible strings.
- [ ] If you touched the capsule, its two benches pass (below).
- [ ] Your commit message says **why** (see [Style](#style)).

<details>
<summary><b>If you touched the capsule — the menu bar pill, <code>capsule/macos</code></b></summary>

Its two benches need macOS and Swift (`xcode-select --install`):

```bash
python3 tests/capsule_runtime.py     # builds the pill outside a fake version, runs `--check`, breaks a source
python3 tests/capsule_liveness.py    # the pill reads the same freshness windows as brain_status.py
```

To look at it:

| Command | Shows |
|---|---|
| `capsule/macos/.build/release/Capsule --image working /tmp/orb.png` | the orb alone, drawn to a file |
| `capsule/macos/.build/release/Capsule --panel-demo working 600 300` | the panel, open at that screen point for 8 s |
| `brain capsule` | the real pill, in the menu bar |

</details>

<details>
<summary><b>What the CI checks for you</b></summary>

It runs `capsule_runtime.py` on its macOS runner, plus a full install /
selftest / uninstall on macOS and every migration replayed twice. It is a small
workflow — the capsule bench alone builds the pill twice, about a minute. Read
`.github/workflows/ci.yml` to see exactly what is asserted.

</details>

## What gets in, and what does not

| | Change | In short |
|:---:|---|---|
| ❌ | A hand-edited engine file on `fr` | it cannot survive the next sync |
| ❌ | Anything that makes the tool phone home | no network call beyond `git pull` — a hard line |
| ❌ | Anything that writes to the user's trunk unasked | the trunk is the user's work |
| ❌ | A migration that does more than migrate | re-wiring is `install.sh`'s job |
| ✅ | Portability | macOS-only today; a clean Linux path is real work |
| ✅ | A second CLI agent | the closed loop is wired for Claude Code only |
| ✅ | Translation gaps | hook comments are still partly French |
| ✅ | A test for a hole the CI missed | worth more than the fix |

<details>
<summary><b>What gets turned down, in full</b></summary>

- **A hand-edited engine file on `fr`.** See [above](#the-one-thing-to-know-first)
  — it is not a style preference, the change genuinely cannot survive.
- **Anything that makes the tool phone home.** No telemetry, no analytics, no
  network call beyond `git pull`. This is a hard line, not a default.
- **Anything that writes to the user's trunk without being asked.** The trunk is
  the user's work. `uninstall.sh` leaves it standing; `brain demo --remove` will
  not delete an example note the user has edited, because editing it made it
  theirs. New code is held to the same rule.
- **A migration that does more than migrate.** Migrations move things.
  Re-wiring is `install.sh`'s job, and `update.sh` always calls it — duplicating
  that logic creates two copies that will drift.

</details>

<details>
<summary><b>What is genuinely welcome, in full</b></summary>

- **Portability.** Today this is macOS-only: `launchd`, AppKit,
  `open`. A clean Linux path is real work and would be a real contribution.
- **A second CLI agent.** The closed loop is wired for Claude Code hooks. The
  rest — trunk, agents, `brain`, planet, capsule — works on demand anywhere.
- **Translation gaps.** Hook comments are still partly French; `english_only.py`
  deliberately ignores comments, so it will not find them for you.
- **Anything the CI should have caught and did not.** A failing test that
  demonstrates the hole is worth more than the fix.

</details>

## Style

Commit messages here explain **why**, and say what broke and how it was found —
often at some length. Match that if you can: a one-line "fix bug" tells the next
reader nothing they cannot already see in the diff.

## Licence

By contributing you agree your contribution is licensed under
[Apache 2.0](LICENSE), like the rest of the project.
