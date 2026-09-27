# cbrain/ — kept for one reason (pre-rename)

GreyMatter was called C Brain until v2.1.0. An installation from that time updates
itself with ITS OWN updater, which runs the new version's migrations from
`cbrain/migrations/` — a path written into it, that nothing can change now.

So this folder holds nothing but forwarding stubs: each one runs the real script in
`greymatter/migrations/`. Without them, an older install would skip the migration
that renames its root, test the new version against a layout it no longer has, and
refuse the update forever.

It can be deleted once no v2.0.x installation is left to update.
