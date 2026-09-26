---
name: how-this-trunk-works
description: The trunk loop in four beats — write, recall, file, review. When you wonder what C Brain actually does once installed, or what triggers what.
metadata:
  type: meta
  demo: true
---

Four beats, and nothing else to remember.

**1. Write.** One note = one fact. It is born when something cost you time and
you do not want to pay for it twice. No "just in case" notes: a trunk swelling
with never-reread notes loses exactly what makes it useful.

**2. Recall.** Ask for it — `?brain` in a message, a plain "any notes on…", or
`brain recall <question>` in a terminal — and a hook searches the trunk and
hands your agent the two or three relevant notes. It is the `description` at
the top of the note that decides — not the title, not the body.
**Care about the description more than anything else.**

**3. File.** The agents run in the background: the gardener re-places notes and
repairs `[[...]]` links, the archivist proposes the dead weight, the challenger
attacks whatever is stale or false. None of them deletes on its own.

**4. Review.** `brain review` aggregates the state of the trunk, `brain doctor`
reports its health, and `brain recall <question>` shows exactly what the
recall hook would hand back.

**Why:** an external memory is only worth something if it comes back the moment
you reach for it, from wherever you are. A folder of notes you have to remember
to reopen is not memory, it is a drawer. Recall waits to be asked because, fired
on every message, it was opened about four times in a hundred and cost its noise
on all the others; `BRAIN_RECALL_AUTO=1` brings it back if you prefer.

**How to apply:** write the note while the trap is fresh, in one minute, badly.
The gardener will file it. An ugly note exists; a perfect note never written
does not.

Linked to [[the-cache-lies-after-a-deploy]] (what a real lesson looks like) and
to [[resuming-the-pricing-page-rework]] (what a resume point looks like).

> Demo note, installed by `brain demo`. `brain demo --remove` takes it away.
