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
