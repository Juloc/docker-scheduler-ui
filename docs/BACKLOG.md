# Backlog

## Now
- [ ] Baseline tests and architecture cleanup without rewrite.
- [ ] Fluent 2 shell, sidebar and System/Dark/Light theme.
- [ ] Central application version/build metadata; remove manual asset versioning.
- [ ] SQLite schema migrations with pre-migration backup.
- [ ] Settings auto-save and configuration export/import.
- [ ] Unified execution engine for manual and scheduled actions.
- [ ] Group reverse-stop, per-step delay, Docker health wait, error policy and conflict policy.
- [ ] Active-run progress/cancellation.
- [ ] Multi-NAS profiles and Wake-on-LAN.
- [ ] Generic/Home Assistant/Discord webhooks.
- [ ] Log retention/compaction.
- [ ] CI and release automation.

## Next
- [ ] Container search/filter and optional Compose-project grouping.
- [ ] Favorite groups and Home quick actions.
- [ ] Today/7-day schedule agenda.
- [ ] Latest-release check in Settings > About.

## Later
- [ ] Evaluate queued conflict policy if real usage requires it.
- [ ] Optional richer webhook templates only when generic presets are insufficient.

## Ideas
- [ ] Additional non-destructive Docker status insights where they directly help scheduling.

## Tech Debt
- [ ] `app/main.py` currently combines routing/view composition and needs gradual route extraction.
- [ ] Current database evolution relies on `ALTER TABLE` checks rather than ordered migrations.
- [ ] Existing group runner uses daemon threads and blocking sleeps without cancellation/conflict coordination.
- [ ] Current NAS model is one global settings namespace.

## Done
- [x] Product scope defined: focused Docker scheduler, not a general Docker/NAS control center.
- [x] Fluent 2 / Windows 11 design direction defined.
- [x] Security and versioning policies documented.
