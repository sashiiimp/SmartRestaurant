# SmartRestaurant: Testing

Read `REQUIREMENTS.md` (acceptance criteria, NFR table), `ARCHITECTURE.md` (layers, D8) and `ML_PLAN.md` (Part B rules) first. Tier labels (M1, M2, S) are defined in the project plan.

## 1. Strategy

One builder and about a week. The approach is to **automate what is cheap and risky, script the rest by hand, and be honest about what was not done.**

| Priority | What | Why |
|---|---|---|
| 1 | Formula tests with hand-calculated expected values (section 4) | The forecast-to-decision logic is the project's value (FR5-FR7) and must be provably right |
| 2 | Route x role RBAC matrix (C2, NFR5) | A missing check is the most likely serious defect |
| 3 | Stock integrity (FEFO, never negative, movement sum) | Silent corruption if wrong (NFR8) |
| 4 | Leakage and fallback tests for the ML code | Guards the credibility of the accuracy claim |
| 5 | Import and validation negative tests (NFR3, NFR8) | Bad data distorts forecasts |
| 6 | Architecture import-rule test | Proves the MVC claim (ARCH section 1) |
| 7 | Scripted UAT per role, timing, responsive, security checklist | Covers NFR1, NFR2, NFR4 |

Not chasing coverage numbers for controllers and templates. **Target: at least 80% line coverage on `app/services` and `app/ml`.**

## 2. Environments and tools

