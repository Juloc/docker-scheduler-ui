# docker-scheduler-ui

A small FastAPI web UI for viewing Docker containers, managing ordered container groups, and scheduling start/stop/restart actions.

## Features

- Lists all Docker containers, including stopped containers
- Container actions: start, stop, restart, logs
- Ordered container groups with delay between containers
- Group actions with per-container execution logs
- Schedules for containers or groups
- Daily schedules or selected weekdays
- Manual schedule runs with detailed run logs
- Lazy log preview on the dashboard
- Optional NAS guard for groups and schedules:
  - ping-based NAS reachability checks
  - optional mount path checks
  - block start/restart for NAS-dependent groups while NAS is unavailable
  - auto-start and auto-stop selected groups on NAS status changes
- SQLite persistence in `/app/data/app.db`
- Configurable authentication:
  - `AUTH_MODE=basic` for browser Basic Auth
  - `AUTH_MODE=form` for the built-in login page

The app intentionally does not expose destructive Docker operations such as container removal, volume deletion, image prune, or system prune.

## Docker Compose

```yaml
services:
  docker-scheduler-ui:
    build: .
    container_name: docker-scheduler-ui
    restart: unless-stopped
    ports:
      - "8099:8099"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/app/data
    environment:
      AUTH_MODE: ${AUTH_MODE:-basic}
      APP_USER: ${APP_USER:?Set APP_USER}
      APP_PASSWORD: ${APP_PASSWORD:?Set APP_PASSWORD}
      APP_SECRET: ${APP_SECRET:?Set APP_SECRET}
```

Start it with:

```bash
docker compose up -d --build
```

Open:

```text
http://localhost:8099
```

## Image-based GitOps Compose

If you publish the image to a registry, use an image-only Compose file in a separate GitOps repository:

```yaml
services:
  docker-scheduler-ui:
    image: ghcr.io/<owner>/docker-scheduler-ui:latest
    container_name: docker-scheduler-ui
    restart: unless-stopped
    ports:
      - "8099:8099"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /opt/docker-scheduler-ui/data:/app/data
    environment:
      AUTH_MODE: ${AUTH_MODE:-basic}
      APP_USER: ${APP_USER:?Set APP_USER}
      APP_PASSWORD: ${APP_PASSWORD:?Set APP_PASSWORD}
      APP_SECRET: ${APP_SECRET:?Set APP_SECRET}
```

Create the host data directory before deploying:

```bash
sudo mkdir -p /opt/docker-scheduler-ui/data
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `APP_USER` | `admin` | Login username |
| `APP_PASSWORD` | `change-me` | Login password |
| `AUTH_MODE` | `basic` | `basic` for browser auth, `form` for the built-in login page |
| `APP_SECRET` | `APP_PASSWORD` value | Secret used to sign form-login session cookies |
| `AUTH_SESSION_SECONDS` | `43200` | Form-login session duration in seconds |
| `AUTH_COOKIE_SECURE` | `false` | Set to `true` when serving the app over HTTPS |
| `APP_DB` | `/app/data/app.db` | SQLite database path |

Do not commit real credentials or secrets. Set them as environment variables in your deployment system.

Generate a suitable `APP_SECRET` with:

```bash
openssl rand -hex 32
```

## Persistence

Groups, schedules, and run logs are stored in SQLite. Mount `/app/data` to keep data across container restarts.

## Docker Socket Access

The Docker socket is required so the app can list containers and run start/stop/restart actions. Anyone with access to the UI can perform those Docker actions.

## NAS Guard

NAS checks are configured in the web UI under **NAS**. The app can ping a configured host or IP address and can also verify that configured mount paths exist.

Mount checks only work for paths that are visible inside the `docker-scheduler-ui` container. If you want the app to verify host paths, mount those paths into the app container, for example:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - ./data:/app/data
  - /mnt/media:/mnt/media:ro
```

Group options:

- **Require NAS before start/restart** skips start or restart actions when NAS is not ready.
- **Auto-start this group when NAS becomes ready** starts the group when NAS changes from not ready to ready.
- **Auto-stop this group when NAS goes offline** stops the group when NAS changes from ready to not ready.

Schedule option:

- **Require NAS to be ready before running** skips the schedule when NAS is not ready.

Skipped runs are written to the run log with status `skipped`.

## Local Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
APP_DB=./data/app.db APP_USER=admin APP_PASSWORD=change-me uvicorn app.main:app --reload --port 8099
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:APP_DB="./data/app.db"
$env:APP_USER="admin"
$env:APP_PASSWORD="change-me"
uvicorn app.main:app --reload --port 8099
```
