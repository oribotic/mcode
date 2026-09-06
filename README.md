# Meet Code

GDPR contact-QR kiosk: a public **remote** web app collects name/company/position/email/phone/url
and consent, generates a vCard QR code, and hands the print job to a **local** Mac agent that prints
it on a Brother QL700 (no OS print dialog) and is the only place personal data is persisted.

```
shared/       vCard / QR / label builders, used by both remote and local_agent
remote/       FastAPI web app + transient job queue (deploy to a VPS)
local_agent/  Print agent + SQLite store (runs on the Mac with the printer)
```

The whole repo is a single [Poetry](https://python-poetry.org/) project, split into optional
dependency groups so each side only installs what it needs:

- `main` — `shared`'s own deps (qrcode, pillow), always installed.
- `remote` — FastAPI/uvicorn/etc, needed to run the web service.
- `local` — requests/brother_ql/pyusb/python-dotenv, needed to run the print agent.

## Prerequisites

- Remote: Docker + Docker Compose on the VPS, a domain name for TLS (Caddy).
- Local: macOS with the Brother QL700 connected via USB, Python 3.11+, [Poetry](https://python-poetry.org/).

---

## 1. Remote service — production deployment (Scaleway VPS or similar)

Deploy the **whole repo**, not just the `remote/` folder — the Docker build needs `pyproject.toml`,
`poetry.lock` and `shared/` alongside `remote/`. Poetry itself runs *inside* the Docker build, so the
host only needs Docker + Docker Compose (no `pipx install poetry` on the VPS).

```bash
git clone <this-repo> && cd mcode/remote
./start.sh          # first run: creates .env from .env.example, then exits so you can edit it
$EDITOR .env         # set AGENT_API_KEY to a long random secret
./start.sh          # builds the image and starts the container via docker compose
./stop.sh            # stops and removes the container
```

`start.sh`/`stop.sh` wrap `docker compose up -d --build` / `docker compose down` and bind the app to
`127.0.0.1:8000` only — put a reverse proxy in front for TLS. A sample Caddy config is in
[remote/Caddyfile.example](remote/Caddyfile.example):

```bash
sudo cp remote/Caddyfile.example /etc/caddy/Caddyfile   # edit the hostname first
sudo systemctl reload caddy
```

The image itself installs only the `main` + `remote` Poetry groups (via `poetry install --only
main,remote`), so it never pulls in the local agent's USB/printer dependencies.

## 2. Remote service — local development (no Docker)

```bash
cd mcode
poetry install --with remote
AGENT_API_KEY=dev-secret poetry run uvicorn remote.app:app --reload
```

Run this from the repo root (not from `remote/`) so `shared` is importable. Visit `http://localhost:8000`.

## 3. Local agent — setup (Poetry)

```bash
cd mcode
poetry install --with local          # creates ./.venv, installs shared + the print-agent deps
cp local_agent/.env.example local_agent/.env
$EDITOR local_agent/.env             # set REMOTE_URL, AGENT_API_KEY (must match the remote's), PRINTER_IDENTIFIER
```

Run it in the foreground to test printing:

```bash
poetry run python local_agent/agent.py
```

## 4. Local agent — run as a background service (macOS LaunchAgent)

```bash
cp local_agent/com.mcode.agent.plist ~/Library/LaunchAgents/com.mcode.agent.plist
launchctl load ~/Library/LaunchAgents/com.mcode.agent.plist    # start now + on every login
launchctl unload ~/Library/LaunchAgents/com.mcode.agent.plist  # stop / disable
```

The plist points directly at `.venv/bin/python` created by `poetry install --with local`, so re-run
that command after pulling dependency changes — no separate activation step is needed for the
LaunchAgent. Logs go to `local_agent/agent.log`.

Working on both remote and local_agent on the same machine? Run `poetry install --with remote,local`
once to get everything in the same `.venv`.

---

## Configuration reference

| Variable | Where | Purpose |
|---|---|---|
| `AGENT_API_KEY` | remote `.env`, local_agent `.env` | Shared secret authenticating the local agent to the remote job queue. Must match on both sides. |
| `REMOTE_URL` | local_agent `.env` | Base URL of the deployed remote service. |
| `PRINTER_IDENTIFIER` | local_agent `.env` | brother_ql USB identifier for the QL700 (default `usb://0x04f9:0x2042`). |
| `POLL_INTERVAL_SECONDS` | local_agent `.env` | How often the agent polls for new jobs (default `3`). |
| `LOCAL_DB_PATH` | local_agent `.env` | Path to the local SQLite contacts database. |
