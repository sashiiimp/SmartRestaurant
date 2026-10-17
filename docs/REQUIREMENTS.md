# SmartRestaurant: Requirements

Team ForeSight, CSE5015. Source of truth: the project proposal (FR1-FR12, NFR1-NFR8, and the per-role function tables on pp. 4-7).

## 0. Assumptions and flagged issues (read first)

### Assumptions (defaults used where the team gave no answer)

| # | Assumption |
|---|---|
| A1 | **Schedule and capacity (confirmed).** Project started Sep Week 1. Hard deadline is **28 Sep 2026**. Today is 19 Sep, so **9 calendar days remain.** The proposal Gantt runs to Oct Week 2 and does not fit. Work is planned for **one builder**; the named team roles in the proposal are ignored. Every story below carries a priority so the project plan can cut to fit. |
| A2 | **Priorities.** **P1** = the MVP demo loop (forecast, prep recommendation, ingredient requirement, shortage, alert, reorder). **P2** = completes the role's dashboard. **P3** = stretch, cut first. |
| A3 | **Data (confirmed).** No real restaurant data: a documented synthetic dataset will be generated (see `ML_PLAN.md`) and labelled as synthetic in the UI, reports and viva. Real data can replace it through the same CSV import (FR2/FR3). Location for weather and holidays is **Colombo, Sri Lanka**. |
| A4 | **"Sales" means quantity sold per menu item per day.** POS and payments are out of scope, so sales arrive by CSV import or by the kitchen's daily "served quantity" entry. Revenue = quantity x the unit price stored on that record. |
| A5 | **Forecast unit.** Daily, per menu item, 7-day horizon. No hourly or per-shift forecasts. |
| A6 | **Two waste types.** *Prepared-food waste* (kitchen, per menu item) and *ingredient wastage* (inventory, per ingredient). They are separate records and separate reports. |
| A7 | **Orders and pre-orders** have no customer-facing channel (POS is excluded), so they are entered manually by the Food Production Manager. Confirmed pre-orders count as committed demand in preparation planning. |
| A8 | **Roles are fixed** (three roles, one role per user). "Role & Access Management" means assigning a role, not building a permission editor. |
| A9 | **Strict RBAC (FR1/NFR5).** Each role sees only its own dashboard and pages. A small set of read-only shared endpoints (e.g. forecasts, alerts) is listed in `API.md`. |
| A10 | **Single restaurant.** All tables carry `outlet_id` (NFR7); the UI never shows it. |
| A11 | **Currency and language.** LKR, English only. |
| A12 | **Reports.** On-screen plus CSV export. PDF export is out of scope. |
| A13 | **Frontend.** Vue.js 3 loaded from a CDN (no build step, no Node toolchain) inside Jinja2 pages, with Bootstrap 5 for layout and a JS chart library. Vue handles interactive parts and calls the JSON API. Flask still renders every page and enforces RBAC. No separate SPA. |

### Issues found in the proposal

| # | Issue | Handling |
|---|---|---|
| I1 | Gantt (to Oct Week 2) is longer than the 28 Sep deadline. | See A1. the project plan will propose a cut list. |
| I2 | No Gantt task for obtaining data, yet forecasting starts Sep Week 2 and needs it. | Synthetic-data generation becomes an explicit early task (A3). |
| I3 | The function tables list 47 functions, far more than FR1-FR12 covers (users, menu, recipes, suppliers, POs, orders, pre-orders, kitchen requests). | All 47 are mapped to stories (Appendix A). Extras are P2/P3. |
| I4 | "Pre-orders" conflicts with "POS excluded". | See A7. |
| I5 | Weather is a feature (FR3), but forecasting tomorrow needs tomorrow's weather. | Use a weather forecast source with a seasonal-average fallback, or drop the feature. Decided in `ML_PLAN.md`. |
| I6 | "Ingredient Usage Recording" and "Actual Food Usage Recording" overlap "Prepared" and "Served" recording. | Ingredient usage is derived from prepared quantity x recipe by default. Manual usage entry is P3. "Actual food usage" is interpreted as served quantity (K6). |
| I7 | The Gantt gives the DB design to Nimansa, but the role table gives it to Dewmi. Loads are uneven. | Moot: planning for one builder (A1). |
| I8 | Literature-review R2 = 0.817 is from a non-peer-reviewed preprint with an assumed waste variable. | Not used as a target. Accuracy is judged against a naive baseline (S1). |
| I9 | Vue.js was requested, but the proposal fixes the frontend as HTML/CSS/JavaScript/Bootstrap. | See A13: Vue via CDN inside Jinja2 pages, so the proposal stack and strict MVC both hold. |
| I10 | Testing/UAT in the proposal assumes a QA person and pilot restaurant staff. | With one builder, UAT is a scripted walkthrough per role, and pilot-restaurant UAT is reported as not done. |

