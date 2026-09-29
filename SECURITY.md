# Security

> [!IMPORTANT]
> **Found a vulnerability? Please do not open a public issue.** Use
> **Security → Report a vulnerability** on this repository — it reaches the
> maintainer privately. [How to report](#reporting-a-vulnerability).

[What it does to your machine](#what-this-software-actually-does-to-your-machine) ·
[Supported versions](#supported-versions) ·
[Reporting](#reporting-a-vulnerability) ·
[In scope](#in-scope) · [Out of scope](#out-of-scope)

## What this software actually does to your machine

| It… | Where, or when | To opt out |
|---|---|---|
| **writes inside `$HOME`** | `~/.greymatter/`, `~/.claude/`, `~/Library/LaunchAgents/com.greymatter.*`, a Desktop launcher, a `GreyMatter` shortcut | `uninstall.sh` undoes it all · `--no-shortcut` |
| **runs code unattended** | hooks on your agent's events · two `launchd` jobs on a timer | install with `--no-launchd` |
| **looks for updates, and asks before installing** | every session start, from published tags | nothing to do — `brain update --auto-on` makes it silent |
| **reads your notes** | on your machine, to find them | — that is how recall works |
| **makes no network call** | except `git pull` | — |
| **adds 2–3 note titles to your prompt** | name, one-line description and path, not the bodies | remove the `UserPromptSubmit` hook |
| **lets agents send whole notes** | only when you start one | do not start it |

Worth stating plainly, because it is the honest basis for judging risk. The two
rows that deserve a second look are the update check and what travels with a
prompt — both are spelled out below.

<details>
<summary><b>What it writes, and how it is undone</b></summary>

`~/.greymatter/` (engine and trunk), `~/.claude/` (settings merge, status line),
`~/Library/LaunchAgents/com.greymatter.*` (scheduled jobs), a launcher on the
Desktop, and a `GreyMatter` shortcut in your home folder pointing at your trunk
(`--no-shortcut` skips it). `install.sh` records every one of them in a
manifest, and `uninstall.sh` undoes them.

</details>

<details>
<summary><b>What runs without you asking</b></summary>

That is the point: hooks fire on your CLI agent's events, and two `launchd` jobs
run on a timer. Install `--no-launchd` if you would rather nothing ran
unattended.

No telemetry, no analytics, no crash reporting, no phone-home on install. The
only network call is `git pull`.

</details>

<details>
<summary><b>It looks for updates, and asks before installing one</b></summary>

Every session start checks the published tags in the background. When a newer
version exists, the next session tells your agent to **ask you** — once per
version per day — and nothing is installed until you say yes (`brain update`).
From v1.28.0 to v2.1.0 it installed on its own; since v2.1.1 that is an opt-in:
`brain update --auto-on`. Silent installing is **remote code running on your
machine without you asking for it**, which is why it is no longer the default.
Either way, what bounds an update:

- updates follow **published tags**, never a working branch;
- the **selftest decides**: a version whose selftest goes red is never
  activated, and the next session tells you so;
- the **trunk is never touched** — only `~/.greymatter/engine` is replaced;
- `brain update --auto-off` goes back to asking; `GREYMATTER_NO_AUTO_UPDATE=1`
  stops silent installs whatever the switch says.

</details>

<details>
<summary><b>Your notes, and what leaves your machine</b></summary>

**It reads your notes locally, and that is how it works.** Recall, the index,
the graph and the agents all open the files — there is no way to find a note
without reading one. It happens on your machine, and nothing is written back
to us.

**What leaves your machine is what any prompt carries.** The recall hook adds
the **name, one-line description and path** of the two or three most relevant
notes to the prompt you are about to send — not the file bodies. That prompt
goes to your model provider, exactly like the rest of your message. GreyMatter
makes no request of its own, but it is not true that nothing of your trunk ever
travels: what it puts in a prompt travels with the prompt. `brain doctor` shows
what the hook would inject; remove the `UserPromptSubmit` hook from
`settings.json` to stop it entirely.

**Agents are the loud case.** When you run a ship's distiller or gardener
mission, it reads whole notes and sends them to the provider — that is what you
asked it to do. Nothing is automatic about it: you start them.

</details>

## Supported versions

| Version | Gets security fixes |
|---|:---:|
| The latest release | ✅ |
| Any older tag | ❌ — `brain update` moves you forward |

There is no long-term support branch.

## Reporting a vulnerability

1. Go to **Security → Report a vulnerability** on this repository. It stays
   private until there is a fix.
2. Say what an attacker can do, what they need first (local access? a malicious
   repo? a crafted note?), and the smallest sequence that shows it.
3. Expect a first answer within about a week.

This is a personal project, not a staffed product — a week is what one
maintainer can honestly promise.

## In scope

| Area | Why it matters here |
|---|---|
| A **note, a repository or a hook payload** running code the user did not ask for | all three reach the engine as input |
| **Path handling** in `install.sh`, `uninstall.sh` and the migrations | they move directories inside `$HOME`; a mistake costs real work |
| **`scripts/leakcheck.py` failing open** | it is what stands between a personal trunk and a public push — a secret that gets past it is a vulnerability, and one of the more interesting kinds here |
| **`merge_settings.py` corrupting or losing keys** | it edits your `~/.claude/settings.json` |

## Out of scope

| Report | Why not |
|---|---|
| The engine executes on your machine | by design — see [above](#what-this-software-actually-does-to-your-machine) |
| An attacker who already has write access to your `$HOME` | at that point they do not need GreyMatter |
| A bug on the `fr` branch that does not also apply to `main` | unless the bug is specifically in the French version |
