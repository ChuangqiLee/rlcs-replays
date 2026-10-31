#!/bin/bash
# Keeps the dashboard alive. Launched in tmux session "dash"; cron re-launches tmux if missing.
D="$(cd "$(dirname "$0")" && pwd)"; PORT="${DASH_PORT:-18765}"
mkdir -p "$D/../logs"
while true; do
  if ! curl -s -m 5 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    echo "$(date '+%F %T') starting server" >> "$D/../logs/dashboard-watchdog.log"
    /usr/bin/python3 "$D/server.py" "$PORT" >> "$D/../logs/dashboard-server.log" 2>&1 &
    sleep 3
  fi
  sleep 30
done
