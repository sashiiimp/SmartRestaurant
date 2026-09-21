#!/usr/bin/env bash
# Temporary demo deployment: gunicorn straight on a firewall-open port. Touches no other service (no nginx changes).
# Usage: scripts/deploy_demo.sh start|stop|status     (port 39500, inside the 39000-40000 range the firewall already allows)
cd "$(dirname "$0")/.."
PID=/tmp/smartrest-gunicorn.pid; PORT=39500
case "$1" in
  start)
    scripts/db.sh start >/dev/null
    [ -f $PID ] && kill "$(cat $PID)" 2>/dev/null && sleep 1
    APP_ENV=dev setsid nohup .venv/bin/gunicorn -w 2 --timeout 120 -b 0.0.0.0:$PORT --pid $PID \
      --access-logfile instance/gunicorn-access.log --error-logfile instance/gunicorn-error.log wsgi:app \
      > /dev/null 2>&1 < /dev/null &
    sleep 4; curl -s -o /dev/null -w "local check: HTTP %{http_code}\n" http://127.0.0.1:$PORT/login ;;
  stop) [ -f $PID ] && kill "$(cat $PID)" && rm -f $PID && echo stopped ;;
  status) [ -f $PID ] && kill -0 "$(cat $PID)" 2>/dev/null && echo "running (pid $(cat $PID))" || echo stopped ;;
esac
