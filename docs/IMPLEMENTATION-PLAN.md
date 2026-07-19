# Implementation Plan

## Status
Modernization implementation complete on `agent/fluent2-modernization`.

## Completed sequence
1. Project rules, architecture, design, security, versioning and backlog documented.
2. Baseline cleanup and regression coverage established.
3. Versioned SQLite migration/backup path implemented.
4. Fluent 2 shell and persistent System/Dark/Light theme implemented.
5. Home Control Center and dedicated Containers workspace implemented.
6. Unified action engine implemented with reverse-stop, per-step delay, health waits, conflict/error policies and cancellation.
7. Multi-NAS profiles and Wake-on-LAN implemented.
8. Scheduler expanded with NAS integration and true seven-day repeated-occurrence agenda.
9. Generic/Home Assistant/Discord webhooks implemented.
10. Settings auto-save, backup/restore, retention and About/version checks implemented.
11. Feature routes extracted from `app/main.py` into `app/routes`; shared presentation helpers live in `app/web.py`.
12. CI validates lint, tests, Python compilation and Docker image build.

## Definition of Done result
- Required docs/skills are current.
- Blocking tech debt: none known; optional future work is tracked in `docs/BACKLOG.md`.
- Fluent 2 and System/Dark/Light are implemented.
- Version/build metadata and release workflow are implemented.
- Existing critical behavior is covered by regression/integration tests.
- WOL, multi-NAS, webhooks, backup/restore, health-aware groups and conflict/cancellation behavior are implemented.
- README/deployment documentation is updated.
- Final CI quality and Docker-build jobs are required to be green before merge.
