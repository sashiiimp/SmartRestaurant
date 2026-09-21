# SmartRestaurant: Implementation plan

Read after `REQUIREMENTS.md`, `ARCHITECTURE.md`, `DATABASE.md`, `API.md`, `ML_PLAN.md`, `UI_PLAN.md`. Testing is in `TESTING.md`. **No code is written until this plan is approved.**

## 0. Status (21 Sep 2026)

**M1 and M2 are complete and tested** (144 automated tests, 91% service/ML coverage, browser tests of all three roles, all 17 pages checked at 360/768/1280 px; see `TEST_LOG.md`). Stretch items built: CSV download of reports (A13) and the settings and alert configuration page (A6, A7). Not built: pre-orders, availability toggle, expiry page, adjustments, manual shortage report, suppliers/purchase orders, admin inventory overview, server deployment, feature ablation. Actual ML results are in `ML_EVALUATION.md`.

**Scope change approved 21 Sep 2026:** every function in the approved proposal is now in scope, including all former S and X items that the proposal lists. Section 3A is the plan for the remaining work; section 4 is superseded for those items. The work is done in tiers 1 to 3 and each group is tested on a copy of the database (`smartrest_work`) before the live demo database is upgraded.

## 1. Situation

| Item | Value |
|---|---|
| Today | Mon 21 Sep 2026 (from the machine clock) |
| Deadline | **Mon 28 Sep 2026**, so 7 build days (21-27 Sep) plus the 28th as submission and buffer. `REQUIREMENTS.md` A1 was written on 19 Sep and said "9 days"; two days have passed. |
| Builder | One person with Claude Code. **Assumed capacity: 8 focused hours per day, 56 hours in total.** Please correct this; every estimate below scales with it. |
| Data | Synthetic and labelled as such (A3). |
| Demo | Local machine (fallback is the primary). A server deployment is a stretch item. |
| What "done" means | The demo loop in section 3 works end to end for all three roles on a clean seeded database, the M1 tests pass, and the UAT scripts were run. |

## 2. Tiers (these replace P1/P2/P3 for scheduling)

| Tier | Meaning | Stories |
|---|---|---|
| **M1** | **Core demo loop.** Never cut. | 26 |
| **M2** | Rest of the MVP. Built after M1; shrinks first when behind (section 7). | 12 |
| **S** | Stretch. Only if ahead of schedule, in the order listed in section 5. A wish list, not a commitment. | 11 |
| **X** | Postponed after 28 Sep. Documented as future work and stated in the report. | 7 |

## 3. Final MVP scope

**The demo loop (M1):** synthetic history loaded, model trained and activated, forecast generated, **kitchen sees a preparation recommendation with the numbers behind it**, accepts or overrides it, records prepared, served and waste, sees **ingredient requirements and a shortage**, an **alert** appears, the **inventory manager sees a reorder suggestion**, records stock-in, and the alert clears. Login and strict RBAC wrap all of it.

### M1 stories (26)

| Area | Stories |
|---|---|
| Common | C1 login and role redirect, C2 RBAC, C4 validation |
| Kitchen | K1 dashboard, K2 forecast view, K3 recommendations (accept and override), K5 record prepared, K6 record served, K7 record waste, K9 requirements and shortage |
| Inventory | I1 dashboard, I2 ingredients, I3 stock levels, I4 min and reorder levels, I5 stock-in, I6 stock-out (FEFO), I7 ingredient forecast, I8 alerts, I9 reorder suggestions, I13 wastage (as a movement type) |
| System | S1 forecasts, S2 prep quantities, S3 requirements and shortage, S4 alerts, S5 missing-data handling, S6 outcome storage |
| Enabling parts of M2 stories | A14 import **service** (the generator uses it), A16 train, activate and forecast **CLI** |

### M2 stories (12)

