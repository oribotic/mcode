#!/usr/bin/env bash
# Pulls the latest git changes and rebuilds/restarts the remote service only if something changed.
# Run this on the server (e.g. via cron or manually) to pick up new commits.
set -euo pipefail
cd "$(dirname "$0")/.."

before=$(git rev-parse HEAD)
git pull --ff-only
after=$(git rev-parse HEAD)

if [ "$before" = "$after" ]; then
	echo "No changes ($before) - skipping rebuild."
	exit 0
fi

echo "Updated $before -> $after, rebuilding..."
cd remote
docker compose up -d --build
docker compose ps
