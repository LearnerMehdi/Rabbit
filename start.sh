#!/usr/bin/env bash
# Orange Reader: the one way to start the app.
#   database (Docker) -> schema -> backend deps -> built UI -> API + UI on one port
# Settings: config.yaml. Secrets: ../.env. Ctrl+C stops the app; the database keeps
# running for fast restarts (`docker compose down` stops it).
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
VENV="$ROOT/../.venv"
PY="$VENV/bin/python"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "Docker is not installed."
docker info >/dev/null 2>&1 || die "Docker is not running (or this user can't reach it)."
command -v npm >/dev/null || die "Node.js/npm is not installed."

step "Python environment"
if [[ ! -x "$PY" ]]; then
  command -v uv >/dev/null || die "No venv at $VENV and uv is not installed to create one."
  uv venv "$VENV"
fi
stamp="$VENV/.orange-reader-requirements"
want="$(cat backend/requirements.txt backend/embedder/requirements.txt | sha256sum | cut -d' ' -f1)"
if [[ "$(cat "$stamp" 2>/dev/null)" != "$want" ]]; then
  if command -v uv >/dev/null; then
    uv pip install --python "$PY" -r backend/requirements.txt
  else
    "$PY" -m pip install -r backend/requirements.txt
  fi
  echo "$want" > "$stamp"
else
  echo "up to date"
fi

step "Database"
docker compose up -d --wait db
(cd backend && "$PY" -m ingest init-db)

step "Frontend"
if [[ ! -f frontend/node_modules/.package-lock.json || frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]]; then
  (cd frontend && npm ci --no-audit --no-fund)
fi
(cd frontend && npm run build --silent)

step "Starting Orange Reader"
cd backend
exec "$PY" -m api
