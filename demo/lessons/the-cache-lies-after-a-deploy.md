---
name: the-cache-lies-after-a-deploy
description: A deploy reported as "successful" can still be serving the old version — check the artefact being served, never the build status. When a fix "doesn't work" although the code is right.
metadata:
  type: lesson
  demo: true
---

A dashboard showing **SUCCESS** proves one thing: the build finished. It does
not prove that the code you are being served is the new one.

In between sit an image cache, a CDN, a service worker — each able to keep
serving the old version for hours, with no error anywhere.

**Why:** the symptom is misleading enough to send you hunting for the bug in
your code. You re-read a correct fix, rewrite it, doubt yourself — while the fix
has never run a single time.

**How to apply:** never conclude from the build status. Put a verifiable marker
in the artefact (version number, build date) and **read it from the outside**
before saying it is live. If the marker is the old one, the problem is not your
code.

Linked to [[how-this-trunk-works]]: this is the kind of note that justifies all
the rest — a trap understood once, never twice.

> Demo note, installed by `brain demo`. `brain demo --remove` takes it away.
> Replace it with your own as soon as you have a real one.
