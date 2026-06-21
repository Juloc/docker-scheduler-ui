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
      AUTH_MODE: basic
      APP_USER: admin
      APP_PASSWORD: change-me
      APP_SECRET: change-this-secret
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
      APP_USER: ${APP_USER}
      APP_PASSWORD: ${APP_PASSWORD}
      APP_SECRET: ${APP_SECRET:-change-this-secret}
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

Change the default password before exposing the UI.

## Persistence

Groups, schedules, and run logs are stored in SQLite. Mount `/app/data` to keep data across container restarts.

## Docker Socket Access

The Docker socket is required so the app can list containers and run start/stop/restart actions. Anyone with access to the UI can perform those Docker actions.

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
