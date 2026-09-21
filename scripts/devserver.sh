#!/usr/bin/env bash
# Start/stop the dev server on port 5055 (used by the UI smoke test). Usage: scripts/devserver.sh start|stop
cd "$(dirname "$0")/.."
PID=/tmp/smartrest-dev.pid
export FLASK_APP=wsgi.py
case "$1" in
  start) [ -f $PID ] && kill "$(cat $PID)" 2>/dev/null; sleep 1
         setsid nohup .venv/bin/flask run --port 5055 > /tmp/smartrest-dev.log 2>&1 < /dev/null & echo $! > $PID
         for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:5055/login && break; sleep 0.5; done; echo started ;;
  stop) [ -f $PID ] && kill "$(cat $PID)" && rm -f $PID && echo stopped ;;
esac
