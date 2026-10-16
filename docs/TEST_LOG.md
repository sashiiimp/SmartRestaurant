# SmartRestaurant: test log

Results of running the plan in `TESTING.md` on 21 Sep 2026 (Python 3.14.4, MariaDB 11.8.6, Chromium 153 via Playwright).
Everything below was actually run; nothing is estimated.

## 1. Automated tests

`pytest -q`: **144 passed**, 0 failed (including 7 MariaDB constraint tests, the MariaDB concurrency test and 2 timing tests).
Coverage of `app/services` + `app/ml`: **91%** (target 80%).

| Area | File | Tests | TESTING.md ids |
|---|---|---|---|
| Architecture import rules, service graph | `tests/test_architecture.py` | 6 | ARC-1 |
| Route x role matrix (every route x anonymous/admin/kitchen/inventory) | `tests/api/test_rbac.py` | 5 | SEC-1 |
| Login, lockout, deactivation, hashing, logout, CSRF, last admin | `tests/api/test_auth.py` | 10 | SEC-2..7, SEC-11, SEC-12 |
| API envelope, validation, escaping, SQL-quote inputs, idle timeout, empty DB, settings, CSV | `tests/api/test_flows.py` | 13 | SEC-7..10, VAL, NEG-1, A13 |
| Prep quantity table 4.1 | `tests/unit/test_prep_formula.py` | 10 | REC-1 |
| Features: hand lags, no leakage, missing data | `tests/unit/test_features.py` | 6 | ML-1..3, ML-8 |
| Training, metrics, selection, determinism | `tests/unit/test_ml_train.py` | 5 | ML-4, ML-5 |
| Decisions, kitchen recording, daily summary | `tests/integration/test_kitchen_recommendation.py` | 22 | REC-2, KIT-1, KIT-2, VAL-1..4 |
| Requirements 4.2, reorder 4.3, alerts 4.4 | `tests/integration/test_requirements_reorder_alerts.py` | 18 | REQ-1/2, ROR-1, ALT-1..4 |
| FEFO scenario 4.5, stock validation, concurrency (MariaDB) | `tests/integration/test_stock_service.py` | 12 | INV-1..3, VAL-5/6 |
| CSV import (sales, holidays, weather) | `tests/integration/test_import_service.py` | 13 | IMP-1..5 |
| Forecast runs: skip, fail, baseline fallback, re-run, activation, backfill | `tests/integration/test_forecast_service.py` | 9 | ML-6, ML-7, ML-9 |
| Menu, recipes, promotions | `tests/integration/test_catalog_services.py` | 4 | A4, A5, A15 |
| DB constraints on MariaDB | `tests/integration/test_schema.py` | 7 | NFR8 |
| Migrations = models, `outlet_id` rule | `tests/integration/test_migrations.py` | 2 | DB-1, DB-2 |
| Timing | `tests/perf/test_timing.py` | 2 | PERF-1, PERF-2 |

Notable results:
- Every hand-calculated value of `TESTING.md` 4.1-4.5 (54, 60, 50 for the Decimal edge, chicken 15.48 / short 3.48,
  lettuce short 0.31, reorder 25 / 30 / 15, cover 0.9 days, FEFO movements -4 / -1) is asserted and passes.
- INV-3 found a real MariaDB 11 behaviour: `SELECT ... FOR UPDATE` after a snapshot read can fail with error 1020
  ("record has changed since last read"). Stock-out and wastage now retry on a fresh snapshot; with two parallel
  stock-outs of 8 against 10, exactly one succeeds and stock never goes negative.
- The test that walks all routes found no route without a declared role rule.

## 2. Performance (NFR2), seeded database (750 days x 10 items), `pytest -m perf -s`

| Measure | Requirement | Result |
|---|---|---|
| PERF-1 forecast run, 10 items x 7 days | under 5 s | **0.27 s** |
| PERF-2 slowest page or API request over 10 repeats | under 3 s | **0.23 s** (inventory dashboard API; most under 0.1 s) |
| PERF-2 p95 of read APIs | under 1 s | max 0.23 s |
| PERF-3 training (informational) | under 60 s | about 11 s on this 2-core machine |

The Flask test client excludes network time.

## 3. Browser tests (Playwright, `tests/ui/smoke.py`), run against the seeded database

These drive the real pages in headless Chromium and act as the scripted UAT of `TESTING.md` section 8, executed by
the builder (not by a volunteer; see section 5).

| Script | Steps exercised | Result |
|---|---|---|
| K-UAT (kitchen1, 390 px wide) | login lands on `/kitchen`; forecast table; prep cards; Accept; Override without reason shows the field error and keeps the form; Override with reason; add prepared quantity; served entry shows the "served above prepared" warning; negative waste quantity shows the field error; valid waste saved; dashboard tiles; requirements shows chicken short; `/admin` returns 403 | pass |
| I-UAT (inventory1, 1280 px) | dashboard shows chicken alerts and reorder; stock list of 20 ingredients; Add ingredient with empty form shows errors; stock-in of 100 kg chicken; stock-out of 9999 kg refused with the available quantity; wastage record; ingredient demand and reorder pages; `/kitchen` returns 403 | pass |
| A-UAT (admin) | dashboard tiles; monitoring tabs (sales, forecast accuracy, waste); train a new model from the UI; activate it; run forecast now; CSV import with one bad row (1 accepted, 1 rejected with reason) then commit; recipe editor opens; create a user (empty form errors first), deactivate it; deactivating the last admin is refused with a message; `/kitchen` returns 403 | pass |
| Responsive (NFR4) | all 17 role pages at 360, 768 and 1280 px: no page-level horizontal scroll | pass |
| Console | no JavaScript errors or failed requests on any page during the runs | pass |

Screenshots of every page are in `docs/screenshots/`.

## 4. Security review checklist (NFR5)

| Check | Result |
|---|---|
| Passwords stored as salted scrypt hashes; never in responses (asserted) | pass |
| Server-side role check on every route (matrix test); blueprint-level `before_request` for role pages | pass |
| CSRF on all POST/PUT/PATCH (page forms and API) | pass |
| Output escaped (Jinja autoescape; Vue text interpolation; no `\|safe`) | pass (asserted for a `<script>` name) |
| Parameterised queries only (SQLAlchemy); quote characters in filters and login give 4xx/401, no error | pass |
| Login lockout, generic error for unknown user / wrong password / deactivated user | pass |
| Session cookie HttpOnly, SameSite=Lax, Secure in prod; 30 min idle timeout (asserted); `Cache-Control: no-store` for logged-in pages | pass |
| No secrets in git (`.env` ignored; `git log -p` shows placeholders only); prod refuses the default `SECRET_KEY` | pass |
| Seed passwords come from `SEED_PASSWORD` or are generated, never hard-coded | pass |

## 5. Not done (state in the report)

