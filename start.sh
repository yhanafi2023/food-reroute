#!/usr/bin/env bash
# One command to run FoodFlow locally: backend on :8000, frontend on :3000.
# First run creates the Python venv and installs npm packages.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -x "$ROOT/backend/.venv/bin/uvicorn" ]; then
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
fi
[ -f "$ROOT/backend/.env" ] || cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
[ -d "$ROOT/frontend/node_modules" ] || (cd "$ROOT/frontend" && npm install)
[ -f "$ROOT/frontend/.env.local" ] || cp "$ROOT/frontend/.env.example" "$ROOT/frontend/.env.local"

(cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --reload --port 8000) &
BACKEND=$!
(cd "$ROOT/frontend" && npm run dev) &
FRONTEND=$!
trap 'kill $BACKEND $FRONTEND 2>/dev/null' EXIT INT TERM
echo "FoodFlow: frontend http://localhost:3000  backend http://localhost:8000/docs"
wait
