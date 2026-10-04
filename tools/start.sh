#!/usr/bin/env bash
# Ai-Lens — start the news server in the background.
# Writes logs/server.pid and logs/server.log; tools/stop.sh stops it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[ -f .env ] || cp .env.example .env
# shellcheck disable=SC1091
set -a; . ./.env; set +a

PORT="${PORT:-8420}"
HOST="${HOST:-127.0.0.1}"
PROBE_HOST="$HOST"; [ "$PROBE_HOST" = "0.0.0.0" ] && PROBE_HOST=127.0.0.1
PIDFILE="$ROOT/logs/server.pid"
LOGFILE="$ROOT/logs/server.out"
mkdir -p "$ROOT/logs" "$ROOT/data"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Ai-Lens already running (pid $(cat "$PIDFILE")) — http://${PROBE_HOST}:${PORT}${BASE_PATH:-}/"
  exit 0
fi

if lsof -ti:"$PORT" >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Run tools/stop.sh, or change PORT in .env." >&2
  exit 1
fi

# Python: project venv (has `anthropic` for enrichment), else the system python3.
PY="$ROOT/python/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

nohup "$PY" python/server.py >"$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

for _ in $(seq 1 40); do
  if curl -fsS "http://${PROBE_HOST}:${PORT}${BASE_PATH:-}/api/health" >/dev/null 2>&1; then
    echo "Ai-Lens started (pid $(cat "$PIDFILE")) — http://${PROBE_HOST}:${PORT}${BASE_PATH:-}/"
    exit 0
  fi
  sleep 0.25
done

echo "Server did not become healthy in time. Last log lines:" >&2
tail -n 20 "$LOGFILE" >&2
exit 1
