# cbrain/ — kept for one reason (pre-rename)

GreyMatter was called C Brain until v2.1.0. An installation from that time updates
itself with ITS OWN updater, which runs the new version's migrations from
`cbrain/migrations/` — a path written into it, that nothing can change now.

So this folder holds nothing but forwarding stubs: each one runs the real script in
`greymatter/migrations/`. Without them, an older install would skip the migration
that renames its root, test the new version against a layout it no longer has, and
refuse the update forever.

One more stub, `launchd-lib.sh`, is for the old UNINSTALLER: the `uninstall.sh`
in a clone from before the rename sources `cbrain/launchd-lib.sh` from the engine.
The stub hands the uninstall over to the engine's own `uninstall.sh`, which knows
the new names; without it the old script reported success and left the jobs, the
shortcut and the Desktop app behind.

It can be deleted once no v2.0.x installation is left to update.
