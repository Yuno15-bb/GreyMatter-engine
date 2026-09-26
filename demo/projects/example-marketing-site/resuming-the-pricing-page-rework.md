---
name: resuming-the-pricing-page-rework
description: Resume point for work in progress — where it stands, what is settled, the next action. When you pick a project back up after a break and no longer know where you left it.
metadata:
  type: project
  demo: true
---

An example of a **resume point** note: the one you read first when reopening a
project three weeks later.

**State on 12 March.** New pricing grid live on staging. The three tiers render,
the comparison table holds up on mobile.

**Settled — do not reopen.** Three tiers, not four: the fourth made people
hesitate instead of reassuring them. Prices shown excluding tax, like the rest
of the site.

**What is left.**

| # | To do | Effort |
|---|---|---|
| 1 | Wire the "Contact us" button to the real form | 30 min |
| 2 | Review the legal notices with the accountant | to schedule |
| 3 | Ship to production | 15 min, after 1 and 2 |

**Trap hit along the way.** The comparison table looked broken on phones while
the CSS was correct: it was a cached version — see
[[the-cache-lies-after-a-deploy]].

**Next concrete action:** item 1. Everything else depends on it.

**Why this note exists:** picking work back up is expensive because you
re-decide things already decided. Writing what is **closed** is worth as much as
writing what is left.

Linked to [[how-this-trunk-works]].

> Demo note, installed by `brain demo`. `brain demo --remove` takes it away.
