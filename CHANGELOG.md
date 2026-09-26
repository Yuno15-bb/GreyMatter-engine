# Changelog

Generated from the annotated git tags by `cbrain/changelog.sh` — do not edit by hand.
Every entry is the message that was attached to the tag when the version was published.

The `fr` branch stopped being a released product on 2026-08-13 — it is the staging
buffer the engine is synced onto, and `publish.sh` refuses to tag from it. The `-fr`
tags up to v1.27.0-fr stay published (moving a tag breaks the fetch of anyone still on
it), and are not listed here.

## v2.0.2 — 2026-09-26

Fix: a new Mac passes its selftest, and a plugin install gets a real trunk

## v2.0.1 — 2026-09-26

Fix: a fresh install no longer reports dead links

## v2.0.0 — 2026-09-26

Recall on request, four agents, and a source that is no longer the engine

## v1.28.1 — 2026-08-16

Five defects found on somebody else's install, and the diagnostic that could not see them

## v1.28.0 — 2026-08-16

Automatic updates: session start installs the latest version by itself, and undoes it if the selftest goes red

## v1.27.1 — 2026-08-13

Fix the red CI: a self-test that guessed a path, and an index build over its gate

## v1.27.0 — 2026-08-13

Recall that learns from use, and knows its own age

## v1.26.7 — 2026-08-04

Orb: a second line names the note being worked on

## v1.26.6 — 2026-08-04

Orb: see-through liquid glass, legible code pad, no cast shadow under the label

## v1.26.5 — 2026-08-03

The demo breathes

## v1.26.4 — 2026-08-03

Slower code scroll

## v1.26.3 — 2026-08-03

Smoother, cleaner demo

## v1.26.2 — 2026-08-03

The orb opens the README

## v1.26.1 — 2026-08-03

Orb polish: pad contained, label laid in the shadow, seamless demo

## v1.26.0 — 2026-08-03

The orb replaces the creature: glass, live code inside it, drag with the mouse

## v1.25.0 — 2026-07-30

Says what actually leaves the machine: the recall hook puts note names and descriptions into prompts that go to your model provider, and agents send whole notes — the README claimed it read and sent nothing. brain update now shows the remote and the target commit before applying, held by two assertions. Two stale claims fixed in the design doc.

## v1.24.0 — 2026-07-29

The plugin path told new users two things that were not true

## v1.23.0 — 2026-07-29

Three skills that drive the tool — the plugin finally has a surface you can type

## v1.22.0 — 2026-07-29

The core is the memory; the capsule and the planet are extensions — and --core-only proves it

## v1.21.0 — 2026-07-29

update and rollback are tested end to end — and the test was reading the wrong code

## v1.20.0 — 2026-07-29

Recall is measured for the first time — and was costing 243 ms on every prompt

## v1.19.1 — 2026-07-29

sync.sh: the new update test joins the package-only exclusions

## v1.19.0 — 2026-07-29

brain update no longer switches a user's language: the tag family follows the installation

## v1.18.0 — 2026-07-29

sync.sh no longer deletes the plugin manifest; the version gate follows its branch

## v1.17.0 — 2026-07-28

C Brain installs as a Claude Code plugin — one command, no installer

## v1.16.0 — 2026-07-28

README: a picture of where C Brain lands in your home folder

## v1.15.0 — 2026-07-28

A visible C Brain shortcut in the home folder — the trunk stops being invisible

## v1.14.0 — 2026-07-28

Repository signals: badges, CONTRIBUTING, SECURITY, generated CHANGELOG, issue templates

## v1.13.0 — 2026-07-28

CI: leak check, English-only guard, install/selftest/uninstall, migrations replayed twice

## v1.12.0 — 2026-07-28

Visuals: all eleven capsule states (animated WebP), and the planet being consulted live

## v1.11.0 — 2026-07-28

README visuals: capsule GIF, knowledge planet, recall loop — plus three missed English strings

## v1.10.0 — 2026-07-28

Fix license headers contradicting LICENSE, and the dead code-scroll background on the English package

## v1.9.0 — 2026-07-27

brain demo: an empty trunk no longer greets you with nothing

## v1.8.0 — 2026-07-27

Rename: the user trunk becomes ~/.c-brain/trunk (migration 001)

## v1.7.0 — 2026-07-27

Apache 2.0 · live activity ring · leakcheck false positives fixed

## v1.6.0 — 2026-07-27

source-available licence, no derivative works

## v1.5.0 — 2026-07-27

MIT licence, and a silent failure for accounts with a dot in the name

## v1.4.0 — 2026-07-27

the repository is fully in English

## v1.3.0 — 2026-07-27

every hook and CLI output in English

## v1.2.0 — 2026-07-27

capsule and planet fully in English

## v1.1.0 — 2026-07-26

English by default, public, 8 agents renamed and rewritten

## v1.0.2 — 2026-07-26

Publication guarded, `sync --check` corrected

## v1.0.1 — 2026-07-26

Documented authentication for a private repository

## v1.0.0 — 2026-07-26

C Brain v1.0.0 — first installable release