---

## 1. Roles

| Role | Home page after login | Purpose |
|---|---|---|
| System Administrator | `/admin` | Oversight, master data, users, settings, analytics, reports, model management |
| Food Production Manager (Kitchen) | `/kitchen` | Decide and record what to prepare, serve and waste each day |
| Inventory & Procurement Manager | `/inventory` | Keep stock right, buy the right things at the right time |

Story ID prefixes: **C** common, **A** admin, **K** kitchen, **I** inventory, **S** system/service behaviour.
Format: story, priority, traces, acceptance criteria (AC).

---

## 2. Common stories (all roles)

### C1 Login and role redirect (P1), FR1, NFR5
*As a user, I want to log in and land on my own dashboard so that I see only what my job needs.*
- Given valid credentials, when I submit the login form, then I am redirected to `/admin`, `/kitchen` or `/inventory` according to my role.
- Given invalid credentials, then I see one generic error and the response does not reveal whether the username exists.
- Given a deactivated account, then login is refused with the same generic error.
- Passwords are stored only as salted hashes; they never appear in logs, responses or the DB dump.
- After 5 failed attempts for one username from one address within 10 minutes, further attempts for it from that address are refused for 5 minutes; an address with 20 failures over any usernames is refused as well. Failures from elsewhere never lock a user out of the restaurant's own terminal.
- Passwords are 8 to 128 characters, must not contain the username, must not be one repeated character and must contain at least one digit or symbol.

### C2 Role-based access control (P1), FR1, NFR5
*As the owner of the data, I want other roles blocked from my pages and APIs.*
- Given I am not logged in, a page request redirects to login and an API request returns `401` JSON.
- Given I am logged in as role X, a page or API request restricted to role Y returns `403` (JSON for API), and nothing from role Y is rendered.
- Role checks happen on the server for every route; hiding a menu link is never the only control.
- Automated test iterates every route against every role (see `TESTING.md`).

### C3 Logout and idle timeout (P2), NFR5
- Logout ends the session on the server, so a copied session cookie stops working too; a password reset or a deactivation ends all of that user's sessions. The Back button does not reveal protected pages.
- Sessions expire after 30 minutes idle.

### C4 Input validation (P1), NFR8
*As the business, I want bad data rejected so that forecasts are not distorted.*
- Quantities must be numeric and > 0 (adjustments may be signed but never zero); prices >= 0. **Exception:** sales/served quantity may be 0, because "zero sold" is a valid observation (`DATABASE.md` 2.3).
- Dates cannot be in the future for actual records (sales, prepared, waste, stock-in).
- One sales record per (outlet, item, date); a duplicate is rejected with a message, or updates the row after explicit confirmation.
- Text fields are length-limited and stored/rendered escaped. Forms carry CSRF protection.
- Errors are shown next to the field and the entered data is kept in the form.

### C5 Change own password (P3), NFR5
- Requires the current password; new password minimum 8 characters.

---

## 3. System Administrator stories