- No pilot-restaurant UAT and no SUS scoring. The scripted UAT above was run by the builder through a browser, not
  by first-time users, so the NFR1 five-minute figure is **not measured**.
- Tested in Chromium only; Firefox and Edge were not run.
- No screen-reader accessibility audit, no load testing beyond section 2, no penetration test.
- The forecast accuracy figures are for synthetic data (see `ML_EVALUATION.md`).
- Feature ablation (ML_PLAN stretch): done 4 Oct 2026, see section 11 and `ML_EVALUATION.md` section 5.

## 6. Defects found and fixed during testing

| # | Finding | Fix |
|---|---|---|
| 1 | `trigger` is a reserved word in MySQL/MariaDB; the migration failed | renamed the column `trigger_type` |
| 2 | MariaDB reports CHECK violations as OperationalError (4025), not IntegrityError | tests accept any DBAPIError |
| 3 | MariaDB 11 snapshot isolation: locking reads can fail with 1020 under concurrent stock-outs | retry on a fresh snapshot (INV-3 passes) |
| 4 | Backfilled forecasts were made with the model refit on all history, so their accuracy was flattering (MAE 7.9 vs hold-out 9.4) | backfill uses the train-only copy; accuracy now 9.46, matching the hold-out; documented |
| 5 | Vue pages loaded without Chart.js | added to the base template; browser test asserts no console errors |
| 6 | Feature importance showed a single one-hot column (`item_7`, 91%) | item columns are reported together as "which item" |

## 7. Tier 1 of the proposal-completion work (21 Sep 2026)

Scope: `PLAN.md` section 3A, functions 1 to 6 (suppliers, stock adjustment, purchase orders, food availability, pre-orders,
admin inventory overview). Developed and tested on `smartrest_work` (a clone of the demo database) and `smartrest_test`;
the live demo database was not touched and needs no schema change for Tier 1.

| Check | Result |
|---|---|
| Automated suite without the perf tests (`pytest -q -m "not perf"`, includes the MariaDB tests) | 190 passed |
| New tests: `test_supplier_service`, `test_stock_adjustment`, `test_purchase_orders`, `test_pre_orders`, `tests/api/test_tier1_api.py` | pass |
| Hand-calculated cases: adjustment of 23 kg on hand to 20 / 12 / 30 kg (batch order and new batch); purchase order R1 and R3 (25 kg suggested, 10 kg on order gives 15, 25 kg on order gives none); pre-order 58 with forecast 40, buffer 10 %, batch 6 gives 60 (48 while pending or cancelled) | pass |
| Concurrency on MariaDB: two parallel receipts of 20 kg against a 25 kg order, exactly one succeeds | pass |
| RBAC: route x role matrix and new explicit tests (writes inventory-only or kitchen-only; admin read-only where stated; other roles 403 on every new page) | pass |
| Movement-sum invariant after adjustment, purchase-order receipt and partial receipt | holds |
| Browser check on the work copy (Chromium, three roles, 36 assertions incl. 360 px width) | pass; the only console errors are the deliberate 403/422 responses |

Defect found by the new tests and fixed: pre-order validation reported the "date in the past" error only after the other
field errors were cleared, so a request with several problems showed only some of them; the rule now joins the same pass.

Not yet done for Tier 1: the perf tests were not run (they write to the live demo database); the live server still runs the
previous code until the final deployment step.

## 8. Tier 2 of the proposal-completion work (21 Sep 2026)

Scope: `PLAN.md` section 3A functions 7 to 10, 14 and 15: kitchen stock requests (both roles), inventory data check,
admin demand-forecast monitoring, admin inventory reports and CSV, shortage reporting, restaurant information.
Migration `b8b8048fad45` (two tables) was applied to `smartrest_work` only; the live database is still at the previous
revision.

| Check | Result |
|---|---|
| Automated suite without the perf tests (`pytest -q -m "not perf"`, includes MariaDB tests) | 221 passed |
| New tests: `test_stock_requests`, `test_shortage_reports`, `test_inventory_reports`, `tests/api/test_tier2_api.py`; `test_migrations` now covers the new tables | pass |
| Hand-calculated cases: issuing 12 kg from usable 17 kg takes B2 4, B1 3, B3 5 and never the expired batch; issuing 20 kg is refused and writes nothing (all-or-nothing across lines); inventory trend closings 0, 10, 12, 10, 11, 11 ending at the on-hand stock; consistency check detects +8 kg added behind the movements | pass |
| Concurrency on MariaDB: two parallel issues of 10 kg against 12 kg usable, exactly one succeeds | pass |
| RBAC: kitchen creates and cancels requests only; inventory decides and issues but cannot create; admin is read-only on requests and holds the report and restaurant endpoints; all new pages 403 for other roles | pass |
| CSV equals the screen (trend closing figure, movement filter, stock levels) | pass |
| Browser check on the work copy (Chromium, three roles, 39 assertions incl. 360 px width) | pass; only the deliberate 4xx responses appear in the console |
| `flask smartrest check-stock` on the work copy | consistent, one expired batch listed |

Defects found by the new tests and fixed: the trend report answered 404 instead of 422 when no ingredient was chosen; two of
my own hand calculations were wrong (the code was right).

Not done: perf tests (they write to the live database); live deployment.

## 9. Tier 3 of the proposal-completion work (21 Sep 2026)

Scope: `PLAN.md` section 3A functions 11 to 13: daily orders, ingredient usage, admin analytics. Migration `165b04a3da7c`
(tables `orders` and `ingredient_usage`) was applied to `smartrest_work` only; the live database is still at the
first revision.

| Check | Result |
|---|---|
| Automated suite without the perf tests (`pytest -q -m "not perf"`, includes MariaDB tests) | 241 passed |
| New tests: `test_orders_and_usage`, `test_analytics`, additions to `tests/api/test_tier2_api.py` | pass |
| Hand-calculated cases: 54 burgers and 30 fried chicken give expected usage bun 54, lettuce 0.81, chicken 15.48, oil 1.5 (burgers prepared in two entries of 24 and 30 are summed); a recorded 16 kg gives variance +0.52; analytics on a five-day dataset gives weekday averages Monday 110, Saturday 190, ordinary days 123.3, promotion days 180 against 127.5, forecast error 5.0 MAE and 10 % WAPE, waste rate 10 % | pass |
| Ingredient usage never changes stock or creates a movement; orders never change the prep quantity | pass |
| RBAC: kitchen writes orders and usage; admin reads them; inventory gets 403; analytics is admin only; new pages 403 for other roles | pass |
| Browser check on the work copy (Chromium, three roles, 30 assertions incl. 360 px width) | pass |

Defects found and fixed: a shared chart component ignored a bare `all-labels` attribute (it arrives as an empty string), so
every other bar label was hidden on the new analytics chart and on the existing kitchen dashboard chart; the daily-orders
page overflowed a 360 px screen by 5 px because of a hidden helper span (removed). Two of my own test expectations
were wrong (the code was right).

