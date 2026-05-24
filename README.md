# Automatr

Automatr is an experimental local automation workbench for managing Docker-backed
desktop containers from a web UI. It combines a FastAPI host service, container
runtime scripts, noVNC access, and a Next.js control panel for creating and
running repeatable GUI automation workflows in a trusted local environment.

This is prototype infrastructure, not a hosted product. It is designed for a
machine you control and a network you trust.

## Current Status

Automatr is a local systems prototype. The host API can create and control
Docker containers, expose noVNC sessions, persist automation graphs in SQLite,
export runnable scripts, and start automation jobs in runtime containers.
XMPP/chat support is present as an experimental integration.

## Screenshots and Demo

TODO - add screenshots or a short GIF after capturing a local run. Suggested
paths:

- `docs/screenshots/host-dashboard.png`
- `docs/screenshots/container-view.png`
- `docs/screenshots/automation-editor.png`
- `docs/screenshots/vnc-panel.png`

## Architecture

```text
Browser UI (Next.js, src/)
  -> FastAPI host API (app.py)
  -> Docker runtime containers
  -> VNC/noVNC desktop session
  -> queued automation runner and exported scripts
```

Runtime state is stored under `data/` by default, including the SQLite database
and container-specific folders. These files are local runtime artifacts and
should not be committed.

## Prerequisites

- Python 3.11 or newer
- Node.js 22 or newer and npm
- Docker Engine available to the user running the host API
- Local access to the Docker socket or Docker CLI
- Optional: Caddy/Prosody scripts if using the local noVNC/XMPP helper scripts
- Optional: `notify-send` if using host desktop notifications

## Backend Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Build the runtime container image:

```bash
docker build -f Dockerfile.runtime -t automatr-runtime:dev .
```

Start the host API:

```bash
uvicorn app:app --host 127.0.0.1 --port 8766
```

Health check:

```bash
curl http://127.0.0.1:8766/health
```

There is also a helper script for local development:

```bash
bin/dev-host-api
```

## Frontend Setup

The frontend package lives in `src/`.

```bash
cd src
npm ci
npm run dev
```

Open `http://127.0.0.1:3000` and keep the host API running at
`http://127.0.0.1:8766`.

Frontend checks:

```bash
cd src
npm run lint
npm run build
```

There is also a helper script:

```bash
bin/dev-web
```

## Smoke Check

With the host API running, `scripts/smoke_endpoints.sh` exercises the main API
paths. It creates local runtime state and may start/stop Docker containers.

```bash
BASE=http://127.0.0.1:8766 scripts/smoke_endpoints.sh
```

## Security and Local-Only Notes

- Automatr controls Docker containers. Anyone who can reach the host API can
  potentially create, start, stop, or interact with local runtime containers.
- Run the host API on `127.0.0.1` unless you have reviewed the Docker, VNC, and
  automation risks for every client on the network.
- noVNC/VNC exposes an interactive desktop session for runtime containers. Treat
  noVNC ports as local-only unless you have added authentication, TLS, and
  network controls outside this repo.
- CORS defaults are for local development. Keep `AUTOMATR_CORS_ORIGINS`
  restricted to the frontend origins you actually use.
- `.env.example` includes development XMPP defaults. `NEXT_PUBLIC_*` frontend
  variables are visible in the browser, so do not place production secrets in
  `NEXT_PUBLIC_XMPP_PASSWORD` or similar values.
- The default `change-me-dev-only` password is only a local development
  placeholder. Change it before using XMPP/chat beyond an isolated local setup.
- Treat generated automation scripts and container-mounted files as executable
  local code. Review them before running on important systems.

## Repository Layout

```text
.
├── app.py                  # FastAPI host API
├── automatr_config.py      # Environment-backed configuration
├── db.py                   # SQLite persistence helpers
├── runner.py               # Runtime container automation runner
├── Dockerfile.runtime      # Docker image for automation containers
├── bin/                    # Local helper scripts and runtime actions
├── scripts/                # Smoke checks and operational helpers
├── data/                   # Ignored runtime state
└── src/                    # Next.js frontend
```