C3 (logout, 30-minute idle timeout), A1 admin dashboard, A2 user management, A3 role change (inside the A2 edit, audited), A4 menu, A5 recipes, A8 sales monitoring, A9 forecast monitoring, A11 waste monitoring, A14 import **page**, A15 promotions form (holidays and weather come from the seed and CSV import through API or CLI), A16 models **page**.

### S stories (11), in build order if time allows

1. A13 CSV download on the monitor tabs (same service rows)
2. A6 and A7 settings and alert-configuration pages (until then: `flask smartrest set-setting`)
3. K13 food availability toggle
4. K10 pre-orders (the K3 pre-order floor is already in the M1 formula and tested)
5. I12 expiry list page (expiry **alerts** are already M1)
6. I14 stock adjustment
7. K12 manual shortage report
8. I10 suppliers page and I11 purchase orders (create from a reorder row, receive)
9. A10 admin inventory overview (reuses inventory endpoints read-only)

That is 11 stories (A13, A6, A7, K13, K10, I12, I14, K12, I10, I11, A10). Two further stretch items are not stories: holiday and weather tabs on the data page (completes A15 in the UI), and server deployment (gunicorn and nginx, time-boxed to 2 hours).

## 3A. Approved scope change: remaining proposal functions (21 Sep 2026)

Basis: audit of the implementation against `docs/proposal.pdf` and the role function tables. Full design: `PLAN_MISSING_FUNCTIONS.md`. Not in scope, as in the proposal: POS or payments, automatic supplier ordering or supplier integration, accounting, staff scheduling, multi-branch.

| # | Function | Role | Tier | h | Status |
|---|---|---|---|---|---|
| 1 | Manage Suppliers | Inventory | 1 | 2.0 | todo |
| 2 | Stock Adjustment | Inventory | 1 | 2.5 | todo |
| 3 | Manage Purchase Orders | Inventory | 1 | 7.0 | todo |
| 4 | Manage Food Availability (toggle on the prep page) | Kitchen | 1 | 1.5 | todo |
| 5 | Manage Pre-Order | Kitchen | 1 | 4.0 | todo |
| 6 | Inventory Monitoring and Inventory Demand Forecast Monitoring (admin page) | Admin | 1 | 2.0 | todo |
| 7 | Request Kitchen Stock and Manage Kitchen Stock Requests | Kitchen, Inventory | 2 | 8.0 | todo |
| 8 | Validate Inventory Data (consistency check) | Inventory | 2 | 1.5 | todo |
| 9 | Food Demand Forecast Monitoring (admin forecast tab) | Admin | 2 | 2.0 | todo |
| 10 | System Reports: inventory and movements, CSV | Admin | 2 | 2.5 | todo |
| 14 | Shortage Reporting (manual report creating a `manual_shortage` alert) | Kitchen | 2 | 2.0 | todo |
| 15 | Restaurant Information Management (name, address, contact, opening days and hours) | Admin | 2 | 1.5 | todo |
| 11 | Manage Daily Order | Kitchen | 3 | 3.5 | todo |
| 12 | Record Ingredient Usage | Kitchen | 3 | 3.5 | todo |
| 13 | System Analytics | Admin | 3 | 4.0 | todo |

Functions 14 and 15 were found in a second check of the proposal tables after the first audit. Food Preparation Management is treated as covered by the prep plan decisions plus prepared recording; no separate status workflow is added.

**Decisions taken (21 Sep 2026).**
1. Capacity is 8 h a day; Sat 26 is a build day; features freeze Sun 27 at noon.
2. Daily order: an internal record (open, fulfilled, cancelled) that feeds no calculation.
3. Ingredient usage: expected usage (prepared x recipe) plus an optional recorded amount; it does not move stock (DB8).
4. Availability: one persistent flag flipped by the manager; no automatic suggestion.
5. Stock request: issue may be partial per line; the requester may cancel while pending.
6. Purchase order receipt cannot exceed the quantity ordered; receiving does not need "send" first.
7. Adjustment compares the counted quantity with on-hand stock (including expired); a shortfall is drawn from the earliest-expiry batches first.
8. Orders and pre-orders share one `/kitchen/orders` page with two tabs.

