# Runbook: SmartRestaurant on MySQL 8.4

> **Status 16 October 2026.** Production has run on **MySQL 8.4.11** (`smartrest-mysql`, 127.0.0.1:3308 / socket)
> since the cutover of 9 October 2026. Staging runs on its own MySQL 8.4.11 instance, `smartrest-staging-mysql`
> (127.0.0.1:3311, databases `smartrest_staging`, `smartrest_dash`, `smartrest_test`), since 16 October 2026; the full
> test suite runs against `smartrest_test` there. The app refuses to start on SQLite, MariaDB or MySQL below 8.4 when
> `APP_ENV=prod` or `REQUIRE_MYSQL=1` (`app/utils/db_check.py`); `flask smartrest db-info` is the read-only preflight.
> The MariaDB instance `smartrest-db` (127.0.0.1:3307) is no longer used by production or staging and is kept until its
> retirement is approved. Sections 1 to 5 below are the original plan of 9 October, kept as written.

*Written 9 October 2026 on branch `feature/mysql`. The private MySQL instance existed and was tested in isolation;
production then still ran on MariaDB until the cutover in section 5.*

## 1. What runs where

| | MariaDB (current production) | MySQL (prepared, isolated) |
|---|---|---|
| Server | MariaDB 11.8.6, binaries of aaPanel's install, `--no-defaults` | **MySQL Community Server 8.4.11 LTS**, official tarball in `/opt/mysql-8.4.11` (signature verified) |
| Service | `smartrest-db` (user `smartrest`) | `smartrest-mysql` (user `smartmysql`), **not enabled at boot** before cutover |
| Data | `/srv/smartrest/.mariadb/data` | `/srv/smartrest-mysql/data` |
| Config | command-line options in the unit | `/srv/smartrest-mysql/my.cnf` (copy in `deploy/mysql/my.cnf`), read **only** through `--defaults-file` |
| Network | 127.0.0.1:3307 | 127.0.0.1:3308 and the socket `/srv/smartrest-mysql/run/mysql.sock`; X Protocol (33060) off |
| App connection | `mysql+pymysql://smartrest:***@127.0.0.1:3307/smartrest?charset=utf8mb4` | `mysql+pymysql://smartrest:***@localhost/smartrest?unix_socket=/srv/smartrest-mysql/run/mysql.sock&charset=utf8mb4` |
| Credentials | `/srv/smartrest/.env` | root: `/root/smartrest-mysql-root.cnf`; app: `/root/smartrest-mysql-app.cnf` and `.url` (all root-only, 0600) |

**Never** run the plain `mysql` or `mysqldump` commands on this server for MySQL: `/usr/bin/mysql` is the *MariaDB*
client and `/etc/my.cnf` belongs to aaPanel's MariaDB. Always use the full path and our own option file:

```
/opt/mysql-8.4.11/bin/mysql     --defaults-file=/root/smartrest-mysql-root.cnf
/opt/mysql-8.4.11/bin/mysqldump --defaults-file=/root/smartrest-mysql-root.cnf --single-transaction --routines --set-gtid-purged=OFF smartrest
```

**Why the socket:** MySQL 8.4 logs users in with `caching_sha2_password`. Over plain TCP that needs either TLS or the
Python `cryptography` package; over the local socket PyMySQL works with no new dependency, and the app needs no
network port at all.

## 2. Install (done 9 Oct 2026; for a rebuild)