### A1 Admin dashboard (P1), FR10, FR12
*Covers: System Dashboard.*
- Shows, for the last 7 and 30 days: total sales quantity and revenue, next-7-day forecast total, count of low-stock ingredients, prepared-food waste quantity and value, open alerts by severity, and the 10 most recent system activities.
- Loads in under 3 s with the seeded dataset (NFR2). Each tile links to its detail page.
- Empty states (no forecast yet, no data) show a message, not an error (NFR3).

### A2 User account management (P1), FR1
*Covers: User Account Management.*
- Admin can create a user (name, username, email, role, initial password), edit, deactivate and reactivate. P2: reset password.
- Usernames are unique; deletion is not allowed (deactivate only), so history is preserved.
- The last active admin cannot be deactivated or have their role changed.

### A3 Role assignment (P2), FR1
*Covers: Role & Access Management.*
- Admin assigns exactly one of the three roles to each user. A role change takes effect on the next request.
- Role changes are written to an audit/activity log with who and when.
- *(14 Oct 2026)* Administration > **Role access** shows, read-only, which role can open each page and which roles receive each alert type, taken from the rules the server applies.

### A4 Menu management (P1), FR2
*Covers: Menu Management.*
- Admin creates, edits, activates and deactivates menu items (name, category, price in LKR, portion unit, shelf life in hours, **batch size**, used by K3 rounding).
- Deactivated items disappear from data entry and forecasts, but their history remains in reports.
- Item names are unique within the outlet.

### A5 Recipe / BOM management (P1), FR6
*Covers: Recipe/BOM Management.*
- For each menu item, admin defines ingredient lines (ingredient, quantity per portion, unit).
- Quantity > 0; the unit must match the ingredient's base unit (or a defined conversion); an ingredient cannot appear twice in one recipe.
- Changing a recipe affects future requirements only, not past records.
- An active menu item with no recipe is flagged on the admin dashboard, because ingredient requirements for it would be zero.

### A6 Restaurant information and settings (P2)
*Covers: Restaurant Information Management, System Settings.*
- Admin edits restaurant name, address, contact, opening days and hours.
- Admin edits global settings: safety buffer % for preparation, forecast horizon (default 7 days), currency label.

### A7 Alert configuration (P2), FR7, FR10
*Covers: Alert Configuration.*
- Admin enables or disables each alert type and sets its thresholds: expiry warning days (default 3), waste-risk threshold, stock-out risk threshold.
- Changes apply to the next alert run; existing alerts are not rewritten.

### A8 Sales and revenue monitoring (P1), FR12
*Covers: Sales & Revenue Monitoring.*
- Shows sales quantity and revenue by day, week and month, with top and bottom items and a date-range filter.
- Revenue uses the price stored on each sales record, not the current menu price.
- Chart totals equal the sum shown in the table beneath it.

### A9 Forecast monitoring (P1), FR4, FR11, FR12
*Covers: Food Demand Forecast Monitoring.*
- Shows forecast vs actual per item and date once actuals exist, and forecast error metrics (MAE, MAPE) per item and overall.
- Shows the active model name, version, training date and its evaluation metrics.
- A forecast run that failed or was skipped is visible, with the reason.

### A10 Ingredient forecast and inventory overview (P2), FR6
*Covers: Inventory Demand Forecast Monitoring, Inventory Monitoring.*
- Read-only view of the ingredient requirement forecast and current stock per ingredient with status (OK / low / out).
- Numbers match the Inventory dashboard for the same date.

### A11 Waste monitoring (P1), FR12
*Covers: Food Waste Monitoring.*
- Shows prepared-food waste and ingredient wastage separately (assumption A6 in section 0), by day/week, by item or ingredient, by reason, with estimated cost.
- Trend line and top-5 wasted items are shown for the selected range.

### A12 Analytics (P2), FR12
*Covers: System Analytics.*
- Demand by day of week, effect of holidays and promotions on sales, forecast error over time, and waste vs stock-out days.
- Each chart states its date range and data source (synthetic vs real).

### A13 Reports (P2), FR12
*Covers: System Reports.*
- Reports: sales, forecast accuracy, waste (food and ingredient), inventory trend and stock movements.
- Each report is viewable on screen with date filters and exportable to CSV.
- Exported figures equal the on-screen figures.

