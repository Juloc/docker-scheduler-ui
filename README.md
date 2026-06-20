# docker-scheduler-ui

Simple FastAPI Weboberflaeche fuer Docker-Container, Gruppen und Start-/Stop-Zeitplaene.

## Funktionen

- Dashboard mit allen Docker-Containern, auch gestoppten
- Aktionen fuer einzelne Container: Start, Stop, Restart, Logs
- Gruppen mit Container-Reihenfolge und Wartezeit zwischen Containern
- Gruppenaktionen: Start, Stop, Restart
- Zeitplaene fuer einzelne Container oder Gruppen
- Taegliche Zeitplaene oder bestimmte Wochentage
- Aktiv/deaktiviert-Schalter fuer Zeitplaene
- Letzte 100 Logzeilen pro Container
- Basic Auth ueber `APP_USER` und `APP_PASSWORD`
- SQLite Persistenz in `/app/data/app.db`

Es gibt bewusst keine destruktiven Docker-Funktionen wie `docker rm`, Volume-Loeschung, Image-Prune oder System-Prune.

## Start mit Docker Compose

```bash
docker compose up -d --build
```

Danach ist die UI erreichbar unter:

```text
http://localhost:8099
```

Standard-Login aus `docker-compose.yml`:

```text
Benutzer: admin
Passwort: change-me
```

Bitte das Passwort vor produktiver Nutzung aendern.

## docker-compose.yml

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
      APP_USER: admin
      APP_PASSWORD: change-me
```

Der Docker-Socket ist notwendig, damit die App Container lesen und starten/stoppen/restarten kann. Wer Zugriff auf diese UI hat, kann damit Docker-Aktionen ausfuehren.

## Image fuer Portainer GitOps

Dieses Repository enthaelt einen GitHub-Actions-Workflow unter `.github/workflows/docker-publish.yml`. Bei Push auf `main` wird ein Image nach GitHub Container Registry gebaut:

```text
ghcr.io/juloc/docker-scheduler-ui:latest
```

Fuer ein separates Compose-/GitOps-Repository kann die Datei `docker-compose.image.yml` als Vorlage verwendet werden:

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
      APP_USER: ${APP_USER}
      APP_PASSWORD: ${APP_PASSWORD}
```

In Portainer die Variablen `APP_USER` und `APP_PASSWORD` im Stack setzen. Auf dem Docker-Host muss der Datenordner existieren:

```bash
sudo mkdir -p /opt/docker-scheduler-ui/data
```

## Lokale Entwicklung

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
APP_DB=./data/app.db APP_USER=admin APP_PASSWORD=change-me uvicorn app.main:app --reload --port 8099
```

Unter Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:APP_DB="./data/app.db"
$env:APP_USER="admin"
$env:APP_PASSWORD="change-me"
uvicorn app.main:app --reload --port 8099
```

## Persistenz

Gruppen und Zeitplaene liegen in SQLite unter `/app/data/app.db`. Im Compose-Setup wird `./data` nach `/app/data` gemountet, damit die Daten nach einem Neustart erhalten bleiben.