Not done: perf tests (they write to the live database); live deployment.

## 10. Deployment of the proposal-completion work to the demo database (21 Sep 2026)

| Step | Result |
|---|---|
| Backup before the change (`backups/smartrest_live_before_deploy_*.sql`, git-ignored) | taken |
| `flask db upgrade` on the demo database | `2f76e5862108` to `165b04a3da7c`; four new tables (`stock_requests`, `stock_request_lines`, `orders`, `ingredient_usage`); existing rows unchanged (3 users, 7,500 sales records) |
| Server reload (gunicorn HUP, port 39500) | new workers booted; every new page redirects to login and every new API answers 401 (not 404) |
| Forecast for the current business date (22 Sep in Asia/Colombo) | run 71, status ok, 10 of 10 items |
| Alert evaluation | 13 open (admin 4 critical and 9 warning; kitchen 2 and 2; inventory 4 and 7) |
| `flask smartrest check-stock` | consistent; one expired batch listed |
| Read-only smoke check, all parameter-free GET routes as each role (injected sessions, no logins) | 62 routes: anonymous refused everywhere; admin 47 allowed and 15 forbidden; kitchen 21 and 41; inventory 24 and 38; no foreign navigation links; slowest request 227 ms |

The perf tests were not run: they write to the demo database and log in with a password that no longer matches the demo users.
The working copy `smartrest_work` (a clone taken before the changes) is kept for further testing and can be dropped.

## 11. Cross-validation, feature ablation and holiday calendar (4 Oct 2026)

Scope: `flask smartrest evaluate` (`app/ml/experiments.py`, `ForecastingService.run_experiments`), read-only; and the
corrected holiday calendar (`scripts/make_holidays.py`, `data/holidays_lk.csv`).

| Check | Result |
|---|---|
| Fast suite (`pytest -q -m "not mysql and not perf"`) | 238 passed (231 before plus 7 new in `tests/unit/test_ml_experiments.py`) |
| Hand-calculated cases: two 7-day windows ending 31 Mar 2026 are 18-24 and 25-31 Mar; feature sets listed by hand; segment rows 4 holiday, 3 promotion and 4 wet item-days | pass |
| No leakage: every window's last training day is before its first test day; windows contiguous; training window grows by exactly one window | pass |
| The ablation's full feature set reproduces the shipped training's XGBoost hold-out metrics exactly (unit test, and on the demo data: MAE 9.1973 both) | pass |
| `evaluate` changes nothing in the database (model and forecast-run counts before and after) | pass |
| Holiday file against the declared 2024-2026 calendars | 19 Poya dates were one day late and 5 holidays missing; corrected, demo rebuilt with `demo-reset` after a backup |

Results are in `ML_EVALUATION.md` sections 4 to 7. The MariaDB and perf tests were not re-run (unchanged code paths;
the perf tests write to the demo database).

## 12. Usability test kit (4 Oct 2026)

`docs/usability/` holds the plan, the printable kit (`.md` and `.docx`), CSV templates, the answer-key script
(`scripts/usability_answers.py`, read-only) and the analysis script (`scripts/usability_report.py`).

| Check | Result |
|---|---|
| `tests/unit/test_usability_report.py` (SUS scoring, time parsing, NFR1 per participant, data checks; hand-calculated) | 11 passed |
| Answer-key script changes nothing in the database (counts before and after) | pass |
| Pilot of every data-changing task through the services on the demo data, against the answer key | all pass; demo reset afterwards (backup `backups/smartrest_before_usability_pilot_20261004_140645`) |
| Kit `.docx` against the OOXML schema | pass |

Pilot findings added to the answer key: after the chicken delivery an alert for a later day can remain (correct); a
waste alert about Chicken Kottu could be mistaken for the chicken stock alert. No sessions with participants yet.

## 13. Input limits after the security and QA audit (4 Oct 2026)

The audit found that unbounded numbers distorted the plan (one 1,000,000,000-portion pre-order became a reorder of
999,999,999,100 burger buns), that `days` and `horizon_days` had no upper bound (a 100,000-day request held a worker
for minutes and wrote forecasts up to the year 2300), and that wrongly typed fields gave 500s. Fixes: limits and
decimal places in `services/validation.py` (API.md section 1), a plausibility check on the sales import, bounded
`days`, `horizon_days` and `limit`, and type checks on users, menu `is_active` and the settings `alerts` object.

| Check | Result |
|---|---|
| Fast suite (`pytest -q -m "not mysql" --ignore=tests/perf`, scratch clone) | 290 passed (249 before plus 41 new in `tests/api/test_input_limits.py`, VAL-7 to VAL-9) |
| `demo-reset` on an SQLite copy: the synthetic history still imports through the new outlier check | 7,630 rows, 0 rejected; same model and forecast as before |
| Browser smoke test, all roles and 360/768/1280 px, on that copy | no problems |
| Perf tests on that copy | forecast run 221 ms, worst request 117 ms |
| The audit's probes re-run | every input-limit, range and type case now 422; remaining findings (session revocation, security headers, lockout, password policy, CSV formulas) are not part of this change |

The MariaDB tests were not run, and the demo server was not restarted, so the live demo still runs the earlier code.

## 14. Security hardening after the audit (4 Oct 2026)