**Rules for this work.** Develop and test on `smartrest_work` (a clone of the demo database) and `smartrest_test`; run `flask db upgrade` on the live database only at the end, after a dump. Do not run `tests/ui/smoke.py` or the perf tests against the live demo data. One commit per function or group; never push without instruction.

## 4. Postponed or cut (X)

*Superseded 21 Sep 2026 by section 3A for every item the proposal lists (K8 ingredient usage, K10 orders and pre-orders, K11 and I15 stock requests, A12 analytics, I16 consistency check). Kept for history.*

| Story or feature | Why it is safe to cut |
|---|---|
| K4 plan status workflow (planned, in progress, done) | Accept or override on the recommendation *is* the plan; the status workflow adds screens, not decisions |
| K8 manual ingredient usage | Derived usage is already implied by prepared x recipe (I6 in REQUIREMENTS) |
| K11 and I15 kitchen stock requests | Needs a two-sided workflow; the kitchen still sees stock and shortages (K9) |
| Daily orders (the orders half of K10) | Pre-orders (S) carry the forecasting value; orders do not feed any calculation |
| A12 analytics page | Monitor tabs already show demand, error and waste trends |
| C5 change own password | Admin can reset; low value |
| I16 consistency-check page | The movement-sum invariant is a test (INV-1) |
| Also postponed | Prediction intervals, weather API, hyperparameter search, per-item models, unit conversions in recipes, PDF export, scheduler or cron, pilot-restaurant UAT, real-data validation |

The proposal's function tables list 47 functions; after these cuts the report must state which are implemented, which are stretch and which are future work (mapping in `REQUIREMENTS.md` Appendix A plus this section).

## 5. Estimates, schedule and gates

Vertical slices: each day ends with something that runs. Hours include tests. Owners: the builder directs, Claude Code writes, the builder reviews and runs.

| Day | Date | Slice and work packages | h | Gate (exit criterion) |
|---|---|---|---|---|
| D0 | Mon 21 | **Foundation.** Python and DB environment check (ML_PLAN M-8), repo and app factory, config, envelope and error handlers (1.5); all models and the initial migration (2.5); auth service, login, lockout, RBAC decorators, base layout, role landing placeholders (2.5); seed CLI: outlet, users, settings, catalog, recipes, suppliers, opening stock (1); `test_architecture` and `test_rbac` (1) | 8.5 | Log in as each role and reach its own placeholder page; another role's page returns 403; SEC-1 and ARC-1 green |
| D1 | Tue 22 | **Data and forecast.** `holidays_lk.csv` curation (1); synthetic generator loading through import services (2); sales and context import service with dry run and tests (2); `app/ml` package (2.5); `ForecastingService`, `ForecastRun`, CLI train, activate, forecast, backfill (1.5) | 9 | `generate-data`, `train --activate`, `forecast` run from the CLI; metrics table printed and stored; ML-1 to ML-9 green; **ML time-box: stop at 5 h in total** |
| D2 | Wed 23 | **Prep recommendation and kitchen recording.** Vue infrastructure, vendored libraries, `api.js`, shared components, K2 page (1.5); `RecommendationService` prep (S2) with table 4.1 tests (1.5); `KitchenService` and API: prepared, served, waste, daily summary (2); kitchen `prep` and `record` pages (3) | 8 | Kitchen user sees forecasts and recommendations, accepts and overrides, records prepared, served and waste on a phone-width screen; REC-1, REC-2, KIT-1, KIT-2 green |
| D3 | Thu 24 | **Stock, requirements, alerts.** `InventoryService`: ingredients, levels, stock-in, FEFO stock-out, wastage, movement invariant, with tests including the concurrency test (3); requirements, ingredient forecast and reorder (B2, B3) with tests 4.2 and 4.3 (3); `AlertService` (B4) with tests (2); kitchen requirements page and K1 dashboard (2) | 10 | Requirement numbers equal the hand calculation; shortage produces an alert; stock-in clears it; INV-1 to INV-3, REQ-1, ROR-1, ALT-1, ALT-2 green |
| D4 | Fri 25 | **Inventory UI and start of admin.** Inventory API and pages: stock, movements, forecast, reorder (4.5); inventory dashboard (1); admin users page (1); catalog page (1.5); data page with sales import and promotions (1.5) | 9.5 | **M1 complete.** I-UAT and K-UAT run end to end. Tag `m1` |
| D5 | Sat 26 | **Admin oversight and hardening.** Models page (1); admin dashboard and `DashboardService` admin part (1.5); monitor tabs for sales, forecast and waste (2.5); full RBAC matrix, negative tests, timing tests, responsive pass (2.5); bug buffer (1.5) | 9 | **M2 complete (or trimmed by the ladder).** A-UAT run. PERF-1 and PERF-2 pass. Tag `m2` |
| D6 | Sun 27 | **Freeze and prove.** UAT rounds and fixes (2.5); ML evaluation write-up with figures (1.5); README, demo script, screenshots (2); backup dump and local fallback rehearsal (1); buffer (1). **Feature freeze at noon.** Stretch items only before the freeze, in section 3 order. | 8 | Demo rehearsed twice from a clean reset; `TEST_LOG.md` complete; `mvp` tag |
| D7 | Mon 28 | Submission. Morning is buffer for severity-1 defects only. No new features. | | Submitted |

