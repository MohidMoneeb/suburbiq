# Seed data

`suburbiq-seed.db` is a snapshot of a real ingest so a fresh deployment has
something to show on first boot. On startup, if no working database exists at
`data/suburbiq.db`, this file is copied into place once. Local runs that already
have a database are left alone.

Contents: Greater Sydney — 2,625 cafés and 10 plumbers, ingested 2026-08-05.

To refresh it after a new ingest:

```bash
cp data/suburbiq.db seed/suburbiq-seed.db
```

## Licence

This database is derived from OpenStreetMap.

Data © OpenStreetMap contributors, available under the
[Open Database Licence (ODbL) v1.0](https://opendatacommons.org/licenses/odbl/1-0/).

Redistributing it — which is what committing this file does — requires that
attribution and licence notice travel with it, and that any derived database you
distribute is offered under the same licence. The running app also displays the
attribution in its footer.
