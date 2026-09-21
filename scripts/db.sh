#!/usr/bin/env bash
# Private dev/test MariaDB instance (port 3307). Does not touch any other database server on the machine.
# Usage: ./scripts_db.sh start|stop|status|shell
B=/www/server/mysql
D="$(cd "$(dirname "$0")/.." && pwd)/.mariadb"
case "$1" in
  start)
    if [ -S "$D/mysql.sock" ]; then echo "already running"; exit 0; fi
    nohup $B/bin/mariadbd --no-defaults --user=root --basedir=$B --datadir=$D/data --socket=$D/mysql.sock \
      --pid-file=$D/mysql.pid --port=3307 --bind-address=127.0.0.1 --innodb-buffer-pool-size=64M \
      --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci --max-connections=40 \
      > $D/server.log 2>&1 &
    for i in $(seq 1 30); do [ -S "$D/mysql.sock" ] && break; sleep 1; done
    [ -S "$D/mysql.sock" ] && echo started || { echo "failed, see $D/server.log"; exit 1; } ;;
  stop) [ -f "$D/mysql.pid" ] && kill "$(cat $D/mysql.pid)" && echo stopping ;;
  status) [ -S "$D/mysql.sock" ] && echo running || echo stopped ;;
  shell) exec mariadb --no-defaults -uroot -S "$D/mysql.sock" "${@:2}" ;;
esac