**Total: about 62 h planned against 56 h available.**

## 6. Recommended implementation order

1. **Environment and foundation (D0)**: nothing else can be verified without models, migration, auth and the RBAC test.
2. **Data and ML (D1)**: the riskiest and least certain part; it needs real numbers early so everything downstream is built against actual data, not placeholders.
3. **Prep recommendation and kitchen recording (D2)**: the first visible payoff and the heart of the proposal (forecast to action).
4. **Stock, requirements, alerts (D3)**: completes the forecast-to-purchase chain (FR5 to FR7).
5. **Inventory UI (D4)**: the second role's pages, using services that are already tested.
6. **Admin master data and imports (D4 to D5)**: mostly forms over tested services.
7. **Admin oversight and monitoring (D5)**: depends on outcomes existing (backfilled forecasts and actuals).
8. **Hardening, UAT, evaluation, demo (D5 to D6)**.

Within every slice: service and its tests first, then API, then page. The service and API for a feature are never postponed even when its page is trimmed.

## 7. Trim ladder (pre-approved order for dropping M2 work)

The plan is about 6 hours over the assumed capacity, so **expect to use most of this ladder.** Decide at the D4 and D5 gates, not late at night. Each step keeps the service and API; only the page is dropped.

| Step | Drop | Falls back to | Saves |
|---|---|---|---|
| L1 | Charts on monitor tabs (A8, A11) | tables only | 1.0 h |
| L2 | Admin dashboard A1 reduced to four tiles | four tiles and the alert list | 0.7 h |
| L3 | Users page (A2) | seeded users and `flask smartrest create-user`; role and deactivation through the API | 1.0 h |
| L4 | Catalog page (A4, A5) | seed catalog; recipes editable through `PUT /menu-items/{id}/recipe` | 1.5 h |
| L5 | Models page (A16) | CLI (`train`, `activate`, `forecast`) | 1.0 h |
| L6 | Forecast monitor tab (A9) | the metrics table only, no forecast-vs-actual chart | 1.0 h |

All six saved would give 6.2 h. **Never on the ladder:** anything in M1, the RBAC matrix, the hand-calculation tests, and the UAT runs.

