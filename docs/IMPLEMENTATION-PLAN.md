# Implementation Plan

## Order
1. Persist project rules/docs and capture baseline.
2. Add tests around current scheduler/group/NAS/auth behavior.
3. Introduce version/build metadata and Fluent 2 shell/theme.
4. Add ordered SQLite migrations and backup-before-migrate.
5. Separate settings/persistence/service responsibilities where touched.
6. Replace ad-hoc run threads with a coordinated execution engine.
7. Upgrade Groups UI/behavior.
8. Upgrade Schedules UI and 7-day agenda.
9. Migrate single NAS settings to multi-NAS profiles; add Wake-on-LAN.
10. Add generic webhooks with HA/Discord presets.
11. Add retention/compaction, backup/export/import and About/update check.
12. Complete CI/release workflow and final regression/security review.

## Verification after each phase
- Existing critical behavior still works.
- New behavior has focused tests.
- No destructive Docker capability was introduced.
- Relevant docs/backlog are updated.
- No obsolete compatibility code remains without a documented reason.

## Definition of Done
- Required docs/skills are current.
- CI is green.
- Fluent 2 design is consistent and responsive.
- System/Dark/Light theme works and persists.
- Version/release pipeline is traceable.
- Existing features have no known regressions.
- WOL, multi-NAS, webhooks, backup/restore and health-aware groups are tested.
- Security review completed.
- README/deployment examples match reality.
- Remaining debt is explicit in `docs/BACKLOG.md`.
