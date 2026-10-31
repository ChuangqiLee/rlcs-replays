#!/bin/bash
# Idempotent: called by cron every 5 min and @reboot on the SAME login node only.
D="$(cd "$(dirname "$0")" && pwd)"
[ "$(hostname -s)" = "login006" ] || exit 0
tmux has-session -t dash 2>/dev/null || tmux new-session -d -s dash "bash $D/watchdog.sh"
