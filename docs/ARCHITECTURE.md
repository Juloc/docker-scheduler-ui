# Architecture

## Current stack
- FastAPI application
- Jinja2 server-rendered UI
- Docker SDK for Python
- APScheduler
- SQLite persisted at `/app/data/app.db`

## Target boundaries
Keep the existing stack. Refactor by responsibility rather than rewriting:

- `routes/`: HTTP request parsing, redirects and view models only.
- `services/`: scheduler, execution, NAS, notifications, backup/version checks.
- `repositories/` or the existing database module: persistence only; no UI logic.
- `docker_ops`: narrow Docker adapter. Destructive operations remain out of scope.
- `templates/` and `static/`: Fluent 2 UI shell and compact work surfaces.

## Execution engine
Manual actions and scheduled actions must use one execution engine.

Required behavior:
- ordered group start
- reverse-order group stop by default
- per-step delay
- optional Docker health wait with timeout; delay fallback if no healthcheck exists
- stop-on-error default, continue-on-error optional
- conflict policy per group/schedule: `skip` default or `cancel_and_start`
- prevent competing actions against the same container
- independent groups may run concurrently when their container sets do not overlap
- controlled cancellation with durable run/step status

## Persistence
SQLite remains the single-instance persistence layer.

Schema changes use explicit ordered migrations. Before a migration that changes schema/data, create a backup. Startup applies pending migrations before scheduler startup.

Configuration export/import includes groups, schedules, NAS profiles and settings, but excludes detailed run logs by default.

## NAS model
Move from one global NAS configuration to NAS profiles. A profile may define ping/readiness checks, visible mount checks, Wake-on-LAN settings and check intervals. Groups/schedules may reference one profile.

## Logging retention
Default: retain detailed run/step logs for 30 days. Older history is compacted to summary records rather than kept indefinitely in full detail. Retention is configurable.

## Non-goals
- Docker Compose editing/deployment management
- general NAS administration
- workflow-builder/DAG engine
- destructive Docker maintenance
- multi-user RBAC until a real requirement exists
