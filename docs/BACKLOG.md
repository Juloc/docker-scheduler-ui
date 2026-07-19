# Backlog

## Now

No open modernization blockers.

## Next
- [ ] Add webhook editing and optional successful-run notifications if real usage needs them.
- [ ] Add richer automated accessibility/UI smoke checks.

## Later
- [ ] Evaluate queued conflict policy if real usage requires it.
- [ ] Optional richer webhook templates only when generic presets are insufficient.
- [ ] Remove legacy single-NAS compatibility settings after a defined compatibility window.
- [ ] Evaluate a dedicated execution worker only if real scale exceeds the lightweight in-process runner.

## Ideas
- [ ] Additional non-destructive Docker status insights where they directly help scheduling.

## Tech Debt

No known blocking tech debt for the modernization release. Compatibility code and possible future scaling work are tracked under Later rather than left as hidden TODOs.

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
- [x] Generic/Home Assistant/Discord webhook support with bounded retries and test action.
- [x] Webhook events wired for run failures, NAS transitions and WOL failures.
- [x] Detailed-log retention and compact long-term history.
- [x] Favorite groups and Home quick actions.
- [x] Dedicated compact Containers workspace.
- [x] Container search/status/project filters and Compose metadata.
- [x] Explicit Compose-project grouping control.
- [x] Optional infrastructure hiding using user-marked Compose projects stored locally in the browser.
- [x] Repeated schedule occurrence engine wired into a true Today / next-seven-days Home agenda.
- [x] Latest GitHub Release detection in Settings > About without self-update.
- [x] Route/view helper extraction: `main.py` is limited to application assembly and middleware; feature routes live under `app/routes`.
- [x] Expanded integration coverage for HTTP auth/settings, migrations, NAS/WOL, webhook filtering/delivery, scheduler recurrence and conflict handling.
- [x] CI quality gate with lint, tests, compile check and Docker build.
- [x] Tagged SemVer GHCR release automation.