### A14 Import sales history (P1), FR2, NFR3, NFR8
- Admin uploads a CSV of (date, item, quantity sold, unit price optional).
- Rows are validated first; the result shows N accepted, M rejected, with row number and reason per rejected row. Accepted rows are saved only after the admin confirms.
- Re-importing the same file does not create duplicates.
- Unknown item names are reported, not silently created.

### A15 Record/import contextual data (P1), FR3
- Admin can manage holidays (including Poya days), promotions (name, dates, items or all, type/discount %) and daily weather (rain mm, temperature), by form or CSV.
- Missing weather or holiday values do not block forecasting (see S5).
- Data source of each weather row is stored (manual, imported, API).

### A16 Model management (P1 for trigger via CLI/button; P2 for version list), FR4, NFR6
- Admin (or the ML owner via CLI) can start a manual retrain. It records model version, training window, features, and metrics.
- A new model becomes active only after an explicit "activate" step; the previous model stays available for rollback.
- No automatic retraining exists (out of scope).

---

## 4. Food Production Manager (Kitchen) stories

### K1 Kitchen dashboard (P1), FR10
*Covers: Kitchen Dashboard.*
- Shows today's predicted demand, recommended prep quantity and prepared-so-far per item, ingredient requirements with shortage flags, and unresolved alerts.
- Loads in under 3 s (NFR2) and works on a phone-sized screen (NFR4).

### K2 View daily demand forecast (P1), FR4
*Covers: Food Demand Forecast.*
- Shows the 7-day forecast per menu item with the forecast date, generated-at time and model version.
- If no forecast exists for a date, shows "No forecast yet" and the last available date.

### K3 Preparation recommendations (P1), FR5
*Covers: Preparation Recommendations.*
- Recommended quantity = forecast x (1 + safety buffer %), rounded up to the item's batch size, and never less than confirmed pre-orders for that date.
- The page shows forecast, buffer, pre-orders and final recommendation, so staff can see why.
- Manager can accept or override the quantity; overrides are stored with a reason (for later evaluation, FR11).

### K4 Daily preparation plan (P2), FR5
*Covers: Food Preparation Management.*
- Manager confirms the day's plan (one line per item), and each line moves planned, then in progress, then done.
- Confirming a plan triggers ingredient requirement and shortage checks (K9).
- *Built 9 Oct 2026 (feature branch, not yet deployed):* accepting or overriding a recommendation plans the item; the
  first prepared quantity (or *Start*) puts it in progress; *Mark done* needs a prepared quantity above 0 and warns when
  it differs from the plan; *Reopen* goes back to in progress. A finished item's plan cannot change until it is reopened.
  Statuses are stored on the decision row (`recommendations.prep_status`). Tests PREP-1 to PREP-6.
- *Simplified 16 Oct 2026 (staging branch prep-simplify):* the Plan & prepare page has no separate Accept button. The
  first *Add prepared* of an undecided item accepts today's recommendation (same stored snapshot; audit entry marked
  `auto`); *Change plan* (the override, reason required) sets another quantity; *Use new N* takes a recommendation that
  moved after acceptance. The accept API is unchanged. *Finish preparation* (done) asks first, showing prepared against
  planned. The forecast is in each item's breakdown and on the 7-day forecast tab. Tests PREP-AUTO-0 to 15.

### K5 Record prepared quantity (P1), FR8
*Covers: Preparation Quantity Recording.*
- Manager records quantity prepared per item per date and time (multiple entries per day are summed).
- Validation per C4; the running total is visible immediately.

### K6 Record served/sold quantity (P1), FR8, FR2
*Covers: Sales/Served Quantity Recording. (Until 9 Oct 2026 it also stood in for Actual Food Usage Recording; that
function now has its own story, K14.)*
- Manager records portions served/sold per item per day (single entry or end-of-day).
- This writes the daily sales record used for training (source = `kitchen`), respecting the one-record-per-item-per-day rule (C4).
- Served > prepared for the same day is allowed only with a warning (can happen due to leftovers or carry-over), and is flagged for review.

