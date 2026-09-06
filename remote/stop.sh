#!/usr/bin/env bash
# Stops and removes the remote service container(s).
set -euo pipefail
cd "$(dirname "$0")"

docker compose down