Fixes 4 to 9 of the audit: sessions end on the server (`users.session_version`, migration `4c1e5e7a9b2d`), security
headers with a CSP (the login page's inline script moved to `static/js/login.js`), CSV formula neutralising, a 5 MB
upload cap, a password rule, lockout per username and address (with `TRUST_PROXY` for a reverse proxy), and the perf
tests no longer run as part of `-m "not mysql"`.

| Check | Result |
|---|---|
| Fast suite (`pytest -q -m "not mysql"`, scratch clone) | 305 passed, 2 skipped (the perf tests, now opt-in); 15 new in `tests/api/test_security_hardening.py` (SEC-13 to SEC-18) |
| MariaDB tests (`pytest -q -m mysql` against `smartrest_test`) | 10 passed |
| Migration chain on MariaDB 11.8 (`smartrest_test`): upgrade from empty, downgrade and upgrade of `4c1e5e7a9b2d` | pass; `session_version INTEGER NOT NULL DEFAULT 0`; test database emptied afterwards |
| `demo-reset` on an SQLite copy, then the browser smoke test (Chromium, all roles, 360/768/1280 px) with the CSP active | no problems, no CSP violations; password show/hide still works |
| Firefox 155 and WebKit 26.6 (system libraries added with `playwright install-deps`: 219 new packages, nothing upgraded or removed) | browser smoke test, all roles and 360/768/1280 px: no problems in either (each on a freshly reset copy; the test saves an import row, so a second run on the same data finds it unchanged) |
| Perf tests on that copy (`-m perf`) | forecast run 286 ms, worst request 144 ms |
| The audit's probes re-run | sessions, headers, CSV, password rule now pass; left: `Secure` cookie (needs HTTPS), the expired-batch warning and `X-Request-ID` (not in this change) |

### Deployment to the demo database (4 Oct 2026)

| Step | Result |
|---|---|
| Backup (`backups/smartrest_before_hardening_20261004_173251/`: database dump, `instance/models`, `.env`, SHA256SUMS; git-ignored) | taken; restored into a temporary database with identical row counts in every table, then dropped |
| `flask db upgrade` | `165b04a3da7c` to `4c1e5e7a9b2d`; `session_version` 0 for the 3 users; no other row changed (7,630 sales, 630 forecasts, 22 batches and movements) |
| Server reload (gunicorn HUP, port 39500) | new workers booted, no errors; every earlier session ended once (new session id format) |
| Read-only check over HTTP, all 62 parameter-free GET routes as each role (signed session cookies, no logins) | anonymous refused; admin 47 allowed and 15 forbidden, kitchen 21 and 41, inventory 24 and 38 (as on 21 Sep); no foreign navigation links; security headers present; slowest request 454 ms |
| Writes that must be refused | a 1,000,000,000-portion pre-order and `horizon_days` "abc" give 422; nothing stored; an old-format session id gives 401 |
| `flask smartrest check-stock` | consistent; one expired batch listed (as before) |

Rollback: restore the dump (`DEMO_NEW_FEATURES.md` step 1) and check out the code before `0d94944`.

## 15. Deployment review fixes: bounded forecast range, unprivileged service, HTTPS (7 Oct 2026)

A second review on 7 Oct 2026 also examined the deployment and rated three issues high: the demo ran over plain HTTP
on public port 39500, gunicorn and the private MariaDB ran as root on a server shared with other websites, and
`GET /api/v1/forecasts` accepted any date range (year 1 to 9999 built about 3.6 million dates, a 51 MB response and
about 400 MB of memory for one logged-in request). Fixes: a 62-day limit in `forecasting_service.get_forecasts`
(commit `4630447`, API.md section 1), the app moved to `/srv/smartrest` and run as the system user `smartrest` under
systemd (`af6c2f5`, `deploy/systemd/`), and HTTPS through the aaPanel nginx at `smartrest.developerstudio.space`
(`ab39bf6`, `deploy/nginx/`). A leftover audit server on 127.0.0.1:39600 was stopped and its `smartrest_audit`
database dropped after a dump.

| Check | Result |
|---|---|
| Fast suite (`pytest -q -m "not mysql"`, scratch copy) | 320 passed, 2 skipped (perf); 15 new cases in `tests/api/test_input_limits.py` (7, 62 and 63 days, year 1 to 9999, end before start, for each role) |
| Full suite without perf, with coverage (`pytest --cov=app/services --cov=app/ml`, `TEST_DATABASE_URL` = `smartrest_test`, scratch copy without `.env`) | 330 passed (320 fast + 10 MariaDB), 2 skipped; services and ML coverage 95%; checksums of every table in the live `smartrest` database identical before and after |
| Fast suite as the `smartrest` user with the `/srv/smartrest/.venv` | 320 passed |
| Live forecast range | 7 days: 200; year 1 to 9999: 422 in 5 ms (135 bytes); end before start: 422 |
| Sandbox of the services (`ProtectHome`, `ProtectSystem=strict`, `PrivateTmp`, `NoNewPrivileges`) | active model loads; `instance/` writable; `app/` read-only; `/root` not readable; no SmartRestaurant process runs as root |
| HTTPS | Let's Encrypt certificate (certbot 4.0.0, webroot, valid to 5 Jan 2027, renewal dry run passes); TLS 1.3 verifies; HTTP gives 301 to HTTPS with path and query kept; HSTS on this host only |
| App behind the proxy (`APP_ENV=prod`, `TRUST_PROXY=1` in the unit; `.env` keeps `dev` for `demo-reset`) | session cookie `Secure; HttpOnly; SameSite=Lax`; a form post without or with a foreign `Referer` gives 400; login attempts record the client address, not 127.0.0.1 |
| Scripted HTTP check over HTTPS, each role (login, home page, role APIs, refused routes, logout, then 401) | all pass |
| Read-only browser pass over HTTPS (Chromium, 1280 and 360 px): every menu page of each role, 23 per width | no console errors, no failed requests; login and logout work |
| Other sites on the server (6 host names, HTTP and HTTPS status and certificate) | identical before and after every nginx reload |

### Deployment to the demo server (7 Oct 2026)

| Step | Result |
|---|---|
| Backup (`/root/smartrest/backups/smartrest_before_sectionA_20261007_120500/`: dumps of `smartrest` and `smartrest_audit`, `instance/models`, `.env`, git bundle, patch of the uncommitted work, a second dump of `smartrest` and `smartrest_test` at the switch, SHA256SUMS) | taken; HEAD plus the patch reproduced the working tree exactly |
| Move to `/srv/smartrest` | copy while running; clean MariaDB shutdown; datadir copied (identical); both services started as `smartrest`; downtime 12:15:29 to 12:16:42 |
| Data | `model_versions.artifact_path` changed from `/root/smartrest/...` to `/srv/smartrest/...` (1 row); 7,630 sales and 630 forecasts unchanged |
| nginx (backup `/root/smartrest/backups/nginx_before_smartrest_https_20261007_150002/`) | one new site file; `nginx -t` before each of the 3 graceful reloads; `proxy_cache off` and `proxy_next_upstream off` for this site, because `proxy.conf` enables both globally |
| Port 39500 | gunicorn bound to 127.0.0.1; both ufw rules for 39500 deleted; other ufw rules unchanged |

Not run: the perf tests (they write to the demo database), and the Playwright UAT script `tests/ui/smoke.py` (it writes
data; the read-only browser pass above was used instead). Firefox and WebKit were not re-run.

Rollback: `systemctl stop smartrest-web smartrest-db`, then start the stale copy in `/root/smartrest` with its old
scripts (see `MOVED_TO_SRV.txt` there); for nginx, remove the new site file, restore the backup and reload after `nginx -t`.

## 16. Demonstration safeguards and supplementary evaluation (7 Oct 2026)

The remaining review items that need no new data or decision. Backup before any change:
`/root/smartrest/backups/smartrest_before_sectionBC_20261007_174608/` (database dump, `.env`, `instance/models`,
SHA256SUMS). The comment-only edits left uncommitted on 4 Oct were reverted to the committed files (50 files, code
unchanged), and the report edits were committed (`9da3145`).

| Item | Change | Check |
|---|---|---|
| Forecast-vs-actual stays out-of-sample (`cf83ae7`) | backfill refused before the active model's hold-out (or, without a train-only copy, before the end of its training data); a non-backfill run cannot start on a past date | 3 new tests; live `POST /forecast-runs?as_of=2026-10-01` gives 422 and records no run (57 runs before and after) |
| Pages follow the server's business date (`5a90285`) | `<meta name="business-today">` in `base.html`; `ui.todayIso()` keeps the offset to the browser's date | 1 new test; offset logic checked in Node for no tag, real date and a fixed demo date; live page shows `2026-10-07` |
| Dead `v-if` on the prep page (`065f15f`) | removed; the input stays visible for every date, as before | browser pass |
| Administrator's own seed password (`2c9af85`) | `SEED_PASSWORD_<USERNAME>` overrides `SEED_PASSWORD`; the seed command never prints a password from the environment | 2 new tests; live admin password reset through `auth_service.reset_password` (audit `user.password_reset`, sessions ended) to `SEED_PASSWORD_ADMIN` in `.env`; the old shared password now gives 401 for `admin` |
| Training time in a web request | none needed | read-only timing on the demo data: 7.7 s (load 0.3 s) against gunicorn's 120 s and nginx's 130 s; hold-out MAE 9.20 reproduced |
| Items without a forecast (`79fa41d`) | ingredient forecast and reorder responses name the menu items with no forecast on some days; warnings on both inventory pages; quantities unchanged | 1 new test; live reorder meta lists all 10 items for 3 days (forecasts end on 10 Oct) |
| End of the holiday calendar (`71530c6`) | `GET /forecasts` reports `holiday_calendar_ends` and `beyond_holiday_calendar`; notice on the kitchen forecast page | 1 new test; live: calendar ends 2026-12-31, flag false for this week and true for 28 Dec to 3 Jan |
| Supplementary evaluation | `scripts/research_supplement.py` (read-only) and `docs/ML_EVALUATION_SUPPLEMENT.md` (not in the report) | live database checksums identical before and after; seed 42 reproduces the published figures; 3 unit tests for the Diebold-Mariano helper, one of which found that the first version divided the autocovariances by n - k instead of n (fixed, every figure regenerated) |

| Suite | Result |
|---|---|
| Fast and MariaDB tests (`pytest --cov=app/services --cov=app/ml`, `smartrest_test`, scratch copy without `.env`) | 341 passed (331 fast + 10 MariaDB), 2 skipped (perf); services and ML coverage 95%; live database checksums identical before and after |
| Scripted HTTP check over HTTPS, each role (admin with its own password) | all pass |
| Read-only browser pass over HTTPS (Chromium, 1280 and 360 px, 23 pages per width) | no console errors, no failed requests |

Not changed, for the team to decide: the fixed 10% safety buffer (the supplement shows the trade-off), the reorder
lead time capped at the 7-day horizon, stock that expires within the lead time counted as usable, and the
school-vacation dates. Not run: the perf tests and `tests/ui/smoke.py` (both write to the database).

## 17. Preparation workflow and Actual Food Usage (9 Oct 2026, feature branch `feature/m2-differences`, not deployed)

Built in an isolated clone (`/root/smartrest-feature`) after the proposal-versus-implementation audit, to close the two
partly implemented proposal functions: Food Preparation Management (K4) and Actual Food Usage Recording (K14).
Nothing was deployed; the live demo, its database and models were not changed.

| Check | Result |
|---|---|
| Fast suite (`pytest -q -m "not mysql"`, SQLite, no `.env`) | **357 passed** (331 before plus 26 new: `test_prep_workflow.py` 11, `test_food_usage.py` 13 executions, `test_prep_and_food_usage_api.py` 2), 2 skipped (perf); services and ML coverage 95% |
| MariaDB tests (`-m mysql`, database `smartrest_test`) | **12 passed** (10 before plus 2 new constraint tests) |
| Migration rehearsal on a copy of the live database (backup of 9 Oct 14:32 restored into a temporary `test_migr_*` database) | upgrade `4c1e5e7a9b2d` -> `7d3e9a1c5b20` -> `9b4f2c7e1d63`: new columns, table and three CHECK constraints present, row counts of all 30 existing tables unchanged; downgrade back to `4c1e5e7a9b2d`: columns and table gone, row counts unchanged; upgrade again: fine |
| Browser walkthrough on that copy (Playwright: Chromium, Firefox, WebKit) | accept, first prepared entry starts preparation, mark done with the below-plan warning, Done badge and Reopen; other food use recorded and shown in the daily balance; dashboard hint "x of y items done"; admin Monitoring > Waste shows other food use; no page-level sideways scroll at 1280 and 360 px; **no console errors** in any engine |

Defects found and fixed during the walkthrough: the Unaccounted column was cut off at 1280 px (the balance table now
has the full width) and Accept and Override still showed on a finished item (now hidden until it is reopened).

## 18. MySQL 8.4 instance, data copy and full test run (9 Oct 2026, branch `feature/mysql`, not deployed)

Production was not changed: it still runs on the private MariaDB 11.8 instance, which was not stopped or modified.
Procedure and rollback: `docs/RUNBOOK_MYSQL.md`.

| Step | Result |
|---|---|
| Install | MySQL Community Server **8.4.11 LTS**, official minimal tarball; MD5 and **GPG signature good** (MySQL Release Engineering, `BCA4 3417 … A8D3 785C`, key valid to 2027-10-23). In `/opt/mysql-8.4.11`; no apt package installed or removed; no missing libraries |
| Instance | user `smartmysql`, data `/srv/smartrest-mysql`, `--defaults-file` only, `127.0.0.1:3308` and a socket, X Protocol off, binary log off, `utf8mb4_unicode_ci`, UTC; unit `smartrest-mysql` running, **not enabled at boot**; about 330 MB RAM; nothing new listening on a public address |
| App login | PyMySQL over the Unix socket with `caching_sha2_password`, no new Python dependency |
| Backup first | `backups/before_mysql_20261009_170332/`: MariaDB dump, `instance/models`, `.env`, SHA256SUMS; dump restored into a temporary MariaDB database with row counts equal to live |
| Schema | built on MySQL by the project's own migrations (to `4c1e5e7a9b2d`); compared with MariaDB table by table: **identical** columns, types, nullability, 67 foreign keys, 44 CHECK constraints, unique keys and indexes (MariaDB's 6 automatic JSON checks become 6 native `JSON` columns) |
| Data copy | **24,440 rows in 6 s**, foreign-key checks on; **30 of 30 tables identical** by row count and content checksum; **0 orphan rows** for all 67 foreign keys; AUTO_INCREMENT above the highest id everywhere; `flask smartrest check-stock`: consistent; MySQL-native baseline dump saved |
| Same answers | 14 read services (sales and weekly sales, waste, forecast accuracy, forecasts, prep plan, requirements, ingredient forecast, reorder, analytics, daily summary, stock levels, data check, inventory trend) give **byte-identical results** on the MariaDB copy and the MySQL copy |
| Full test suite, production code on MySQL (`TEST_ALL_ON_DATABASE=1`) | `3da6ed4`: 341 passed, 0 failed in the first complete run, but one test failed intermittently in later runs (the defect below). **After the fix: MySQL 343 passed, 0 failed; the same suite on MariaDB 343 passed; SQLite 333 passed** (2 timing tests skipped and run separately); includes the constraint and concurrency tests |
| Demonstration pipeline on MySQL | `flask db upgrade` + `flask smartrest demo-reset` on a separate MySQL database: 7,680 synthetic sales imported, XGBoost trained (beats the baseline), 56-day backfill all ok, 7-day forecast for 10 of 10 items, alerts evaluated |
| Browser walkthrough (`tests/ui/smoke.py`, fresh reset before each engine) | Chromium, Firefox and WebKit: kitchen, inventory, admin and responsive checks all ok (one WebKit run reported a request cancelled during navigation; two repeat runs were clean) |
| Timing (same seeded data on a MariaDB and a MySQL test database) | full pipeline 24.0 s vs 25.1 s; PERF-1 forecast run 269 ms vs 256 ms; PERF-2 worst request 220 ms vs 267 ms (targets 5 s and 3 s) |
| Feature branch (K4, K14) on MySQL | migrations `7d3e9a1c5b20` and `9b4f2c7e1d63` up, down and up again on a copy of the MySQL data: row counts unchanged; full suite with the restock fix: **377 passed, 0 failed** (before the fix one run had the intermittent failure below) |