### K7 Record prepared-food waste (P1), FR8
*Covers: Food Waste Recording.*
- Manager records item, quantity, reason (overproduction, quality, expired, other) and date.
- Waste cannot exceed prepared for that day without a warning; waste appears in A11 and the kitchen dashboard.

### K8 Ingredient usage (P3), FR8
*Covers: Ingredient Usage Recording.*
- By default, usage is derived: prepared quantity x recipe.
- Optional manual override of actual ingredient use with reason. Deferred if time is short.

### K9 Ingredient requirements and shortage flags (P1), FR6, FR7
*Covers: Ingredient Requirements.*
- For the confirmed or recommended plan, lists each ingredient's required quantity (sum over items of quantity x recipe), current stock, and status: sufficient / short by X.
- An item with no recipe is listed under "cannot compute" instead of being ignored.
- Requirement figures equal a hand calculation for a sample plan (see `TESTING.md`).

### K10 Daily orders and pre-orders (P2), FR5
*Covers: Daily Order Management, Pre-Order Management.*
- Manager enters, edits or cancels orders and pre-orders (item, quantity, date, customer note). Since 13 Oct 2026 a pre-order also has a customer name, optional contact, pickup time, and the status flow pending -> confirmed -> completed (or cancelled); a details view shows who created it and what it can move to. Confirmed and completed pre-orders count in K3 (as a floor, see ML_PLAN B1).
- Editing a pre-order after the plan is confirmed prompts to refresh the plan.

### K11 Kitchen stock request (P2), FR9
*Covers: Kitchen Stock Requests.*
- Manager requests ingredient quantities from inventory; status is visible: pending, approved, issued, rejected.
- A rejected request shows the inventory manager's reason.

### K12 Shortage reporting (P2), FR7
*Covers: Shortage Reporting.*
- Manager reports a shortage of an ingredient (manual, e.g. found less than the system says). This creates a high-priority alert for the Inventory & Procurement Manager.
- Automatic shortage flags from K9 also appear in the inventory dashboard.

### K13 Food availability (P2), FR5
*Covers: Food Availability Management.*
- Manager marks a menu item available or unavailable for the day.
- (P3) The system suggests "unavailable" when ingredient stock cannot cover one batch.

### K14 Actual food usage (added 9 Oct 2026), FR8
*Covers: Actual Food Usage Recording.*
- Manager records prepared portions used other than sold or wasted: staff meals, complimentary portions, tasting
  samples, other. One figure per item, day and type; recording again replaces it; it can be cleared.
- A daily balance per item shows prepared = served + wasted + other use + unaccounted; unaccounted appears once the
  served figure is recorded, and a negative value (more used than prepared) is saved with a warning and flagged.
- Other use never changes sales (the measure of demand that trains the forecast), stock or the forecast.
- The administrator sees other use by type and item in Monitoring > Waste, with CSV. Tests USE-1 to USE-6.

---

## 5. Inventory & Procurement Manager stories

### I1 Inventory dashboard (P1), FR10
*Covers: Inventory Dashboard.*
- Shows current stock status counts (low and out, with the OK count), low-stock and reorder alerts, the ingredients whose next-7-day need is above usable stock (the full need-vs-stock list is on Ingredient demand, I7), top reorder recommendations, expiring-soon batches and pending kitchen requests. *(Simplified 11 Oct 2026: only at-risk ingredients are drawn on the dashboard.)*

### I2 Ingredient management (P1), FR9
*Covers: Ingredient Management.*
- Create, edit, deactivate ingredients (name, unit, category, shelf life days, default supplier, min stock, reorder level, reorder quantity).
- Name unique; unit is fixed after the first stock movement (avoids corrupting history).

### I3 Stock level monitoring (P1), FR9
*Covers: Stock Management, Stock Level Monitoring.*
- List of every ingredient with current quantity (sum of batch remaining), status colour and last movement date.
- Current quantity always equals the sum of all movements (verified by test).