**Slip rules.** If a day ends more than half a day behind: (1) trigger the next ladder step; (2) never carry M1 work past D4; (3) if the ML result is not good by the 5-hour cap, ship the baseline comparison as the result and move on.

## 8. Demo script (about 8 minutes, on the local machine, database freshly reset)

1. **Admin** `/admin/models`: the "Synthetic demo data" banner, the active model against the naive baseline on the hold-out, and forecast vs actual (A9).
2. **Kitchen** `/kitchen/prep`: a recommendation with its numbers (forecast, buffer, batch); Accept one, Override one with a reason; add prepared quantity.
3. **Kitchen** `/kitchen/requirements`: chicken is short by X kg (matches the hand calculation).
4. **Inventory** `/inventory`: the projected stock-out alert and the reorder suggestion with its terms.
5. **Inventory** `/inventory/movements`: stock-in of chicken; the alert clears; back in the kitchen the shortage is gone.
6. **Kitchen** `/kitchen/record`: end-of-day served and one waste entry.
7. **Security**: as kitchen, open `/admin`: 403.

Fallbacks: a `mysqldump` of the ready-to-demo state; screenshots of every step in the README; the same steps runnable from the CLI.

## 9. Risks

| Risk | Likelihood | Response |
|---|---|---|
| Time: 62 h planned vs 56 h available | High | Trim ladder (section 7); S tier is a wish list |
| Python 3.14 on this machine lacks wheels for scikit-learn or XGBoost | Medium | Check on D0; use Python 3.12 (needs installing) |
| Model does not beat the baseline | Medium | Reported honestly (S1); the decision layer still demonstrates the system |
| Vue and Jinja delimiter mistakes cost time | Medium | `[[ ]]` rule in `CLAUDE.md` and the page skeleton in `UI_PLAN.md` |
| Holiday file errors | Low | Generator and app read the same file; verify before the report |
| Demo-day machine or network trouble | Medium | Local fallback and vendored JS from the start |
| The database here is MariaDB 11.8, not MySQL | Low | Portable types only; integration tests run on it |
| Scope creep | High | Section 10 change control |

## 10. Working agreements

- **Change control.** Any scope change edits this file first (tier, hours, ladder), then the code.
- **Git.** `git init` at approval. One commit per finished work package, tagged `m1`, `m2`, `mvp`. Never commit `.env`, `instance/`, `data/synthetic/`, or any password.
- **Daily rhythm.** Start of day: read the day's row above. End of day: update the "done" state in this file (a checkbox column is added when coding starts), record hours actually spent, decide on the ladder.
- **Definition of done for a story:** service tested, API matches `API.md`, page matches `UI_PLAN.md`, RBAC test still green, no business logic in controllers (ARC-1 green).
- **Documentation follows code.** If the code has to differ from a planning document, change the document in the same commit.

## 11. Changes made to earlier documents while planning

| Where | Change |
|---|---|
| `ARCHITECTURE.md` | Model list amended (section 10 added): `Outlet`, `LoginAttempt`, `ForecastRun`, `PromotionItem` added; `IngredientWastage` dropped; `Order` and `StockRequest` postponed. Your three open points are recorded as accepted: eight services, the import-rule test, and run commands without a scheduler. |
| `REQUIREMENTS.md` | C4 note: sales quantity may be 0 (zero sold is a valid observation); A4 gains `batch_size`; Appendix B points to this file's tiers. |
| Not changed | Everything else. Where a planning document refines a story, the story text stands and the refinement is in the planning document. |

## 12. Assumptions to confirm at approval

1. Capacity is 8 h per day for 7 days.
2. The 28th is the date the working system, the report and the viva material are due. If only the system is due on the 28th, more time is free for stretch items.
3. MariaDB 11.8 is acceptable as "MySQL" in the report.
4. Python 3.12 may be installed for the project if 3.14 lacks the ML wheels.
5. The postponed list in section 4 is acceptable, including that daily orders and kitchen stock requests are not built.
