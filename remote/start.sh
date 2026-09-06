#!/usr/bin/env bash
# Initializes .env if missing, then builds and starts the remote service via docker compose.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
	cp .env.example .env
	echo "Created remote/.env from .env.example - edit AGENT_API_KEY before relying on it, then re-run." >&2
	exit 1
fi

docker compose up -d --build
docker compose ps
