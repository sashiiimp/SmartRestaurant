# Release runbook: system-integration + nav-consolidation + ui-final (October 2026)

Production today: `/srv/smartrest` at `56d439f`, MySQL 8.4 (`smartrest-mysql`, socket
`/srv/smartrest-mysql/run/mysql.sock`), schema revision `9b4f2c7e1d63`, web `smartrest-web` (gunicorn as `smartrest`),
no forecast timer (the last forecast was a manual run on 11 Oct, so the live forecast stops on 17 Oct).

Release: branch `release-check` in the staging repository, a fast-forward of `56d439f`. **Nothing in this file has
been run on production.** Every step below was rehearsed on copies of the production database in an isolated MySQL
8.4 server (section 5). Run it only after explicit approval.

## 1. What the release changes

| From | Change | Production impact |
|---|---|---|
| system-integration | daily forecast (`flask smartrest forecast-daily`) + `smartrest-forecast.timer`; pre-orders get customer name, contact, pickup time and a *completed* status; dashboard additions; viva guide | **one migration** `c4e1a7b9d052` (additive: 4 nullable columns, status check allows `completed`); **one new timer** |
| nav-consolidation | 23 menu pages become 14 (tabs); old addresses redirect; Role access tab | none (pages only) |
| ui-final | one design language, dashboards, Reports & Analytics groups, Forecasting tabs | none (pages only) |
| release-check | end-to-end workflow test, Served table, phone card lists for Purchasing, WebKit-safe walkthrough, this runbook | none (pages and tests only) |

No new Python package. No change to ML training or prediction, recommendation formulas, stock calculations, roles or
permissions. Static files are served with `Cache-Control: no-cache` and an ETag, so browsers pick up the new CSS/JS.

## 2. Before the deployment

1. Approval from the project owner, and a quiet moment (not during a demo).
2. Backup folder, root only:
   ```
   TS=$(date +%Y%m%d_%H%M%S); B=/root/smartrest/backups/release_$TS; mkdir -m 700 -p $B
   /opt/mysql-8.4.11/bin/mysqldump --defaults-file=/root/smartrest-mysql-root.cnf --single-transaction --routines \
     --triggers --no-tablespaces --set-gtid-purged=OFF smartrest | gzip > $B/smartrest_db.sql.gz
   tar czf $B/files.tgz --exclude=.venv -C /srv smartrest            # code, instance/models, .env
   runuser -u smartrest -- git -C /srv/smartrest bundle create /tmp/prod.bundle --all && mv /tmp/prod.bundle $B/
   git -C /srv/smartrest rev-parse HEAD > $B/HEAD
   cp -a /etc/systemd/system/smartrest-web.service /etc/systemd/system/smartrest-web.service.d $B/
   (cd $B && sha256sum * > SHA256SUMS)
   ```
   Check the dump is complete: `gunzip -c $B/smartrest_db.sql.gz | grep -c 'CREATE TABLE'` gives 32.
3. Row counts for comparison after the upgrade (`select count(*)` per table into `$B/rows_before.txt`).

## 3. Deployment steps

1. Bring the release into the production repository (fast-forward only, nothing else changes):
   ```
   runuser -u smartstage -- git -C /srv/smartrest-dashboard bundle create /tmp/release.bundle 56d439f..release-check
   runuser -u smartrest -- git -C /srv/smartrest fetch /tmp/release.bundle release-check:release
   runuser -u smartrest -- git -C /srv/smartrest merge --ff-only release
   ```
2. Database upgrade (additive, about 3 s on a copy of production):
   `cd /srv/smartrest && runuser -u smartrest -- .venv/bin/flask --app wsgi db upgrade`, then `db current` shows
   `c4e1a7b9d052 (head)`. Compare row counts with `rows_before.txt` (only `alembic_version` changes).