Defect found in the test harness, not the application: every test builds a new app and connection pool that was
never closed, so a full run on a database server hit `max_connections` (40, the same on the MariaDB instance) and
also spent about 8 s per test dropping and recreating 30 tables on MySQL. Fixed in `tests/conftest.py`: the pool is
disposed after each test, and on a server the schema is built once per session and tables are truncated between
tests (a full run takes 7 minutes instead of about 70).

Defect found in the application by running everything on a database server: a manual shortage report (K12) closes
when the ingredient is "restocked since the report", which compared `stock_movements.created_at > alert.created_at`.
MySQL and MariaDB store `DATETIME` in whole seconds (MySQL rounds, MariaDB truncates), so a report and a stock-in in the
same second carried the same timestamp: the restock was missed (with `>`), and with `>=` older stock in that second
would count. SQLite keeps microseconds, which is why the fast suite never showed it; on MySQL the test failed in
about two runs out of three. Fixed by comparing **movement ids** instead of times: the report stores the highest
stock-movement id for that ingredient in its `details` (`last_movement_id`, kept on a repeat report), and a restock is
a positive movement with a higher id; alerts created before the fix fall back to the time comparison. Two new tests
force equal timestamps in both directions (both fail on the old code). No schema change.

## 19. Merged pages: 23 menu pages to 14 (14 Oct 2026, branch `nav-consolidation` on `system-integration`, staging only, not deployed)

