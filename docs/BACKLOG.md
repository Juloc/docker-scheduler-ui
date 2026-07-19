# Backlog

## Now
- [ ] Complete route extraction from `app/main.py` without introducing a rewrite.
- [ ] Add broader integration coverage for HTTP forms, migrations, NAS/WOL and webhook flows.
- [ ] Wire the repeated-occurrence Today / next-7-days agenda engine into the Home UI.
- [ ] Add optional infrastructure-container hiding and explicit Compose-project grouping controls.
- [ ] Promote Containers from a Home anchor to a dedicated compact workspace.

## Next
- [ ] Add webhook editing and optional successful-run notifications if real usage needs them.
- [ ] Add richer automated accessibility/UI smoke checks.

## Later
- [ ] Evaluate queued conflict policy if real usage requires it.
- [ ] Optional richer webhook templates only when generic presets are insufficient.

## Ideas
- [ ] Additional non-destructive Docker status insights where they directly help scheduling.

## Tech Debt
- [ ] `app/main.py` still combines too much routing/view composition and should be extracted gradually by feature area.
- [ ] Legacy single-NAS compatibility settings remain temporarily for upgrade compatibility; remove only after a defined compatibility window.
- [ ] Background execution still uses lightweight daemon threads; cancellation/conflict coordination is implemented, but a dedicated executor can be evaluated only if scale requires it.

## Done
- [x] Product scope defined: focused Docker scheduler, not a general Docker/NAS control center.
- [x] Fluent 2 / Windows 11 design direction and reusable UI skill documented.
- [x] Fluent 2 application shell with persistent System / Dark / Light theme.
- [x] Security and versioning policies documented.
- [x] Central semantic version/build metadata and release workflow.
- [x] Ordered SQLite schema migrations with pre-migration backup.
- [x] Settings auto-save and configuration export/import without detailed logs.
- [x] Unified execution engine path for manual and scheduled actions.
- [x] Reverse-stop, per-step delays, Docker health waiting, error policy and conflict policy.
- [x] Container conflict identity normalized across full ID, short ID, name, manual runs, groups and schedules.
- [x] Active-run progress and cancellation.
- [x] Multi-NAS profiles and Wake-on-LAN with optional auto-wake.
- [x] Wake-on-LAN packet generation and MAC validation covered by tests.
- [x] Generic/Home Assistant/Discord webhook support with bounded retries and tests from Settings.
- [x] Webhook events wired for run failures, NAS transitions and WOL failures.
- [x] Detailed-log retention and compact long-term history.
- [x] Favorite groups and Home quick actions.
- [x] Container search/filter plus Compose metadata display.
- [x] Repeated schedule occurrence engine for true seven-day agenda calculations.
- [x] Latest GitHub Release detection in Settings > About without self-update.
- [x] CI quality gate with lint, tests, compile check and Docker build.
- [x] Tagged SemVer GHCR release automation.