### I4 Minimum and reorder levels (P1), FR7
*Covers: Minimum Stock Level Management, Reorder Level Management.*
- Manager sets min stock and reorder level per ingredient. Reorder level must be >= min stock.
- Changes apply to the next alert run.

### I5 Stock-in recording (P1), FR9
*Covers: Stock-In Recording.*
- Records ingredient, quantity, supplier (optional), unit cost, batch number and expiry date (optional), and date received. This creates a batch and a `stock_in` movement.
- Quantity > 0; expiry cannot precede received date.

### I6 Stock-out recording (P1), FR9
*Covers: Stock-Out Recording.*
- Records ingredient, quantity, reason (issued to kitchen, other) and date, and deducts stock from the batch with the earliest expiry first (FEFO).
- A stock-out that exceeds available stock is rejected; stock never goes negative.

### I7 Ingredient demand forecast (P1), FR6, FR7
*Covers: Ingredient Demand Forecast.*
- For each ingredient, next-7-day requirement = sum over items of forecast x recipe quantity, shown against current stock and days of cover.
- Ingredients used by items with no recipe are listed as "unknown".

### I8 Low-stock and reorder alerts (P1), FR7, FR10
*Covers: Low-Stock Alerts.*
- An alert is raised when stock <= reorder level (warning) or <= min stock (critical), or when projected stock over the next N days would fall below zero.
- Alerts appear on the dashboard, can be acknowledged and are not duplicated while an identical one is open.

### I9 Reorder recommendations (P1), FR7
*Covers: Reorder Recommendations.*
- Suggested quantity = projected need over the lead time + safety stock - stock on hand - quantity on order, rounded up to pack size; never negative.
- Each row shows the numbers that produced it. The manager can create a PO from a recommendation (I11).

### I10 Supplier management (P2)
*Covers: Supplier Management.*
- Create, edit, deactivate suppliers (name, contact, lead time days, notes). Supplier details are internal records only; no external integration (out of scope).

### I11 Purchase orders (P2), FR9
*Covers: Purchase Order Management.*
- Manager creates a PO (supplier, lines, expected date), with status: draft, sent (manual), received, cancelled.
- Receiving a PO (in full or partly) creates stock-in movements/batches for the received quantities and updates "on order".
- No automatic ordering or supplier pricing integration (out of scope).

### I12 Expiry tracking (P2), FR9
*Covers: Expiry Tracking.*
- List of batches sorted by expiry date; batches within the warning window (A7) are highlighted and raise an alert.
- Expired batches with remaining quantity prompt a wastage record (I13).

### I13 Ingredient wastage recording (P1 as a movement type; P2 for reasons and reporting), FR9
*Covers: Inventory Wastage Recording.*
- Records ingredient, quantity, reason (expired, damaged, spoiled, other) and date; creates a `wastage` movement that reduces stock.
- Appears in the waste reports (A11).

### I14 Stock adjustments (P2), FR9
*Covers: Stock Adjustment Management.*
- Manager enters the counted quantity; the system posts a signed adjustment for the difference with a mandatory reason.
- The adjustment is immutable and visible in the movement history.

### I15 Kitchen stock request handling (P2), FR9
*Covers: Kitchen Stock Request Management.*
- Manager sees pending requests and can approve, reject (with reason), or issue in full or part.
- Issuing creates the stock-out movement (I6) linked to the request.

### I16 Inventory data validation (P2), NFR8
*Covers: Inventory Data Validation.*
- Real-time validation is delivered by C4 and the rules in I5/I6/I14 (no negative stock, no unit change, no future dates).
- A "consistency check" page lists ingredients whose stored quantity differs from the movement sum (P3).

---

## 6. System (service-level) stories

These describe behaviour of the forecasting, recommendation and alert services. They carry most of the ML acceptance criteria.

