# Contributing

Thanks for looking. This repository has a shape that is not obvious from the
outside, and getting it wrong costs you a rejected patch — so it is spelled out
here before anything else.

## The one thing to know first

**`main` is a translation. `fr` is the source.**

GreyMatter is extracted from a real, personal, French knowledge trunk. The chain
runs one way:

```
the author's living Brain
   │  sync.sh          whitelist — refuses to run anywhere but `fr`
   ▼
this repo, branch `fr`
   │  generalize.py + rules.json     depersonalisation
   │  leakcheck.py                   21 markers, blocking
   ▼
   branch `main`                     translated, by hand
   ▼
   publish.sh vX.Y.Z "message"       the only sanctioned path to a push
```

What follows from that:

- **On `fr`, do not hand-edit anything under `hooks/`, `agents/`, `capsule/`,
  `planet/`, `companion/`, `tests/`, or the `brain` script.** `sync.sh`
  overwrites those files from the author's Brain on the next pass, and your
  change disappears without a trace. Those need a rule in `rules.json` instead.
- **On `main`, editing directly is the right move** — `main` is the translation,
  it has no upstream to be overwritten from.
- **Open your pull request against `main`** unless you are specifically fixing
  the French branch.

## Before you open a pull request

```bash
python3 leakcheck.py           # must be CLEAN — it blocks publication otherwise
python3 tests/english_only.py  # main only: no French in user-visible strings
```

If you touched the capsule (the menu bar pill, `capsule/macos`), run its two
benches. They need macOS and Swift (`xcode-select --install`):

```bash
python3 tests/capsule_runtime.py     # builds the pill outside a fake version, runs `--check`, breaks a source
python3 tests/capsule_liveness.py    # the pill reads the same freshness windows as brain_status.py
```

To look at it: `capsule/macos/.build/release/Capsule --image working /tmp/orb.png`
draws the orb alone, `--panel-demo working 600 300` opens the panel at that
screen point for 8 s, and `brain capsule` puts
the real pill in the menu bar.

The CI runs `capsule_runtime.py` on its macOS runner, plus a full install / selftest / uninstall on macOS and every
migration replayed twice. It is a small workflow — the capsule bench alone builds the pill twice, about a minute —
read `.github/workflows/ci.yml` to see exactly what is asserted.

## Things that will get a patch turned down

- **A hand-edited engine file on `fr`.** See above — it is not a style
  preference, the change genuinely cannot survive.
- **Anything that makes the tool phone home.** No telemetry, no analytics, no
  network call beyond `git pull`. This is a hard line, not a default.
- **Anything that writes to the user's trunk without being asked.** The trunk is
  the user's work. `uninstall.sh` leaves it standing; `brain demo --remove` will
  not delete an example note the user has edited, because editing it made it
  theirs. New code is held to the same rule.
- **A migration that does more than migrate.** Migrations move things.
  Re-wiring is `install.sh`'s job, and `update.sh` always calls it — duplicating
  that logic creates two copies that will drift.

## Things that are genuinely welcome

- **Portability.** Today this is macOS-only: `launchd`, Electron, `open`. A
  clean Linux path is real work and would be a real contribution.
- **A second CLI agent.** The closed loop is wired for Claude Code hooks. The
  rest — trunk, agents, `brain`, planet, capsule — works on demand anywhere.
- **Translation gaps.** Hook comments are still partly French; `english_only.py`
  deliberately ignores comments, so it will not find them for you.
- **Anything the CI should have caught and did not.** A failing test that
  demonstrates the hole is worth more than the fix.

## Style

Commit messages here explain **why**, and say what broke and how it was found —
often at some length. Match that if you can; a one-line "fix bug" tells the next
reader nothing they cannot already see in the diff.

## Licence

By contributing you agree your contribution is licensed under
[Apache 2.0](LICENSE), like the rest of the project.