| Check | Result |
|---|---|
| Backup first | `/root/smartrest/backups/before_nav_consolidation_*`: bundle of every branch, worktree files, HEAD `a8cb275` |
| Fast suite (`pytest -m "not mysql"`) | **420 passed**, 2 skipped (395 before; new `tests/api/test_navigation.py`; four older page tests now open the tab address instead of the old page) |
| RBAC and architecture tests | green; every redirecting old address is still refused (403) to the other roles |
| Role access table | every row compared with a real request per role: 200 exactly where the table shows a tick, 403 elsewhere |
| Browser walkthrough (`tests/ui/smoke.py`, fresh copy of the staging demo database per engine, temporary server on 127.0.0.1) | Chromium and Firefox: kitchen, inventory, admin and responsive (360, 768, 1280 px, every page and tab) all ok. WebKit: first run reported two requests cancelled while leaving Served & waste (an unchanged page; seen before), the repeat run was clean |
| Found and fixed during the walkthrough | the Role access table scrolled the whole page sideways at 360 px (the screen-reader labels were positioned outside the scrolling table); fixed in CSS |

The walkthrough's old "Chicken is short today" check depended on the demo date; it now follows a shortage link when
one exists and otherwise opens the same pre-filled Stock requests address directly.

## 20. Final UI pass (14 Oct 2026, branch `ui-final` on `nav-consolidation`, staging only, not deployed)

| Check | Result |
|---|---|
| Backup first | `/root/smartrest/backups/before_ui_final_20261014_112309/`: bundle of every branch (restored by a test clone to `3d37cd9`), worktree files, staging demo database, SHA256SUMS |
| Scope | templates, page scripts, CSS, menu labels, a default tab; `git diff nav-consolidation` of `app/services`, `app/ml`, `app/models`, `app/controllers`, `migrations`, `app/seed`, config: **empty** |
| Same results as before | base build `a8cb275` (system-integration) and this build, two copies of the same demo database, the same fixed date: **42 of 42 GET endpoints give identical JSON** (dashboards for all roles, every report, forecasts, accuracy, prep plan, requirements, reorder, ingredient forecast, model versions, stock levels and batches, stock check, pre-orders, purchase orders, settings; only timestamps ignored); responses checked to contain real data |
| Fast suite | **423 passed**, 2 skipped (3 new tests: Forecasting tabs and default, Reports title and dashboard labels, Role access phone list) |
| Browser walkthrough (fresh copy of the staging demo database per engine) | Chromium and Firefox: kitchen, inventory, admin and responsive (360, 768, 1280 px; every menu page, tab and Reports group) all ok, including the new desktop prep table, recipe panel, Reports groups and Forecasting tabs. WebKit: every section passed in at least one run; failures moved between runs (login redirected back to the login page, requests cancelled while leaving a page), the same intermittent WebKit behaviour recorded in sections 18 and 19 |
| Found and fixed | dashboard template briefly held the old body twice (edit anchored on the wrong `endblock`), caught before testing; prep table and recipe actions cut off at 1366 px (layout changed); a test-harness port clash (review server and walkthrough server both on 39531) that made Firefox and WebKit see data saved by the Chromium run |
| Not run | MySQL-marked tests (no `TEST_DATABASE_URL` on staging; no database code changed); production checks (nothing deployed) |

## 21. Release check (14 Oct 2026, branch `release-check` on `ui-final`, staging and isolated copies only, not deployed)