### S1 Generate and store forecasts (P1), FR4, FR11, NFR2, NFR6
- A forecast run produces 7 days of forecasts for every active item in **under 5 s** using the active saved model (no training at request time).
- Each stored forecast has: item, target date, predicted quantity, model version, generated-at time, and a snapshot of key inputs (holiday, weather, promo flags).
- Re-running for the same date creates a new version; the previous one is kept, not overwritten.
- **Accuracy criterion.** On a chronological hold-out set, the chosen model must beat the naive baseline (same weekday last week) on MAE. If it does not, the result is reported honestly and the baseline is used.
- MAE, RMSE, MAPE and R2 are reported per model (`ML_PLAN.md`).

### S2 Convert forecasts into preparation quantities (P1), FR5
- Implements the formula in K3. Given fixed inputs the output is deterministic, and unit tests cover buffer, rounding, pre-order floor and zero-forecast cases.

### S3 Ingredient requirements and shortage check (P1), FR6, FR7
- Requirement per ingredient = sum over items of (recommended or forecast quantity x recipe quantity).
- Shortage = requirement > available stock (usable, non-expired batches only).
- Results equal hand calculation on a documented sample (`TESTING.md`).

### S4 Alert generation (P1), FR7, FR10
- Alert types: low stock, critical stock, projected stock-out, expiry warning, over-preparation risk (waste risk), forecast run failed.
- Alerts are created by a scheduled or manual run, de-duplicated, and closed automatically when the condition clears.

### S5 Handle missing or incomplete data (P1), NFR3
- Missing weather: use the seasonal average and mark the forecast "weather estimated".
- Missing holiday or promo data: treated as "no event" and flagged.
- Fewer than N days of history for an item: no ML forecast; the UI says so and shows the baseline (or nothing) instead of a wrong number.
- Any failure returns a readable message, never a stack trace or a blank page.

### S6 Store outcomes for evaluation (P1), FR11
- Each day's actual sold, prepared and wasted quantities are stored next to the forecast and recommendation for the same item and date, so forecast error and waste-vs-recommendation can be computed later.

---

## 7. Non-functional requirements (made measurable)

| ID | Requirement | Measurable criterion | Verified by |
|---|---|---|---|
| NFR1 | Usability for non-technical staff | A first-time user completes the 3 core tasks for their role (e.g. kitchen: view recommendation, record prepared, record waste) without help in <= 5 minutes; SUS >= 68 from pilot users | UAT |
| NFR2 | Performance | Forecast run < 5 s for 7 days x all items; dashboard pages < 3 s with seed data; API p95 < 1 s for read endpoints | Timing tests |
| NFR3 | Reliability | Missing/invalid data never yields a 500 or blank page; behaviours in S5 pass | Negative tests |
| NFR4 | Accessibility (browsers, desktop and mobile) | Works on current Chrome, Firefox, Edge; layouts usable at 360 px width; no horizontal scroll | Manual + responsive checks |
| NFR5 | Security | Hashed passwords, server-side RBAC on every route, CSRF protection, escaped output, parameterised queries, no secrets in the repo | Route x role test, review |
| NFR6 | Maintainability | ML code lives behind one service class; model versions recorded; retrain via one documented command | Code review |
| NFR7 | Scalability (multi-outlet) | Every operational table has `outlet_id`; no code assumes exactly one outlet | Schema review |
| NFR8 | Data integrity | Rules in C4, I5, I6, I14 enforced in service layer and DB constraints; invalid rows rejected on import with reasons | Unit + import tests |

---

## 8. Traceability: functional requirements to stories

| FR | Requirement (short) | Stories |
|---|---|---|
| FR1 | Login with role-based access | C1, C2, C3, A2, A3 |
| FR2 | Import/enter historical sales | A14, K6, A4 |
| FR3 | Record/import contextual data | A15 |
| FR4 | Item-level demand forecast | S1, K2, A9, A16 |
| FR5 | Forecast to preparation quantity | S2, K3, K4, K10, K13 |
| FR6 | Ingredient requirements from forecast and recipes | S3, K9, I7, A5, A10 |
| FR7 | Compare requirement to stock, flag shortages | S3, S4, I4, I8, I9, K12, A7 |
| FR8 | Record actual sales, preparation, waste | K5, K6, K7, K8 |
| FR9 | Record stock movements | I2, I3, I5, I6, I11, I12, I13, I14, I15, K11 |
| FR10 | Dashboard of forecasts, recommendations, alerts | A1, K1, I1, S4 |
| FR11 | Store forecasts and outcomes | S1, S6, A9 |
| FR12 | Basic operational reports | A8, A11, A12, A13 |

