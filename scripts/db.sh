#!/usr/bin/env bash
# Private MariaDB for SmartRestaurant on 127.0.0.1:3307. Since 7 Oct 2026 it runs as the unprivileged `smartrest`
# user under systemd (unit: deploy/systemd/smartrest-db.service, installed in /etc/systemd/system). Run as root.
D="$(cd "$(dirname "$0")/.." && pwd)/.mariadb"
case "$1" in
  start|stop|status|restart) systemctl "$1" smartrest-db ;;
  shell) exec /www/server/mysql/bin/mariadb --no-defaults -uroot -S "$D/mysql.sock" "${@:2}" ;;
  *) echo "usage: $0 start|stop|status|restart|shell" ;;
esac
