# AGENTS.md

## Mission
Maintain docker-scheduler-ui as a small, focused Docker scheduling tool. Preserve FastAPI, Python, SQLite, APScheduler and server-rendered Jinja unless a documented decision explicitly changes them. Avoid rewrites.

## Mandatory workflow
1. Read this file and only the task-relevant docs before changing code.
2. Reuse existing services/components before adding abstractions.
3. Keep changes small, cohesive and testable.
4. Remove dead/duplicate code when safe; document intentional debt in `docs/BACKLOG.md`.
5. Update relevant docs when architecture, UX, security, persistence or release behavior changes.
6. Do not weaken or rewrite tests merely to fit an implementation.

## Product constraints
- Focus: schedule Docker container/group start, stop and restart actions.
- No destructive Docker operations: no container removal, volume deletion, image prune or system prune.
- Desktop-first, responsive Microsoft Fluent 2 / Windows 11 visual language.
- Theme control is always three-state: System (default), Dark, Light; persist the choice.
- Work areas such as tables/logs/editors stay flat and compact; dashboard summary areas may use subtle elevated cards.
- Form login is default; Basic Auth remains optional.
- SQLite stays the persistence engine for the single-instance deployment model.

## Security
Treat Docker socket access as host-equivalent privilege. Never commit credentials, secrets, deployment-specific private paths or tokens. Prefer least privilege around all other integrations. See `docs/SECURITY.md`.

## Quality gate
A change is not done while relevant tests, linting or CI fail. New behavior requires tests for business logic and critical API/UI flows.

## Token-efficient project knowledge
Read only the relevant documents:
- Architecture/persistence: `docs/ARCHITECTURE.md`
- UI/UX: `docs/DESIGN.md`
- Security: `docs/SECURITY.md`
- Releases/versioning: `docs/VERSIONING.md`
- Planned work/debt: `docs/BACKLOG.md`
- Current modernization order: `docs/IMPLEMENTATION-PLAN.md`
- Reusable execution notes: `docs/skills/`
