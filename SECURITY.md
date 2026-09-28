# Security

## What this software actually does to your machine

Worth stating plainly, because it is the honest basis for judging risk:

- **It writes inside `$HOME`.** `~/.greymatter/` (engine and trunk), `~/.claude/`
  (settings merge, status line), `~/Library/LaunchAgents/com.greymatter.*`
  (scheduled jobs), a launcher on the Desktop, and a `GreyMatter` shortcut in your
  home folder pointing at your trunk (`--no-shortcut` skips it). `install.sh` records every
  one of them in a manifest, and `uninstall.sh` undoes them.
- **It runs code on your machine automatically.** That is the point: hooks fire
  on your CLI agent's events, and two `launchd` jobs run on a timer. Install
  `--no-launchd` if you would rather nothing ran unattended.
- **It makes no network call except `git pull`.** No telemetry, no analytics, no
  crash reporting, no phone-home on install.
- **It looks for updates, and asks before installing one.** Every session
  start checks the published tags in the background. When a newer version
  exists, the next session tells your agent to **ask you** — once per version
  per day — and nothing is installed until you say yes (`brain update`). From
  v1.28.0 to v2.1.0 it installed on its own; since v2.1.1 that is an opt-in:
  `brain update --auto-on`. Silent installing is **remote code running on your
  machine without you asking for it**, which is why it is no longer the
  default. Either way, what bounds an update:
  - updates follow **published tags**, never a working branch;
  - the **selftest decides**: a version whose selftest goes red is never
    activated, and the next session tells you so;
  - the **trunk is never touched** — only `~/.greymatter/engine` is replaced;
  - `brain update --auto-off` goes back to asking; `GREYMATTER_NO_AUTO_UPDATE=1`
    stops silent installs whatever the switch says.
- **It reads your notes locally, and that is how it works.** Recall, the index,
  the graph and the agents all open the files — there is no way to find a note
  without reading one. It happens on your machine, and nothing is written back
  to us.
- **What leaves your machine is what any prompt carries.** The recall hook adds
  the **name, one-line description and path** of the two or three most relevant
  notes to the prompt you are about to send — not the file bodies. That prompt
  goes to your model provider, exactly like the rest of your message. GreyMatter
  makes no request of its own, but it is not true that nothing of your trunk
  ever travels: what it puts in a prompt travels with the prompt.
  `brain doctor` shows what the hook would inject; remove the
  `UserPromptSubmit` hook from `settings.json` to stop it entirely.
- **Agents are the loud case.** When you run a ship's distiller or gardener
  mission, it reads whole notes and sends them to the provider — that is
  what you asked it to do. Nothing is automatic about it: you start them.

## Supported versions

Fixes go onto the latest release. There is no long-term support branch, and
older tags are not patched — `brain update` moves you forward.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting on this repository:
**Security → Report a vulnerability**. It reaches the maintainer directly and
stays private until there is a fix.

Useful in a report: what an attacker can do, what they need first (local access?
a malicious repo? a crafted note?), and the smallest sequence that shows it.

Expect a first answer within about a week. This is a personal project, not a
staffed product — that number is what one maintainer can honestly promise.

## In scope

- Anything letting a **note, a repository, or a hook payload** run code that the
  user did not ask for.
- **Path handling** in `install.sh`, `uninstall.sh` and the migrations — they
  move directories inside `$HOME` and a mistake there costs real work.
- **`leakcheck.py` failing open**: it is what stands between a personal trunk
  and a public push. A way to get a secret past it is a vulnerability, and one
  of the more interesting kinds here.
- **`merge_settings.py` corrupting or losing keys** in `~/.claude/settings.json`.

## Out of scope

- The fact that the engine executes on your machine by design — see above.
- Anything requiring an attacker who already has write access to your `$HOME`;
  at that point they do not need GreyMatter.
- Reports against the `fr` branch that do not also apply to `main`, unless the
  bug is specifically in the French version.