| Check | Result |
|---|---|
| Backups | staging repository `/root/smartrest/backups/before_release_check_20261014_123349` (bundle verified by a clone); production database, read-only dump `predeploy_release_20261014_124326` (32 tables, 24,590 rows) |
| End-to-end chain on controlled data (new E2E-1) | **pass** on SQLite and on MySQL 8.4: every hand-calculated value matched (accuracy MAE 3.5 / WAPE 8.75 % / MAPE 8.33 % / bias -3.5; missing forecast day named; burger plan 60 = max(52.03, 58) up to batch, not 108; requirements 19.2 kg with the expired batch excluded; FEFO issue; wastage; waste 11 portions = 8,850 LKR; dashboard 220 portions, 170,200 LKR, waste rate 11.0 %, forecast 553.8 with one null day; ingredient demand 99.6 kg; reorder 40 kg and 100 buns; purchase order received; stock consistent) |
| Fast suite (SQLite) | **424 passed**, 2 skipped (timing tests) |
| MySQL 8.4, isolated server (127.0.0.1:3310, own data folder, never the production server) | `-m mysql`: **14 passed**; whole suite on MySQL (`TEST_ALL_ON_DATABASE=1`): **437 passed**, 2 skipped; E2E-1 plus navigation and RBAC on MySQL: **34 passed** |
| Browsers (fresh copy of the staging demo database per run, gunicorn `--timeout 120` as in production) | Chromium **pass**, Firefox **pass**, WebKit **pass in 5 consecutive runs**: kitchen, inventory (now with phone checks of the Purchasing cards), admin, responsive (360 / 768 / 1280 px, every page and tab) |
| WebKit cause found | the walkthrough waited for the next page's full `load` event within 15 s after logging in; under load WebKit sometimes took longer although the login had worked. It now waits for the navigation itself (`wait_until="commit"`). WebKit also reports fetches it cancels when a page is left as "access control checks" errors; the page code catches them, so the walkthrough ignores that message only. A failed login now records the URL, the last responses and a screenshot |
| Test-harness defects found | the walkthrough's temporary server used gunicorn's 30 s default, so model training under browser load was killed once (production uses 120 s); fixed in the harness |
| Missing 7th forecast day | **not a code defect**: no forecast had run on the day. One `forecast-daily` run made 7 days x 10 items; the second answered `already_done`, no duplicates (staging copy and production copy) |
| Production deployment rehearsal (copy of the production dump in the isolated server) | upgrade `9b4f2c7e1d63 -> c4e1a7b9d052` in 3.3 s; all 30 other tables identical to production by `CHECKSUM TABLE`; daily forecast 70 rows; release walkthrough on production data (Chromium) pass; CSV downloads (7) all 200 with data |
| Rollback rehearsal | A, code only: production code `56d439f` on the upgraded schema, 23 pages and 12 API calls all 200. B, schema downgrade: back to `9b4f2c7e1d63`, completed pre-orders confirmed, the 4 columns removed, other tables identical to production |
| Not tested | logged-in pages on the live site (owner's passwords); the real systemd timer on production (rehearsed with the same command) |

## 22. Viva polish: the six-step workflow on every dashboard (14 Oct 2026, branch `viva-polish` on `release-check`, staging only, not deployed)

| Check | Result |
|---|---|
| Backup first | `/root/smartrest/backups/before_viva_polish_20261014_135323` (bundle, restored by a test clone to `9bb8c73`) |
| Scope | templates, page scripts, `components.js`, CSS, `utils/navigation.py` (step map), the template context (one more helper); no service, ML, model, API, migration or permission change |
| Fast suite | **432 passed**, 2 skipped (8 new: step marker on six pages, none on dashboards and reports, step map matches the menus) |
| Browsers (fresh copy of the staging demo database per run, gunicorn `--timeout 120`) | Chromium **pass**, Firefox **pass**, WebKit **pass in 3 consecutive full runs**; the walkthrough now checks the 6-step strip on each dashboard, its links (5 of 6 for the administrator) and the figure read from the prep plan |
| Harness races fixed | the override check waited for a label that is always shown, then read the field error before the server answered (now waits for the error); headless WebKit sometimes drops the login click without sending the form (seen twice in 3 runs; the walkthrough now reloads and tries once more, and prints that it did) |
| Screens | 41 pages, no page scrolls sideways at 1366 or 390 px: `SmartRestaurant_Viva_Polish_Screens.pdf` |

## 23. Minimal pass: less wording, compact workflow (14 Oct 2026, branch `ui-minimal` on `viva-polish`, staging only, not deployed)

| Check | Result |
|---|---|
| Scope | templates, page scripts (labels and captions only), `components.js` (workflow strip markup), CSS; no service, ML, model, API, migration, permission or navigation change |
| Fast suite | **432 passed**, 16 skipped (14 MySQL-only, 2 timing); one label assertion updated (quick actions no longer have sub-text) |
| Browsers (fresh copy of the staging demo database per run) | Firefox **pass**, WebKit **pass** (kitchen, inventory, admin, responsive 360 / 768 / 1280 px); Chromium kitchen, admin, responsive **pass**, inventory **not completed** |
| Chromium on this VPS | headless Chromium 153 aborted (`trap int3` in the kernel log) after about seven logged-in page loads, also with the previous commit `c3627b2`. **Cause found later (section 24): `/tmp` (a 1.9 GB tmpfs) was full**, and Playwright starts Chromium with `--disable-dev-shm-usage`, so its shared memory lives in `/tmp`. Not an application defect; the memory-pressure explanation first given here was wrong |
| Screens | 41 pages plus 3 before/after dashboard pages, no page scrolls sideways at 1366 or 390 px: `SmartRestaurant_Minimal_UI_Screens.pdf` |

## 24. Role dashboards (14 Oct 2026, branch `role-dashboards` on `ui-minimal` = production `d26b1e9`, staging only, not deployed)

| Check | Result |
|---|---|
| Preservation audit | `scripts/preservation_audit.py` read the production code into `tests/preservation_baseline.json` before any change: 122 route methods with their roles, 14 menu pages and 16 tabs, 10 reports, 9 redirects, 11 CLI commands, 24 page views with 125 actions and 117 API calls. `docs/PRESERVATION_CHECKLIST.md` explains every item |
| Preservation test (new PRES-1..PRES-5, 41 tests) | **pass**: every route with the same roles, the same menu and tabs, every report, redirect and CLI command, every action and API call on every page (2 dashboard data calls moved to the dashboard endpoint, each still used by the page behind it), each role opens all its views and none of another role's |
| Dashboard figures on controlled data (new RD-1..RD-4, 7 tests) | **pass**, values worked out by hand: accuracy MAE 6.667 / WAPE 22.22 % / bias +3.33 on 3 pairs (a forecast made after the day ignored); kitchen forecast 15.0, to prepare 17 (12 + 5), 6 prepared, served "not recorded" (never 0), 1 wasted, pre-orders 1 pending / 3 confirmed portions; inventory reorder count not capped at the 5 shown, bun need 26 = 12 + 14 vs 15 usable -> 1 at risk, expired 1 / expiring 1 (a used-up expired batch not counted), requests 2 waiting / 1 approved, purchase orders 1 draft / 2 awaiting; dashboards write no records except the alert check |
| Fast suite (SQLite) | **480 passed**, 16 skipped (14 MySQL-only, 2 timing) |
| MySQL 8.4 (isolated server, port 3310) | role dashboards, admin dashboard, E2E-1 and preservation tests: **62 passed** |
| Browsers (fresh copy of the staging demo database per run) | Firefox **pass**, WebKit **pass**, Chromium **pass** (kitchen, inventory, admin, responsive 360 / 768 / 1280 px); the walkthrough now checks each role's figures, Needs attention and, for the administrator, Forecasting performance |
| Environment defect found | `/tmp` (tmpfs, 1.9 GB) was full: 1.3 GB of assistant session scratch and 413 MB of pytest temp folders. It caused the Chromium crashes of section 23 and, this time, 22 unit-test errors (OSError). The pytest folders of this work were removed; tests and browsers now keep temporary files under `instance/tmp_tests` on the main disk. Production does not use `/tmp` for data (MySQL under `/srv`) |
| Consistency across roles (demo data, 14 Oct) | the same figures on all three dashboards: 5 out of stock and 1 low, 6 ingredients short in 7 days, 7 expired batches, 604 portions to prepare, 511 forecast |
| Screens | 41 pages plus 6 before/after dashboard pages (desktop and phone), no page scrolls sideways: `SmartRestaurant_Role_Dashboards_Screens.pdf` |

## 25. Simplification (14 Oct 2026, branch `simplify` on `role-dashboards`, staging only, not deployed)

| Check | Result |
|---|---|
| Scope | approved M1, M2 (approve and issue stay separate operations), M3, M4, M5, M6, M7, M8, R1, R2; templates, page scripts, CSS, navigation (one tab moved, one label), two unread dashboard fields; no service rule, ML, model, migration, route or permission change |
| Preservation test | **pass**: every baseline route with the same roles; menus equal to the baseline apart from the approved M7 tab and M8 label; the 10 baseline reports reachable (8 reports, the merged keys open them); every baseline action and API call present or listed as an approved change with the place it moved to (`tests/api/test_preservation.py`, `docs/PRESERVATION_CHECKLIST.md` section 7) |
| Fast suite (SQLite) | **479 passed**, 16 skipped (step-marker tests replaced by a no-marker test, R1) |
| MySQL 8.4 (isolated, port 3310) | role dashboards, admin dashboard, E2E-1, prep workflow, preservation, navigation, RBAC: **113 passed** |
| Browsers | Chromium, Firefox, WebKit **pass**; the walkthrough now uses Ask inventory, sends a kitchen request, checks that inventory sees only Approve first and Issue to kitchen after approval, records waste on End of day, opens Stock & expiry, Stock history and the old `?tab=movements` address, and Role access under Users |
| Found and fixed | the Ask inventory button on red (short) rows had unreadable text; on phones its panel sat inside the sideways-scrolling table (now pinned to the visible width); Forecast generation could read an empty model list when a page was left mid-load (WebKit console error, an older race; guarded) |
| Test environment | Chromium failed once more because its temporary directory under `instance/tmp_tests` had been handed to another user; Chromium's processes drop the right to bypass file permissions. The directory is root's again |
| Screens | 41 pages plus 5 before/after pairs: `SmartRestaurant_Simplify_Screens.pdf` |

## 26. Final checks (15 Oct 2026, branch `final-checks` on `simplify`, staging only, not deployed)

| Issue | Verified | Fix |
|---|---|---|
| 1. Prep plan: Accept on an already accepted plan | **Confirmed**: an accepted item still showed "Accept 84" (table and phone cards); pressing it only wrote a second, identical acceptance to the audit log | Accept is shown only when it changes the plan: not yet decided ("Accept 84"), overridden ("Accept 84"), or accepted at a quantity the recommendation has since left ("Accept new 90", e.g. after a new pre-order). Override stays. Server unchanged |
| 2. End of day sequence | **Confirmed**: the three sections were numbered but nothing showed what was already recorded, and Daily balance, the last step, sat in another tab without a number | One step line "1 Served · 2 Food waste · 3 Other use · 4 Daily balance", ticked when the day has a record; each step jumps to its section or tab. No new explanatory text |
| 3. Requests with zero or too little usable stock | **Server correct** (no change): Approve moves no stock and is allowed without stock (stock may arrive before issuing); Issue checks usable, non-expired stock under a row lock and refuses the whole issue with "only X usable" if any line is short, writing nothing. **Screen confirmed**: with 0 usable the issue form opened empty and pressing Issue said "enter a quantity for at least one line", hiding the reason | A line with no usable stock shows "No usable stock" instead of a quantity box; when no line can be issued the form says "Nothing can be issued yet: receive stock first" and Issue is disabled. Partly covered lines are still filled with the usable quantity |

| Check | Result |
|---|---|
| New tests | approve with no usable stock moves nothing; issue with zero usable stock is refused (`insufficient_stock`, available 0), nothing written, request stays approved; expired-only stock counts as 0 usable and the request shows 0 |
| Fast suite (SQLite) | **483 passed**, 16 skipped |
| MySQL 8.4 (isolated) | stock requests, prep workflow, recommendations, role dashboards, E2E-1, preservation, RBAC: **104 passed** |
| Browsers | Chromium, Firefox, WebKit **pass**; the walkthrough now checks that an accepted card has no second Accept, that End of day ticks served and waste once recorded, and that Issue is disabled when nothing is usable |

## 27. MySQL 8.4 for staging and tests, fail-fast (16 Oct 2026, branch `mysql-failfast` on production `159d7aa`, staging only, not deployed)

Earlier entries are kept as written: the runs they record used MariaDB 11.8 for the server tests.

| Check | Result |
|---|---|
| Staging data moved to MySQL 8.4 (instance `smartrest-staging-mysql`, 127.0.0.1:3311) | staging 24,941 rows and worktree 24,819 rows compared value by value: no differences, no orphan foreign keys; `flask db check` clean on both |
| Production backup restore test | dump restored on the staging instance: 32/32 table checksums equal to production |
| Fail-fast (`app/utils/db_check.py`) | no SQLite fallback outside tests; MySQL required with `APP_ENV=prod` or `REQUIRE_MYSQL=1`; MariaDB and MySQL < 8.4 refused; access denied or unknown database refused; only an unreachable server (2002/2003/2006/2013) warns and starts. Checked by hand: SQLite, MariaDB 3307 and a missing URL are refused, staging passes (`flask smartrest db-info`) |
| New tests DB-1 .. DB-7 | 14 passed (incl. the server version, a wrong password and an unknown database on MySQL 8.4) |
| Fast suite (SQLite in memory) | **498 passed**, 2 skipped |
| Full suite on MySQL 8.4 (`TEST_ALL_ON_DATABASE=1`, `smartrest_test`) | **514 passed, 0 failed** (the MariaDB-only failure `test_two_runs_at_once...` passes on MySQL) |
| Browsers on a MySQL copy | Chromium, Firefox, WebKit: kitchen, inventory, admin, responsive **pass** |
| Functional checks on MySQL | 16/16: model and forecasts, prep formula and pre-order floor, BOM requirements, pre-order workflow, served and waste, ingredient usage, stock, dashboards, permissions; forecast run on MySQL wrote 70 rows |
| Live staging service on MySQL | kitchen 10/10, inventory 6/6, admin 7/7 pages and APIs; forecast timer runs on schedule, no errors |