---

## Appendix A. Coverage of the proposal's 47 listed functions

**System Administrator (14):** System Dashboard A1 | User Account Management A2 | Role & Access Management A3 | Menu Management A4 | Recipe/BOM Management A5 | Restaurant Information Management A6 | System Settings & Alert Configuration A6, A7 | Sales & Revenue Monitoring A8 | Food Demand Forecast Monitoring A9 | Inventory Demand Forecast Monitoring A10 | Food Waste Monitoring A11 | Inventory Monitoring A10 | System Analytics A12 | System Reports A13

**Food Production Manager (15):** Kitchen Dashboard K1 | Daily Order Management K10 | Pre-Order Management K10 | Food Demand Forecast K2 | Preparation Recommendations K3 | Food Preparation Management K4 | Preparation Quantity Recording K5 | Ingredient Requirements K9 | Ingredient Usage Recording K8 | Actual Food Usage Recording K14 | Sales/Served Quantity Recording K6 | Food Waste Recording K7 | Kitchen Stock Requests K11 | Food Availability Management K13 | Shortage Reporting K12

**Inventory & Procurement Manager (18):** Inventory Dashboard I1 | Ingredient Management I2 | Stock Management I3 | Stock-In Recording I5 | Stock-Out Recording I6 | Stock Level Monitoring I3 | Minimum Stock Level Management I4 | Reorder Level Management I4 | Ingredient Demand Forecast I7 | Low-Stock Alerts I8 | Reorder Recommendations I9 | Supplier Management I10 | Purchase Order Management I11 | Expiry Tracking I12 | Inventory Wastage Recording I13 | Stock Adjustment Management I14 | Kitchen Stock Request Management I15 | Inventory Data Validation I16

## Appendix B. Story count by priority

| Priority | Common | Admin | Kitchen | Inventory | System | Total |
|---|---|---|---|---|---|---|
| P1 | C1, C2, C4 | A1, A2, A4, A5, A8, A9, A11, A14, A15, A16 | K1, K2, K3, K5, K6, K7, K9 | I1, I2, I3, I4, I5, I6, I7, I8, I9, I13 | S1-S6 | 36 |
| P2 | C3 | A3, A6, A7, A10, A12, A13 | K4, K10, K11, K12, K13 | I10, I11, I12, I14, I15, I16 | none | 18 |
| P3 | C5 | none | K8 | none | none | 2 |

P1 alone is too much for one builder in the time left. **the project plan replaces P1/P2/P3 with scheduling tiers** (M1 core loop 26 stories, M2 12, S stretch 11, X postponed 7) and gives the final MVP scope, the cut list and the trim ladder.

## Appendix C. Questions and answers

| # | Question | Answer |
|---|---|---|
| 1 | Is 28 Sep final, and when did the clock start? | Started Sep Week 1; deadline 28 Sep 2026 (A1) |
| 2 | Real data or synthetic? | Synthetic (A3) |
| 3 | Weather/holiday location | Colombo (A3) |
| 4 | Forecast horizon | 7 days (A5) |
| 5 | Deployment (Docker, VPS) | Defaults accepted: Ubuntu, Docker Compose optional, local venv for dev |
| 6 | ORM and auth | Defaults accepted: Flask-SQLAlchemy, Flask-Migrate, Flask-Login sessions with CSRF |
| 7 | UI | Vue.js (A13) |
| 8 | Scope and team | One builder; scope defaults stand, cuts set in the project plan |

Still open: who plays each role during the UAT walkthrough (I10), and whether the examiners expect pilot-restaurant UAT despite the synthetic data.
