# docker-scheduler-ui

A small FastAPI web UI for viewing Docker containers, managing ordered container groups, and scheduling start/stop/restart actions.

## Features

- Fluent 2 / Windows 11 inspired desktop-first UI with persistent `System` / `Dark` / `Light` theme
- Lists all Docker containers, including stopped containers
- Container actions: start, stop, restart, logs
- Ordered container groups with reverse stop order and per-container delay overrides
- Optional Docker health waiting before the next group step
- Group error policy: stop or continue
- Conflict policy: skip a new run or cancel the conflicting run and start the new one
- Manual run cancellation with detailed per-container progress
- Schedules for containers or groups, daily or selected weekdays
- Multiple NAS profiles with ping/mount readiness checks
- Wake-on-LAN with optional automatic wake before dependent actions
- Optional NAS-triggered group auto-start/auto-stop
- Generic webhook support with Home Assistant and Discord payload presets
- SQLite persistence with ordered schema migrations and pre-migration backups
- Configuration export/restore without detailed run logs
- Detailed log retention with compact long-term history
- Form login by default; Basic Auth remains optional
- Semantic version/build metadata and tagged GHCR release workflow

The app intentionally does not expose destructive Docker operations such as container removal, volume deletion, image prune, or system prune.

## Docker Compose

```yaml
services:
  docker-scheduler-ui:
    image: ghcr.io/juloc/docker-scheduler-ui:latest
    container_name: docker-scheduler-ui
    restart: unless-stopped
    ports:
      - "8099:8099"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /opt/docker-scheduler-ui/data:/app/data
    environment:
      AUTH_MODE: ${AUTH_MODE:-form}
      APP_USER: ${APP_USER:?Set APP_USER}
      APP_PASSWORD: ${APP_PASSWORD:?Set APP_PASSWORD}
      APP_SECRET: ${APP_SECRET:?Set APP_SECRET}
```

Create the persistent data directory before deployment:

```bash
sudo mkdir -p /opt/docker-scheduler-ui/data
```

Open `http://<host>:8099`.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `APP_USER` | required | Login username |
| `APP_PASSWORD` | required | Login password |
| `AUTH_MODE` | `form` | `form` for built-in login, `basic` for browser Basic Auth |
| `APP_SECRET` | required for form login | Secret used to sign session cookies |
| `AUTH_SESSION_SECONDS` | `43200` | Form-login session duration |
| `AUTH_COOKIE_SECURE` | `false` | Set `true` behind HTTPS |
| `APP_DB` | `/app/data/app.db` | SQLite database path |
| `APP_VERSION` | build/version file | Optional runtime version override |
| `APP_COMMIT` | `unknown` | Optional build commit identifier |

Generate a suitable secret with `openssl rand -hex 32`.

## Persistence and backup

Groups, schedules, NAS profiles, webhooks, settings and run history are stored in SQLite. Mount `/app/data` persistently.

Schema updates are versioned. Before a pending migration is applied, the current database is backed up under `/app/data/backups`.

`Settings` provides configuration export/restore. Normal exports intentionally exclude detailed run logs.

## Docker socket access

The Docker socket is required to inspect containers and perform start/stop/restart operations. Access to this UI must be treated as privileged because Docker socket access is effectively host-level control.

## NAS profiles and Wake-on-LAN

NAS profiles are configured under **NAS**. Each profile can use:

- ping reachability
- optional mount paths visible inside this application container
- Wake-on-LAN with MAC address
- optional automatic wake before a dependent group/schedule starts
- auto-start/auto-stop groups on readiness transitions

Mount checks only work for paths visible inside the application container, for example:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - /opt/docker-scheduler-ui/data:/app/data
  - /mnt/nas:/mnt/nas:ro
```

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
APP_DB=./data/app.db APP_USER=local-user APP_PASSWORD=local-password APP_SECRET=local-secret uvicorn app.main:app --reload --port 8099
```

Quality checks:

```bash
ruff check app tests
pytest
python -m compileall -q app
```

See `AGENTS.md` and `docs/` for architecture, design, security, versioning, backlog and reusable project workflows.