3. Forecast timer (production only; the staging timer `smartrest-staging-forecast` uses its own database and stays):
   ```
   cp /srv/smartrest/deploy/systemd/smartrest-forecast.service /srv/smartrest/deploy/systemd/smartrest-forecast.timer /etc/systemd/system/
   systemctl daemon-reload && systemctl enable --now smartrest-forecast.timer
   systemctl start smartrest-forecast.service && journalctl -u smartrest-forecast.service -n 20 --no-pager
   ```
   The first run makes today plus 6 days; later hourly runs answer `already_done` (one run per Colombo day, a
   row lock against overlap, and systemd never starts the oneshot service twice at once).
   Leave `smartrest-web.service` and its `mysql.conf` drop-in as they are: they already require MySQL. The unit in
   `deploy/systemd/` is the same thing written as one file and can be installed later.
4. Preflight (from the MySQL fail-fast release on): `cd /srv/smartrest && runuser -u smartrest -- env APP_ENV=prod
   .venv/bin/flask --app wsgi smartrest db-info` must print `backend: mysql`, server `8.4.x` and exit 0; only then
   reload the web app without downtime: `systemctl kill -s HUP --kill-whom=main smartrest-web`.

## 4. Checks after the deployment

- `curl -sI https://smartrest.developerstudio.space/login` is 200; `/admin` redirects to the login page; an API call
  without a session gives 401.
- `/static/css/app.css` contains `14 final UI pass`.
- `db current` is `c4e1a7b9d052`; forecasts for today to today + 6 exist for every active menu item, no duplicates:
  `select count(distinct target_date), count(*) from forecasts where is_latest=1 and target_date between curdate() and curdate()+interval 6 day`.
- `tail instance/gunicorn-error.log` and `instance/smartrest.log`: no new errors.
- The owner logs in to each role once (passwords are known only to the owner) and opens the dashboards.

## 5. Rehearsal results (14 Oct 2026, isolated MySQL 8.4 on 127.0.0.1:3310, never the production server)

| Rehearsal | Result |
|---|---|
| Production dump (read-only, `--single-transaction`) loaded into the isolated server | 32 tables, 24,590 rows, counts identical table by table |
| `flask db upgrade` with the release | `9b4f2c7e1d63 -> c4e1a7b9d052` in 3.3 s; 4 nullable columns; status check allows `completed` |
| Data preserved | `CHECKSUM TABLE` of all 30 other tables identical to production (model_versions equal apart from the artifact path changed for the copy) |
| Daily forecast on the copy | first run: 7 days x 10 items = 70 forecasts, 14-20 Oct; second run `already_done`; no duplicate rows |
| Release served on the copy, browser walkthrough (Chromium) | kitchen, inventory, admin and responsive checks all ok (temporary passwords set on the copy only) |
| Rollback A (code only) | production code `56d439f` on the upgraded schema: 23 pages and 12 API calls for the 3 roles all 200; confirmed pre-orders still counted |
| Rollback B (schema too) | `db downgrade 9b4f2c7e1d63`: back to the old revision, completed pre-orders become confirmed, the 4 columns are removed, the other 30 tables identical to production |

## 6. Rollback

Choose the smallest step that fixes the problem. All keep the data entered after the deployment unless stated.

**A. Code only (preferred; keeps every record).**
```
systemctl disable --now smartrest-forecast.timer            # the old code has no forecast-daily command
runuser -u smartrest -- git -C /srv/smartrest reset --keep 56d439f
systemctl kill -s HUP --kill-whom=main smartrest-web
```
The schema stays at `c4e1a7b9d052`; the old code ignores the 4 new columns (rehearsed). Pre-orders marked *completed*
are not counted by the old prep plan (it counts *confirmed* only). Do not run `flask db` commands with the old code (it
does not know revision `c4e1a7b9d052`).

**B. Code and schema.** With the release code still in place, first `runuser -u smartrest -- .venv/bin/flask --app wsgi db downgrade 9b4f2c7e1d63`
(completed pre-orders become confirmed; customer name, contact and pickup time entered after the deployment are
removed), then step A.

**C. Last resort: restore the backup.** Stop the web app, restore `$B/smartrest_db.sql.gz` into `smartrest`, restore
`files.tgz`, start the web app. This loses everything recorded after the deployment; take a fresh dump first.
