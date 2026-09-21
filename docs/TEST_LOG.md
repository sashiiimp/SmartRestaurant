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
- Feature ablation (ML_PLAN stretch) not run.

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
