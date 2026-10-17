#!/usr/bin/env bash
# Demo web app (gunicorn, port 39500) as the unprivileged `smartrest` user under systemd
# (unit: deploy/systemd/smartrest-web.service). Run as root. `reload` picks up code changes without downtime.
# Flask CLI commands must run as the same user, e.g.:
#   runuser -u smartrest -- env FLASK_APP=wsgi.py .venv/bin/flask smartrest demo-reset
case "$1" in
  start|restart) systemctl restart smartrest-mysql smartrest-web
                 sleep 3; curl -s -o /dev/null -w "local check: HTTP %{http_code}\n" http://127.0.0.1:39500/login ;;
  reload) systemctl reload smartrest-web ;;
  stop) systemctl stop smartrest-web ;;
  status) systemctl --no-pager status smartrest-web smartrest-mysql | grep -E "Active|●" ;;
  *) echo "usage: $0 start|restart|reload|stop|status" ;;
esac
