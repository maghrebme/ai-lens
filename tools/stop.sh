#!/usr/bin/env bash
# Ai-Lens — stop the news server and any stray process holding its port.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi
PORT="${PORT:-8420}"
PIDFILE="$ROOT/logs/server.pid"
stopped=0

# 1. The pid we recorded.
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null
    for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.2; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
    echo "Stopped server (pid $PID)"
    stopped=1
  fi
  rm -f "$PIDFILE"
fi

# 2. Anything else still holding our port.
for PID in $(lsof -ti:"$PORT" 2>/dev/null); do
  kill "$PID" 2>/dev/null && echo "Freed port $PORT (pid $PID)" && stopped=1
done

# 3. Stray Ai-Lens server processes started from this project.
for PID in $(pgrep -f "$ROOT/python/server.py|python/server.py" 2>/dev/null); do
  if [ "$(lsof -p "$PID" -a -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')" = "$ROOT" ]; then
    kill "$PID" 2>/dev/null && echo "Stopped stray server (pid $PID)" && stopped=1
  fi
done

[ "$stopped" = 1 ] || echo "Ai-Lens was not running."
exit 0
