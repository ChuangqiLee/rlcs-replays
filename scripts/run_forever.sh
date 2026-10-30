#!/bin/bash
# Keep a ballchasing.py command running unattended: restart it after a crash, stop when it
# finishes (exit 0) or hits a fatal error (exit 2, e.g. rejected API key or already running).
# Status lines also go to logs/<command>.log so other scripts can watch for them.
# Usage: bash scripts/run_forever.sh crawl|download [extra args]
cd "$(dirname "$0")/.."
source env.sh
log="logs/$1.log"
while true; do
    python scripts/ballchasing.py "$@"
    rc=$?
    if [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; then
        echo "[$(date -Is)] run_forever: ballchasing.py $* exited with $rc; not restarting" | tee -a "$log"
        exit "$rc"
    fi
    echo "[$(date -Is)] run_forever: ballchasing.py $* crashed with $rc; restarting in 60 s" | tee -a "$log"
    sleep 60
done