1. Download `mysql-8.4.11-linux-glibc2.28-x86_64-minimal.tar.xz` and its `.asc` from `cdn.mysql.com`; verify with the
   MySQL Release Engineering key, fingerprint `BCA4 3417 C3B4 85DD 128E C6D4 B7B3 B788 A8D3 785C` (from
   keyserver.ubuntu.com; valid to 2027-10-23). Extract to `/opt/mysql-8.4.11`, owner root, not writable by others.
   No apt packages are installed or removed (apt's `mysql-server` would replace the MariaDB client packages and fight
   aaPanel's MariaDB for port 3306).
2. `useradd --system --no-create-home --home-dir /srv/smartrest-mysql --shell /usr/sbin/nologin smartmysql`;
   create `/srv/smartrest-mysql/{data,run,log,tmp}` (data, log, tmp 0700 `smartmysql`; `run` 0750 `smartmysql:smartrest`
   so only the app's group can reach the socket).
3. `runuser -u smartmysql -- /opt/mysql-8.4.11/bin/mysqld --defaults-file=/srv/smartrest-mysql/my.cnf --initialize-insecure`,
   install `deploy/systemd/smartrest-mysql.service`, `systemctl daemon-reload && systemctl start smartrest-mysql`.
4. Immediately: set a random root password, create the databases `smartrest` and `smartrest_test` (utf8mb4,
   `utf8mb4_unicode_ci`) and the user `smartrest@localhost` with rights on those two only; store the credentials in the
   root-only files of section 1.
5. Check `ss -ltnp`: only `127.0.0.1:3308` for mysqld, nothing on 33060.

## 3. Load a copy of the data (repeatable)

1. Back up: `mariadb-dump --single-transaction` of `smartrest` (MariaDB), `instance/models`, `.env`, with `SHA256SUMS`,
   into a new root-only `/root/smartrest/backups/before_mysql_<time>/`.
2. Restore that dump into a temporary MariaDB database `test_<name>` and compare its row counts with live (proves the
   dump).
3. On MySQL, drop and recreate `smartrest` (empty), then build the schema with the application's own migrations:
   `env DATABASE_URL=<mysql url> APP_ENV=dev FLASK_APP=wsgi.py .venv/bin/flask db upgrade`.
   (A MariaDB dump cannot be fed to the MySQL client: it starts with MariaDB's `/*M!999999\- enable the sandbox mode */`.)
4. Copy and verify with `.venv/bin/python scripts/maria_to_mysql.py SOURCE_URL TARGET_URL --copy` (run from the repository folder): it
   compares the schemas table by table, copies every row in foreign-key order keeping the ids with foreign-key checks
   on, then checks row counts and a content checksum of every table, orphans for all 67 foreign keys and the
   AUTO_INCREMENT counters. Exit code 0 = identical.
5. `flask smartrest check-stock` against MySQL must say `consistent`. Drop the temporary MariaDB database.

## 4. Backups on MySQL

```
umask 077; /opt/mysql-8.4.11/bin/mysqldump --defaults-file=/root/smartrest-mysql-root.cnf --single-transaction \
  --routines --set-gtid-purged=OFF smartrest > /root/smartrest/backups/<name>/smartrest_mysql.sql
```

Restore into an empty database with `/opt/mysql-8.4.11/bin/mysql --defaults-file=/root/smartrest-mysql-root.cnf <db> < file`.
Binary logging is off (`skip-log-bin`): there is no replication, and backups are dumps.

## 5. Production cutover (only with explicit approval)

Planned downtime about **10 to 15 minutes** (the copy and its verification take well under a minute for about 25,000
rows; the rest is checks). MariaDB keeps running throughout and is not changed.

1. Announce the window. Take the backups of section 3, step 1, and prove the dump (step 2).
2. `systemctl stop smartrest-web` (**downtime starts**).
3. Take a final MariaDB dump (now nothing can write), prove it, then section 3, steps 3 to 5, from that dump.
4. `cp /srv/smartrest/.env /root/smartrest/backups/<name>/env.before_mysql`; set `DATABASE_URL` in `/srv/smartrest/.env`
   to the MySQL socket URL (value in `/root/smartrest-mysql-app.url`); keep the file owner `smartrest`, mode 0600.
5. In `smartrest-web.service` add `Requires=smartrest-mysql.service` and `After=smartrest-mysql.service` (instead of
   `smartrest-db`); `systemctl enable smartrest-mysql`; `systemctl daemon-reload`.
6. `systemctl start smartrest-web` (**downtime ends**). Checks: the login page answers 200 over HTTPS; each role's
   dashboard API answers with data (read-only requests); `flask smartrest check-stock` says consistent; the error log
   `/srv/smartrest-mysql/log/error.log` and gunicorn's log have no new errors.
7. Leave `smartrest-db` (MariaDB) running and untouched as the rollback source for at least two weeks.

## 6. Rollback

- **Before or during the cutover, or soon after with no new data:** `systemctl stop smartrest-web`; copy
  `env.before_mysql` back to `/srv/smartrest/.env`; restore the original `smartrest-web.service` (or remove the two MySQL
  lines); `systemctl daemon-reload && systemctl start smartrest-web`. The site is back on MariaDB with the data as it was
  at the cutover. About one minute.
- **After new data was written on MySQL:** either accept that those records are lost on MariaDB, or copy them back with
  the same script in the other direction (MySQL as source, a fresh MariaDB schema as target) and the same checks before
  switching.
- **Remove MySQL completely:** `systemctl disable --now smartrest-mysql`; `rm /etc/systemd/system/smartrest-mysql.service`;
  `systemctl daemon-reload`; `rm -rf /opt/mysql-8.4.11 /srv/smartrest-mysql /root/smartrest-mysql-*.cnf /root/smartrest-mysql-app.url`;
  `userdel smartmysql`. Nothing else on the server was changed by the install.

## 7. Maintenance

The tarball is not updated by apt. Check the MySQL 8.4 release notes monthly; to update, download and verify the new
tarball, stop `smartrest-mysql`, take a dump, point `ExecStart` and `basedir` at the new folder, start (8.4.x patch
releases upgrade the data dictionary in place), run `check-stock` and the read-only checks, and keep the old folder
until the new one is proven.

## 7. Staging on MySQL 8.4 (16 October 2026)

| | |
|---|---|
| Service | `smartrest-staging-mysql` (user `stagemysql`, enabled), config `/srv/smartrest-staging-mysql/my.cnf` = production settings with port 3311 and its own paths; unit file in `deploy/systemd/` |
| Databases | `smartrest_staging` (staging service), `smartrest_dash` (staging worktree), `smartrest_test` (test suite); users `stage_app`, `stage_test` |
| Migration | schema by `flask db upgrade`, rows copied from the staging SQLite files and compared value by value (24,941 and 24,819 rows, no differences, no orphan foreign keys; DATETIME keeps whole seconds, as in production) |
| Backups | `/root/smartrest/backups/mysql_staging_migration_20261016_122245` (production dump restore-tested: 32/32 table checksums equal; SQLite files; MariaDB dumps) |
| Rollback | restore the commented SQLite `DATABASE_URL` line in the staging `.env`, remove `REQUIRE_MYSQL=1`, restart the staging service (the SQLite files are kept unchanged) |
| Preflight | `flask --app wsgi smartrest db-info` prints backend, server version, database, migration and exits 1 when MySQL is required but not used |