| Item | Choice |
|---|---|
| Runner | `pytest`, `pytest-cov`. Flask test client for API and page tests. Browser walkthroughs with Playwright (`tests/ui/smoke.py`, added after this plan was first written) in Chromium, Firefox and WebKit. |
| Unit tests | SQLite in-memory (fast, isolated; the only place SQLite is used). Marker: none. |
| Integration and API tests | MySQL 8.4 database `smartrest_test` on the staging instance (127.0.0.1:3311; `TEST_DATABASE_URL` in `.env`; MariaDB was used before 16 Oct 2026). Marker `@pytest.mark.mysql`. With `TEST_ALL_ON_DATABASE=1` **every** test runs against `TEST_DATABASE_URL` instead of in-memory SQLite (added 9 Oct 2026 for the MySQL migration; each test's connection pool is closed afterwards so a full run stays under `max_connections`). Needed for `FOR UPDATE`, constraint behaviour, concurrency. |
| Clock | `SMARTREST_TODAY` env var overrides `utils.dates.today()` so tests and the demo are deterministic. Tests set it through a fixture. |
| Data | `tests/factories.py` builders (`make_user(role)`, `make_item(batch_size=...)`, `make_ingredient(...)`, `add_batch(...)`, `add_recipe(...)`, `add_sales(...)`). Formula tests build their own small fixtures; they never depend on the seed data. |
| Commands | `pytest -q -m "not mysql"` (fast, run constantly), `pytest -q` (everything), `pytest -q -m perf` (timing), `pytest --cov=app/services --cov=app/ml`. The perf tests are skipped unless `-m perf` is given, because they write a forecast run to the dev database. |

## 3. Layout

```
tests/
  test_architecture.py           # ARCH import rules
  unit/       test_prep_formula.py  test_requirements.py  test_reorder.py  test_alert_rules.py
              test_features.py  test_models_baseline.py  test_fifo.py  test_validation.py  test_import_parse.py
  integration/ test_stock_service.py  test_import_service.py  test_forecast_service.py  test_alert_service.py  test_concurrency.py
  api/        test_rbac.py  test_envelope.py  test_kitchen_api.py  test_inventory_api.py  test_admin_api.py
  perf/       test_timing.py
```

## 4. Worked examples (expected values are calculated by hand, never copied from the code's output)

### 4.1 Preparation quantity (B1, S2)

| # | Forecast | Buffer % | Confirmed pre-orders | Batch | Expected | Working |
|---|---|---|---|---|---|---|
| P1 | 47.3 | 10 | 0 | 6 | **54** | 52.03 / 6 = 8.67, up to 9, x6 |
| P2 | 47.3 | 10 | 58 | 6 | **60** | need = max(52.03, 58) = 58; 58 / 6 = 9.67, up to 10, x6 |
| P3 | 0 | 10 | 0 | 6 | **0** | need 0 |
| P4 | 0 | 10 | 5 | 6 | **6** | pre-orders lift the floor, then batch |
| P5 | 0.3 | 10 | 0 | 6 | **6** | 0.33 rounds up to one batch |
| P6 | 60.0 | 0 | 0 | 10 | **60** | exact multiple stays |
| P7 | 12.0 | 10 | 0 | 1 | **14** | 13.2 up to 14 |
| P8 | 45.45 | 10 | 0 | 5 | **50** | 49.995 / 5 = 9.999, up to 10 (Decimal must not lose this to float noise) |
| P9 | none | 10 | 0 | 6 | status `no_forecast`, no number | S5 |

Plus: accept stores `final_qty = recommended`; override without reason gives 422; override below pre-orders returns a warning; only `confirmed` pre-orders count; inactive items are excluded.

### 4.2 Ingredient requirements and shortage (B2, S3, K9)

Recipes: Chicken Burger uses Chicken 0.120 kg, Bun 1 pcs, Lettuce 0.015 kg. Fried Chicken 2 pc uses Chicken 0.300 kg, Oil 0.050 L. Iced Milo has **no recipe**.
Plan: Chicken Burger 54, Fried Chicken 30, Iced Milo 20.
Stock: Chicken batch A 12.0 kg (expires in 5 days) and batch B 5.0 kg (**expired yesterday**); Buns 60; Lettuce 0.5 kg; Oil 4.0 L.

| Ingredient | Required | Usable | Result | Working |
|---|---|---|---|---|
| Chicken | **15.48 kg** | 12.0 (on hand 17.0) | short by **3.48** | 54 x 0.12 + 30 x 0.30 = 6.48 + 9.00; expired batch excluded |
| Bun | 54 | 60 | sufficient | |
| Lettuce | **0.81 kg** | 0.5 | short by **0.31** | 54 x 0.015 |
| Oil | **1.5 L** | 4.0 | sufficient | 30 x 0.05 |
| cannot_compute | Iced Milo, reason `no_recipe` | | | listed, not ignored |

### 4.3 Days of cover, shortfall and reorder (B3)

Chicken: usable 12.0, `min_stock` 5.0, `reorder_level` 10.0, `pack_size` 5, supplier lead time 2 days. Daily need: day 1 = 15.48, day 2 = 14.02 (days 3-7 total 68.50, so the 7-day total is 98.00).

| # | Case | Expected |
|---|---|---|
| R1 | `need_L` = 15.48 + 14.02 = 29.50; raw = 29.50 + 5 - 12 - 0 = 22.5; pack 5; MOQ 10 | suggested **25** |
| R2 | as R1 with MOQ 30 | suggested **30** |
| R3 | as R1 with on_order 10 | raw 12.5, suggested **15** |
| R4 | `need_L` 4.0 (raw = 4 + 5 - 12 = -3) | no suggestion (never negative) |
| R5 | days of cover | avg daily need 98 / 7 = 14.0, cover 12 / 14 = **0.86 days** |
| R6 | first shortfall | day 1 (15.48 > 12) = **today**, so a `projected_stockout` alert, severity critical |

### 4.4 Alert conditions (B4), Chicken min 5, reorder level 10

| Usable | Expected open alerts |
|---|---|
| 12 (no shortfall in window) | none |
| 12 (with the daily needs above) | `projected_stockout` critical |
| 8 | `low_stock` warning |
| 4 | `critical_stock` critical (and no `low_stock`) |
| 4 then stock-in raises usable to 14 | `critical_stock` closes (`cleared`); no duplicate opens on repeated runs |

Waste risk: prepared 100 and waste 20 over 7 days gives 20% > 15%, so a warning; prepared 15 and waste 10 gives no alert (volume below 20).

### 4.5 FEFO and stock integrity (I6, I13)

Batches: B1 expires 10 Oct qty 3; B2 expires 5 Oct qty 4; B3 no expiry qty 10; B4 **expired** 20 Sep qty 6 (today 25 Sep).
- Stock-out 5 gives movements -4 (B2) and -1 (B1); B1 left 2; B3 and B4 untouched.
- Then stock-out 20 is rejected `insufficient_stock`, `available = 12` (B1 2 + B3 10; B4 is expired, excluded). No partial deduction.
- Wastage 6 (reason `expired`) from B4 succeeds; B4 remaining 0.
- After every operation: `SUM(movements.quantity) == SUM(batches.qty_remaining)` per ingredient.

## 5. Test catalogue

Tier column: which tier the test gates. M1 tests must pass before the demo.

### 5.1 Security and access (C1, C2, C4, NFR5)

| ID | Test | Tier |
|---|---|---|
| SEC-1 | RBAC matrix: iterate `app.url_map`; for each route x {anonymous, admin, kitchen, inventory} assert the status from the table in API.md (page 302 to login or 403; API 401 or 403). A route with no declared rule fails the test. | M1 |
| SEC-2 | Each role lands on its own home after login | M1 |
| SEC-3 | Wrong password and unknown user return the identical message and status | M1 |
| SEC-4 | Deactivated user cannot log in (same message) | M1 |
| SEC-5 | 5 failures within 10 minutes lock the username for 5 minutes from that address, including for an unknown username (see SEC-18) | M1 |
| SEC-6 | Stored hash is not the password; no password in logs or responses | M1 |
| SEC-7 | POST/PUT/PATCH without CSRF token gives 400 `csrf_failed` | M1 |
| SEC-8 | `<script>` in item name, note and customer note is stored and rendered escaped | M1 |
| SEC-9 | A quote or SQL fragment in filters and text fields causes no error and no injection (parameterised queries) | M1 |
| SEC-10 | Session expires after idle timeout (clock advanced), the next API call gives 401 | M2 |
| SEC-11 | Logout, then Back button, shows no protected content | M2 |
| SEC-12 | Last active admin cannot be deactivated or demoted | M2 |
| SEC-13 | Logout, password reset and deactivation end the session on the server: a copied cookie gives 401; old-format session ids are refused | audit |
| SEC-14 | Security headers on pages and API (CSP without inline script, frame-ancestors none, nosniff, referrer); no page has an inline script or event handler | audit |
| SEC-15 | CSV export: text starting with = + - @ gets a leading apostrophe; numbers, including negative ones, are unchanged | audit |
| SEC-16 | Upload over 5 MB gives 413 `too_large` | audit |
| SEC-17 | Password rule: username inside, one repeated character, letters only, under 8 or over 128 characters are refused with the reason, on create and reset | audit |
| SEC-18 | Lockout per username and address: failures from one address do not lock the user out from another; 20 failures from one address over many usernames lock that address; behind `TRUST_PROXY` the forwarded address counts | audit |

### 5.2 Validation and import (C4, A14, NFR3, NFR8)

| ID | Test | Tier |
|---|---|---|
| VAL-1 | Non-numeric, zero or negative quantity rejected on prepared, waste, stock-in/out (422 with field message) | M1 |
| VAL-2 | Sales quantity 0 accepted, negative rejected | M1 |
| VAL-3 | Future date rejected for actual records | M1 |
| VAL-4 | Duplicate served record for the same item and date gives 409 `duplicate_record`; resend with `confirm_overwrite` updates it | M1 |
| VAL-5 | Expiry before received date rejected; `reorder_level < min_stock` rejected | M1 |
| VAL-6 | Ingredient unit change rejected after first movement | M1 |
| VAL-7 | Upper limits (API.md section 1, input limits): 10,001 portions, a 1,000,000,000 pre-order, 10^15 stock, 0.0001 stock and 650.555 LKR are all 422; 400 = 10 x the stored maximum of 40 is accepted on import, 401 rejected; 4000 against a file median of 40 rejected | audit |
| VAL-8 | Bounded ranges: `ingredient-forecast` `days` 0, -5, 32, 100000 give 422 and 1, 31 give 200; `horizon_days` "abc", 0, -3, 15, 100000, true give 422 and no forecast run is recorded; an integer query parameter beyond 2^31-1 gives 422 | audit |
| VAL-9 | Type checks: users (name as object, username as list or with a space, password as a number, bad email, role as list, `is_active` "false"), menu `is_active` "no", settings `alerts` as a list give 422, never 500 | audit |
| IMP-1 | CSV with 2 bad rows: dry run reports N accepted, 2 rejected, row numbers and reasons; nothing saved | M1 |
| IMP-2 | Commit saves only valid rows; re-importing the same file creates no duplicates (`skipped_unchanged`) | M1 |
| IMP-3 | Unknown item name is reported and not created | M1 |
| IMP-4 | Differing existing row: `skip` reports conflict, `overwrite` updates | M1 |
| IMP-5 | Empty file, wrong header, wrong encoding give a readable error, never a 500 | M1 |

### 5.3 Recommendation, stock and alerts

| ID | Test | Tier |
|---|---|---|
| REC-1 | All rows of table 4.1 (parametrised) | M1 |
| REC-2 | Accept and override persist the right fields; second decision updates the same row and writes audit | M1 |
| REQ-1 | Table 4.2 exactly, including expired batch exclusion and `cannot_compute` | M1 |
| REQ-2 | Decision quantity (`final_qty`) is used in preference to `recommended_qty` | M1 |
| ROR-1 | Rows R1-R6 of table 4.3 | M1 |
| INV-1 | FEFO scenario 4.5, including the movement-sum invariant after each step | M1 |
| INV-2 | Stock-in creates batch plus movement; wastage from expired batch; adjustment cases | M1 (adjustment S) |
| INV-3 | **Concurrency (`mysql`)**: two parallel stock-outs of 8 against 10 usable: exactly one succeeds, stock never negative | M1 |
| ALT-1 | Table 4.4 conditions, thresholds and severities | M1 |
| ALT-2 | Repeated evaluation creates no duplicates; cleared conditions auto-close | M1 |
| ALT-3 | Disabled type opens nothing; role visibility filter per API.md section 6 | M2 |
| ALT-4 | Lazy refresh: reading alerts after more than 60 s re-evaluates | M2 |
| ALT-5 | A manual shortage report closes on a restock recorded after it, even in the same second (compared by movement id); stock from before the report never closes it (added 9 Oct 2026 after the MySQL run) | M2 |
| KIT-1 | Prepared entries for one day sum; served writes `sales_records` with source `kitchen`; served greater than prepared warns and flags; waste greater than prepared warns | M1 |
| KIT-2 | `daily-summary` figures equal the underlying rows (S6) | M1 |

### 5.4 ML and forecasting (S1, S5, A16)

| ID | Test | Tier |
|---|---|---|
| ML-1 | **No leakage:** changing any sales value dated on or after target-6 leaves that target's features unchanged | M1 |
| ML-2 | Train and inference use the same `build_features` (same columns, same order) | M1 |
| ML-3 | `naive_lag7` and `seasonal_mean4` match hand values on a 5-week toy series | M1 |
| ML-4 | Training on a small synthetic set completes, returns all metrics, and is deterministic for the same seed | M1 |
| ML-5 | Selection picks the lowest-MAE candidate; when the baseline wins, `beats_baseline = false` and the reason says so | M1 |
| ML-6 | Item with 7-34 days of history gets `method = baseline`; under 7 days gets no row and run status `partial` | M1 |
| ML-7 | No active model: run status `skipped`, no forecasts, `forecast_failed` alert; no stack trace to the UI | M1 |
| ML-8 | Missing weather uses the seasonal average and sets `weather_estimated`; missing lag is imputed and flagged | M1 |
| ML-9 | Re-run keeps the old rows and flips `is_latest`; activation swaps the active model and the cache reloads | M1 |
| ML-10 | Accuracy view counts only forecasts whose run `as_of_date <= target_date` | M2 |
| ML-11 | **Report check** (run once, recorded): hold-out MAE of the chosen model vs `naive_lag7`, plus WAPE, bias, `oracle_mae` | M1 |

### 5.4a Preparation workflow and actual food usage (added 9 Oct 2026)

Hand-worked values: Chicken Burger forecast 47.3, buffer 10%, batch 6 -> plan 54 (table 4.1, P1). Balance example:
prepared 40 + 20 = 60, served 48, waste 5, staff meals 3, complimentary 2 -> other use 5, unaccounted **2**; with served
58 instead, unaccounted is **-8** and the row is flagged.

| ID | Test | Tier |
|---|---|---|
| PREP-1 | An item without a decision has no preparation status; *start* is refused (`no_plan`) | M2 |
| PREP-2 | Accept plans the item (`planned`, final 54) | M2 |
| PREP-3 | The first prepared entry starts it (`in_progress`); 24 + 30 = 54 prepared | M2 |
| PREP-4 | Start then done with 54 of 54: no warning, done time and audit entries written | M2 |
| PREP-5 | Done with 48 of 54 warns "6 below"; after reopen and an override to 42, "6 above"; done needs a prepared quantity | M2 |
| PREP-6 | Invalid transitions are 409; a done item's plan cannot change (`prep_done`) until reopened; future dates refused | M2 |
| USE-1 | Daily balance equals the hand calculation above (unaccounted 2) | M2 |
| USE-2 | Use above prepared (unaccounted -8) is saved with the warning and the `used_more_than_prepared` flag | M2 |
| USE-3 | Before served is recorded, unaccounted is unknown; waste plus other use above prepared still warns | M2 |
| USE-4 | One figure per item, day and type: recording again replaces it (3 then 4 -> one row of 4), both audited | M2 |
| USE-5 | Quantity 0, -2, 1.5, 10001, an unknown type and a future date are 422 | M2 |
| USE-6 | Other use never changes the sales record (still 48); the daily summary shows other use and unaccounted | M2 |

MariaDB: `prep_status` outside the three steps and a second figure for the same item, day and type are rejected by
the database (`tests/integration/test_schema.py`).

### 5.5 Architecture and data model

| ID | Test | Tier |
|---|---|---|
| ARC-1 | Import rules of ARCH section 1 hold for every module (scan of `import` lines) | M1 |
| DB-1 | `create_all` and the migrations produce the same table names | M2 |
| DB-2 | Every operational table has `outlet_id` (DB5 exceptions listed) | M2 |

## 6. Non-functional tests (NFR2, NFR3)

`tests/perf/test_timing.py`, marker `perf`, run against the seeded database (about 750 days x 10 items; MariaDB in the runs recorded below, MySQL 8.4 since 16 Oct 2026):

| ID | Measure | Pass |
|---|---|---|
| PERF-1 | `run_forecast` for 7 days x all active items | under 5 s |
| PERF-2 | Each dashboard endpoint and each page route, 20 requests | under 3 s (worst), p95 under 1 s for read endpoints |
| PERF-3 | Model training | under 60 s (informational) |
| NEG-1 | Empty database (no data, no model): every page and API returns 200 or a readable 4xx, never 500 or a blank page | M1 |
| NEG-2 | Unknown ids, huge numbers, very long text, unexpected JSON types on every write endpoint give 4xx envelopes | M2 |

The Flask test client excludes network time; the demo machine is also checked by hand with browser dev tools.

## 7. Manual checks

**Responsive and browser (NFR4).** For every M1 and M2 page: 360, 768 and 1280 px in Chrome; then the three kitchen pages, the inventory dashboard and the admin models page in Firefox and Edge. Pass = readable, no sideways page scroll, primary buttons reachable. Results go into the test log (created during testing).

**Security review (NFR5), 30 minutes.** No secrets in git (`git log -p | grep -i password`); `.env` ignored; cookie flags; every write path uses a service; no `|safe` in templates; `SEED_PASSWORD` not defaulted.

## 8. Scripted UAT (NFR1, I10 in REQUIREMENTS)


There is no pilot restaurant and no QA team. The builder runs each script on a clean seeded database, ideally with **one volunteer per role** who is not the builder; times are recorded. Pilot-restaurant UAT and SUS scoring are reported as **not done** (Appendix C, open point). Steps 1-6 of the kitchen script are the NFR1 timing task: target 5 minutes or less for a first-time user.

**K-UAT (kitchen1)**
1. Log in; land on `/kitchen`. 2. Open Prep: recommendations for today show forecast, buffer, batch, recommended. 3. Accept three items, override one with a reason. 4. Add prepared quantities. 5. Open Requirements: the chicken shortage is flagged. 6. Record end-of-day served and one waste entry. 7. Enter a negative quantity: error shown by the field, input kept. 8. Type `/admin` in the address bar: 403 page.

**I-UAT (inventory1)**
1. Log in; dashboard shows open alerts. 2. Stock page: chicken is low; edit its reorder level. 3. Record stock-in of 10 kg chicken with an expiry date; refresh alerts: the shortage alert closes. 4. Try a stock-out larger than stock: message with available quantity. 5. Record wastage for the expired batch. 6. Reorder page: each suggestion shows its terms (compare one with a hand calculation). 7. Try `/kitchen`: 403.

**A-UAT (admin)**
1. Log in; dashboard tiles load. 2. Models: Train; the comparison table shows the baseline and both models; Activate the new version; Run forecast now. 3. Monitor: forecast vs actual and error metrics appear. 4. Data: import a sample sales CSV with one bad row: 1 rejected with a reason; confirm. 5. Catalog: change the Chicken Burger recipe; the kitchen requirement changes. 6. Users: create a kitchen user, deactivate it, confirm login is refused; try to deactivate the last admin: refused.

**Defects.** Logged in the test log: id, script step, severity (1 crash, wrong number or data loss, 2 wrong behaviour with workaround, 3 cosmetic), status. Severity 1 blocks the demo.

## 9. Traceability (M1 stories to tests)

| Requirement | Tests |
|---|---|
| C1 | SEC-2, SEC-3, SEC-4, SEC-5, SEC-6, SEC-17, SEC-18 |
| C2 | SEC-1, SEC-7 |
| C4 | VAL-1 to VAL-6, SEC-8, SEC-9 |
| A14, A15 | IMP-1 to IMP-5 |
| S1, A16 | ML-2 to ML-11, PERF-1 |
| S2, K3 | REC-1, REC-2 |
| S3, K9 | REQ-1, REQ-2 |
| S4, I8 | ALT-1, ALT-2 |
| S5 | ML-6 to ML-8, NEG-1, IMP-5 |
| S6, K5-K7 | KIT-1, KIT-2 |
| I3, I5, I6, I13 | INV-1 to INV-3 |
| I7, I9 | ROR-1 |
| NFR2 / NFR3 / NFR4 / NFR5 | PERF-1, PERF-2 / NEG-1, IMP-5 / section 7 / SEC-*, section 7 |
| NFR6 / NFR7 / NFR8 | ARC-1, ML-2 / DB-2 / VAL-*, IMP-*, DB constraints |
| NFR1 | K-UAT, I-UAT, A-UAT timings |

## 10. Exit criteria for the MVP

1. All M1 tests green (`pytest -q`), including MariaDB tests. ARC-1 and SEC-1 green.
2. Coverage on `app/services` and `app/ml` at least 80%, or the gap is listed.
3. ML-11 recorded: the hold-out result, honest whichever way it falls.
4. All three UAT scripts executed at least once on a clean seed; no open severity-1 defect.
5. PERF-1 and PERF-2 within limits on the seeded database, on the demo machine.
6. Responsive check done for the M1 pages.

## 11. Explicitly not done

Load testing beyond section 6, penetration testing, accessibility audit with a screen reader, pilot-restaurant UAT, SUS scoring, and validation of forecast accuracy on real *Sri Lankan* restaurant data. (Browser automation has since been added, and the forecasting method was validated offline on external real datasets; see `ML_EVALUATION_REAL_DATA.md` on the staging branch.) These go in the report's limitations section.

## End-to-end decision chain (E2E-1, 14 Oct 2026)

`tests/integration/test_end_to_end_workflow.py` drives the whole chain through the API with all three roles on
controlled data: sales import (check, then save) -> forecast accuracy (MAE, WAPE, MAPE, bias) -> 7-day forecast with a
missing day -> confirmed and pending pre-orders -> prep plan (no double counting: 58 pre-ordered and 47.3 forecast give
60, not 108) -> accept / override with reason -> BOM requirements with an expired batch excluded -> stock request
approved and issued FEFO -> inventory wastage of the expired batch -> prepared / served / waste / other use -> waste
report value -> admin dashboard sales, revenue, waste rate and forecast total -> 7-day ingredient demand -> reorder ->
purchase order sent and received -> stock consistency -> movement report -> completed pre-order. Every expected value
is worked out by hand in the test's comments. It passes on SQLite and on MySQL 8.4.

