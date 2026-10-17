# SmartRestaurant: API

Read `ARCHITECTURE.md` (envelope, RBAC, MVC rules) and `DATABASE.md` (fields) first. This is the contract between the Vue pages and the Flask controllers. Tier labels are defined in the project plan: M1 core, M2 rest of MVP, S stretch.

## 1. Conventions

| Topic | Rule |
|---|---|
| Base | `/api/v1`. Same Flask app and session as the HTML pages (ARCH D2). |
| Auth | Session cookie from the `/login` form. No tokens. |
| CSRF | Every `POST`, `PUT`, `PATCH` needs header `X-CSRFToken` (value from `<meta name="csrf-token">`; `static/js/api.js` adds it). Missing or wrong gives `400 csrf_failed`. |
| Format | JSON in and out, UTF-8. File upload endpoints take `multipart/form-data`. |
| Dates | `YYYY-MM-DD` (Colombo business date). Timestamps are ISO-8601 UTC with `Z`. |
| Numbers | Quantities and money are JSON numbers (decimals converted at the DTO boundary; money has 2 decimals). |
| Envelope | Success `{"data": ..., "meta": {...}}`. List meta: `{"total": n, "limit": n, "offset": n}`. Error `{"error": {"code", "message", "fields"?}}`. |
| Paging | Lists take `limit` (default 50, max 200) and `offset`. Small lookups (menu, ingredients) return everything. |
| Filters | `from`, `to` (inclusive dates), `item_id`, `ingredient_id`, `status` as listed per endpoint. Unknown filters are ignored. |
| Idempotency | `POST` creates are not idempotent, except imports (re-import creates no duplicates) and decisions (upsert per item and date). |
| Request id | Every response carries `X-Request-ID`, also written to the log. |
| Outlet | Never sent by the client. The server uses `current_outlet_id()`. |

### Status codes

| Code | `error.code` | Meaning |
|---|---|---|
| 200 / 201 | | OK / created |
| 400 | `bad_request`, `csrf_failed` | Malformed JSON, missing CSRF |
| 401 | `unauthenticated` | Not logged in (pages redirect to `/login`) |
| 403 | `forbidden` | Logged in, wrong role |
| 404 | `not_found` | Unknown id, or an id from another outlet |
| 409 | `duplicate_record`, `conflict` | Unique rule broken, or state conflict. Duplicates can be resent with `"confirm_overwrite": true` where noted |
| 422 | `validation_error` | Rule broken; `fields` maps field name to message |
| 500 | `server_error` | Logged, generic message, never a stack trace |

```json
{"error": {"code": "validation_error", "message": "Please fix the highlighted fields.",
           "fields": {"quantity": "must be greater than 0"}}}
```

**Input limits (NFR8, `services/validation.py`).** Values outside these give 422, never a 500 or a stored value:

| Kind | Rule |
|---|---|
| Portions (prepared, served, waste, pre-orders, daily orders, override `final_qty`, imported sales) | whole number, at most 10,000 per entry |
| Ingredient quantities (stock in/out, wastage, adjustment, PO and request lines, usage, min stock, reorder level, pack size, reorder quantity) | at most 1,000,000 base units, at most 3 decimal places |
| Prices and unit costs | 0 to 10,000,000 LKR, at most 2 decimal places |
| Recipe quantity per portion | greater than 0, at most 100, at most 4 decimal places |
| Ids and other whole numbers; integer query parameters | at most 2,147,483,647 (query parameter beyond that: `is out of range`) |
| Text fields | must be text (an object, list or true/false is refused) |
| Sales import | a row more than 10 times the item's highest stored day is rejected; an item with no stored history is compared with the median of its own rows in the file (7 rows or more) |
| Users | username letters, digits, `.`, `-`, `_`; email must look like an address; password text of 8 to 128 characters; `is_active` true or false |
| Forecast date range (`GET /forecasts`) | `to` not before `from`, at most 62 days inclusive (`to`: `range is too long (max 62 days)`) |

## 2. Roles and access

Abbreviations: **A** admin, **K** kitchen, **I** inventory. **(R)** means read-only (GET only).

- Writes to kitchen records are **K only**; writes to inventory records are **I only**. Admin owns master data (users, menu, recipes, context, models) and can **read** kitchen and inventory data for monitoring.
- Pages are stricter than the API (each role sees only its own pages, A9 in ARCH). The read-only endpoints marked (R) exist so the admin dashboard and monitors can reuse the same services.
- A missing role decorator is a failing test (`tests/api/test_rbac.py`).

## 3. Endpoints

### 3.1 Session and users

| Method and path | Roles | Tier | Story | Notes |
|---|---|---|---|---|
| `GET /me` | A K I | M1 | C1 | `{id, username, full_name, role, home_url}` |
| `GET /users` | A | M2 | A2 | |
| `POST /users` | A | M2 | A2 | `{full_name, username, email, role, password}`; 409 on duplicate username |
| `PATCH /users/{id}` | A | M2 | A2, A3 | `full_name, email, role, is_active`. 422 `last_admin` if it would remove the last active admin. Role change is audited. |
| `POST /users/{id}/password` | A | S | A2 | reset |

`/login` (form POST, rate-limited by lockout per username and address) and `/logout` (POST, ends the session on the server) are page routes, not API. Uploads larger than 5 MB give 413 `too_large`. In CSV downloads a text cell starting with `=`, `+`, `-`, `@` is prefixed with `'` so a spreadsheet does not run it.

### 3.2 Catalog, ingredients, stock

| Method and path | Roles | Tier | Story | Notes |
|---|---|---|---|---|
| `GET /menu-items?active=` | A K I | M1 | A4 | |
| `POST /menu-items` | A | M2 | A4 | `name, category, price, portion_unit, shelf_life_hours, batch_size` |
| `PATCH /menu-items/{id}` | A | M2 | A4 | includes `is_active` |
| `PATCH /menu-items/{id}/availability` | K | S | K13 | `{is_available}` |
| `GET /menu-items/{id}/recipe` | A K I | M1 | A5 | lines plus computed "has recipe" |
| `PUT /menu-items/{id}/recipe` | A | M2 | A5 | `{lines: [{ingredient_id, quantity_per_portion}]}` replaces all lines atomically |
| `GET /ingredients?active=` | A K I | M1 | I2 | master data, no stock |
| `POST /ingredients` | I | M1 | I2 | 422 if `reorder_level < min_stock` |
| `PATCH /ingredients/{id}` | I | M1 | I2, I4 | `unit` rejected once movements exist |
| `GET /stock/levels` | A(R) K(R) I | M1 | I3 | per ingredient: `on_hand`, `usable`, `expired` (on hand minus usable: expired stock awaiting a wastage record), `status` (`ok`/`low`/`out`), `is_critical`, `last_movement_date` |
| `GET /stock/batches?ingredient_id=&expiring_within_days=` | A(R) I | M1 | I12 | sorted by expiry |
| `GET /stock/movements?ingredient_id=&type=&from=&to=` | A(R) I | M1 | I3 | paged |
| `GET /stock/consistency` | A(R) I | S | I16 | read-only data check: `mismatches` (sum of movements differs from batch stock), `batches_over_received`, `expired_with_stock`, and `consistent`; also `flask smartrest check-stock` |
| `POST /stock/in` | I | M1 | I5 | `{ingredient_id, quantity, received_date, expiry_date?, batch_no?, unit_cost?, supplier_id?}` |
| `POST /stock/out` | I | M1 | I6 | `{ingredient_id, quantity, movement_date, reason}`; 422 `insufficient_stock` with `available` |
| `POST /stock/wastage` | I | M1 | I13 | `{ingredient_id, quantity, movement_date, reason, batch_id?}` |
| `POST /stock/adjustments` | I | S | I14 | `{ingredient_id, counted_quantity, movement_date?, note}`; `note` required. Posts `counted - on_hand` (on hand includes expired stock): a shortfall is drawn from the earliest-expiry batches first, a surplus becomes batch `ADJ-<date>` with no expiry. 422 when the difference is 0. Returns `on_hand_before`, `counted`, `difference`, `usable`. |
| `GET /stock-requests?status=&detail=` | A I | S | I15 | kitchen requests, open ones first; `meta.pending` is the pending count; each request has `overdue` (pending or approved, and needed before today; also on the kitchen's list) |
| `GET /stock-requests/{id}` | A I | S | I15 | lines with requested, issued, outstanding and current usable stock |
| `POST /stock-requests/{id}/approve` | I | S | I15 | pending to approved |
| `POST /stock-requests/{id}/reject` | I | S | I15 | `{reason}` required; pending only |
| `POST /stock-requests/{id}/issue` | I | S | I15 | `{lines: [{line_id, quantity}], close?}`; from pending or approved; all lines are checked against usable stock first (422 `insufficient_stock`, nothing saved); draws FEFO with reason `issued_to_kitchen`, `reference_type = stock_request`; status `issued` when every line is complete or `close` is true, else `approved` |
| `GET /suppliers?active=` | A I | M1 | I10 | `active=true` lists only active suppliers |
| `POST /suppliers` | I | S | I10 | `name, contact_person?, phone?, email?, lead_time_days?, notes?`; name unique |
| `PATCH /suppliers/{id}` | I | S | I10 | any of the above plus `is_active`; an inactive supplier cannot be chosen for new ingredients or purchase orders, existing links stay |
| `GET /purchase-orders?status=` | A I | S | I11 | list, newest first |
| `GET /purchase-orders/{id}` | A I | S | I11 | header and lines (`qty_ordered`, `qty_received`, `qty_outstanding`) |
| `POST /purchase-orders` | I | S | I11 | `{supplier_id, expected_date?, notes?, lines: [{ingredient_id, qty_ordered, unit_cost?}]}`; status `draft`; number `PO-YYYYMMDD-NN`; an inactive supplier or ingredient is rejected. The body can be built from reorder rows |
| `POST /purchase-orders/{id}/send` | I | S | I11 | draft to sent, marked by hand; nothing is transmitted to the supplier |
| `POST /purchase-orders/{id}/receive` | I | S | I11 | `{received_date?, lines: [{line_id, quantity, expiry_date?, batch_no?, unit_cost?}]}`; creates a batch and a `stock_in` movement per line (linked to the order); a line cannot receive more than is outstanding (422, nothing saved); allowed from draft, sent or partially received; the status becomes partially received or received |
| `POST /purchase-orders/{id}/cancel` | I | S | I11 | draft or sent with nothing received, else 409 |

### 3.3 Sales, context, forecasting, models

| Method and path | Roles | Tier | Story | Notes |
|---|---|---|---|---|
| `POST /sales/import` | A | M1 | A14 | multipart `file`, form fields `dry_run` (default `true`), `on_conflict` = `skip`\|`overwrite` (default `skip`). Same call with `dry_run=false` commits (the file is re-sent; no server-side staging). |
| `POST /sales/served` | K | M1 | K6 | `{date, lines: [{menu_item_id, quantity}], confirm_overwrite?}`; writes `sales_records` with source `kitchen` |
| `GET /promotions`, `POST /promotions`, `PATCH /promotions/{id}` | A | M2 | A15 | `PATCH` can set `is_active` |
| `GET /holidays`, `POST /holidays/import` | A | M2 | A15 | CSV, same dry-run contract as sales import |
| `GET /weather?from=&to=`, `POST /weather/import` | A | M2 | A15 | CSV, same dry-run contract |
| `GET /forecasts?from=&to=&item_id=` | A K I | M1 | K2, S1 | latest version per item and date. `meta` has `active_model`, `last_run`, `missing_dates` when a date has no forecast, `holiday_calendar_ends` and `beyond_holiday_calendar` (the range goes past the last imported holiday, so later holidays are unknown to the forecast). |
| `GET /forecasts/accuracy?from=&to=&item_id=&format=csv` | A | M2 | A9 | per item and overall MAE, WAPE, MAPE, bias, plus a daily forecast-vs-actual series (rule in DATABASE 2.6) |
| `GET /forecast-runs?limit=` | A | M1 | A9, S1 | includes failed/skipped with `reason`; `limit` 1 to 200 |
| `POST /forecast-runs` | A | M1 | S1 | `{as_of?, horizon_days?}` (defaults: today, 7; `horizon_days` 1 to 14, checked before a run is recorded; `as_of` cannot be in the past, because the shipped model has seen those days: use the backfill). Synchronous, target under 5 s. |
| `GET /model-versions` | A | M1 | A16 | with metrics summary and active flag |
| `POST /model-versions` | A | M1 | A16 | trains synchronously (seconds to about a minute) and returns the comparison table. Not activated. |
| `POST /model-versions/{id}/activate` | A | M1 | A16 | audited; previous version stays available |

### 3.4 Recommendations and kitchen

| Method and path | Roles | Tier | Story | Notes |
|---|---|---|---|---|
| `GET /recommendations/prep?date=` | A(R) K | M1 | K3, S2 | one row per active item, computed live |
| `POST /recommendations/prep/decisions` | K | M1 | K3 | `{menu_item_id, date, action: "accept"\|"override", final_qty?, reason?}`; `override` needs `final_qty` and `reason`. A decision sets `prep_status` to `planned`; once preparation has started the change is saved with a warning; once it is `done` the plan cannot change (409 `prep_done`) until it is reopened |
| `POST /recommendations/prep/status` | K | M2 (added 9 Oct 2026) | K4 | `{menu_item_id, date, action: "start"\|"done"\|"reopen"}`. Preparation workflow: `planned` -> `in_progress` -> `done`; `reopen` goes back from `done` to `in_progress`. Needs a decision for that item and date (422 `no_plan`); the date cannot be in the future; `done` needs a prepared quantity above 0 and returns `warnings` when prepared differs from the plan; any other transition is 409 `invalid_transition`. Recording the first prepared quantity starts preparation automatically |
| `GET /recommendations/requirements?date=` | A(R) K I | M1 | K9, S3 | requirements and shortage flags for that day's plan |
| `GET /recommendations/ingredient-forecast?from=&days=7` | A(R) I | M1 | I7 | per ingredient per day; `days` 1 to 31; `items_without_forecast` names menu items with no forecast on some days (their demand is missing) |
| `GET /recommendations/reorder` | A(R) I | M1 | I9 | rows with the numbers behind each suggestion; `meta.items_without_forecast` names menu items with no forecast on some of the 7 days, whose demand is therefore missing from the quantities; `meta.covered_by_orders` lists ingredients that are needed (need over lead time + safety stock above usable) but not suggested because open purchase orders cover them, with those `orders [{id, status, qty}]` (a draft counts as on order but has not been sent) |
| `POST /kitchen/prepared` | K | M1 | K5 | `{menu_item_id, date, quantity}`; returns the new running total |
| `DELETE /kitchen/prepared/<id>` | K | M1 | K5 | undo a mistaken entry: only the latest entry of an item, today, while the item is not finished (409 `not_today`, `not_latest`, `prep_done`); returns `{menu_item_id, date, removed, total_prepared}`; the removed entry is kept in the audit log (`prepared.undo`). The prep plan's `last_entry` (`entry_id, quantity, prepared_at`) names the entry it would remove |
| `POST /kitchen/waste` | K | M1 | K7 | `{menu_item_id, date, quantity, reason, note?}`; 200 with `warnings` when waste exceeds prepared |
| `GET /kitchen/daily-summary?date=` | A(R) K | M1 | K1, K5-K7, S6 | per item: forecast, recommended, final, `prep_status`, prepared, served, wasted, `other_use` (food usage total), `unaccounted` (prepared minus served, wasted and other use; `null` until served is recorded) |
| `GET /kitchen/pre-orders?from=&to=&status=&menu_item_id=` | A(R) K | S | K10 | `from` defaults to today; ordered by date and pickup time; each row has `customer_name, customer_contact, pickup_time (HH:MM), created_at, completed_at, counts_in_plan` |
| `GET /kitchen/pre-orders/{id}` | A(R) K | S | K10 | one pre-order plus `created_by` (name), `updated_at` and `allowed_status` (the statuses it can move to next); 404 if unknown (added 13 Oct 2026) |
| `POST /kitchen/pre-orders` | K | S | K10 | `{menu_item_id, target_date, quantity, customer_name, pickup_time, customer_contact?, customer_note?, status?}` (name and pickup time required since 13 Oct 2026); `status` is `pending` (default) or `confirmed`; date cannot be in the past; `meta.warnings` when a decision already exists for that item and date |
| `PATCH /kitchen/pre-orders/{id}` | K | S | K10 | any of `quantity, target_date, pickup_time, customer_name, customer_contact, customer_note, status`. Status flow: pending -> confirmed or cancelled; confirmed -> pending, completed or cancelled; completed and cancelled are final (409, `invalid_transition` for a disallowed move). `completed` only on or after the pre-order date (422). A past-dated pre-order can only be completed. Confirmed and completed pre-orders count in the recommendation for their day; completing one records no sale |
| `GET /kitchen/stock-requests?status=` | A(R) K | S | K11 | with lines and status; the reject reason is shown to the kitchen |
| `POST /kitchen/stock-requests` | K | S | K11 | `{needed_date?, note?, lines: [{ingredient_id, quantity}]}`; status `pending` |
| `POST /kitchen/stock-requests/{id}/cancel` | K | S | K11 | pending only, else 409 |
| `GET /kitchen/orders?date=&from=&to=&status=&menu_item_id=` | A(R) K | S | K10 | daily orders, newest first; `date` is shorthand for `from = to` |
| `POST /kitchen/orders` | K | S | K10 | `{menu_item_id, quantity, order_date?, customer_note?}`; date defaults to today and cannot be in the future (future days are pre-orders); status `open` |
| `PATCH /kitchen/orders/{id}` | K | S | K10 | any of `quantity, order_date, customer_note, status` (`open`, `fulfilled`, `cancelled`); only an open order can change (409 otherwise). Internal record only: no prices, no payment, no effect on forecasts |
| `GET /kitchen/ingredient-usage?date=` | A(R) K | S | K8 | per ingredient: `expected` (prepared x recipe), `recorded` (or null), `variance`, `note`; `items_without_recipe` lists prepared items with no recipe |
| `POST /kitchen/ingredient-usage` | K | S | K8 | `{date?, ingredient_id, quantity >= 0, note?}`; one recorded figure per ingredient and day, recording again replaces it (200, first time 201); never changes stock |
| `DELETE /kitchen/ingredient-usage/{id}` | K | S | K8 | removes a recorded figure |
| `GET /kitchen/food-usage?date=` | A(R) K | M2 (added 9 Oct 2026) | K14 | Actual Food Usage: `entries` (one per item and usage type) and `balance` per item: `prepared`, `served`, `wasted`, `other_use` by type, `unaccounted` and `flags` (`used_more_than_prepared`) |
| `POST /kitchen/food-usage` | K | M2 (added 9 Oct 2026) | K14 | `{date?, menu_item_id, usage_type: "staff_meal"\|"complimentary"\|"sample"\|"other", quantity > 0, note?}`; one figure per item, date and type, recording again replaces it (200, first time 201); the date cannot be in the future; `meta.warnings` when served, waste and other use together exceed prepared. Never changes sales, stock or the forecast |
| `DELETE /kitchen/food-usage/{id}` | K | M2 (added 9 Oct 2026) | K14 | removes a recorded figure |
| `POST /kitchen/shortage-reports` | K | S | K12 | `{ingredient_id, note?}` creates a critical `manual_shortage` alert visible to Admin and Inventory (201); a second report for the same ingredient updates the open alert (200). The alert closes itself (`closed_reason = restocked`) when that ingredient later gets a positive stock movement |

### 3.5 Alerts, dashboards, reports

| Method and path | Roles | Tier | Story | Notes |
|---|---|---|---|---|
| `GET /alerts?status=open&type=&refresh=` | A K I | M1 | I8, S4 | filtered by role (section 6). Evaluates first if the last evaluation is over 60 s old, or when `refresh=true`. For a role that sees both, an ingredient's stock alert and its projected stockout are one row (the stock alert, with the shortfall in its message and `merged_ids`). `meta.counts` = `critical`, `warning`, `info`, `total` over every unresolved alert, acknowledged or not (the bell, the badges and the list all show `total`), and `new` = not yet acknowledged (since 17 Oct 2026). |
| `POST /alerts/{id}/acknowledge` | A K I | M1 | I8 | only for alerts the role can see; a stock alert also acknowledges the projected stockout shown in its row. An acknowledged alert stays listed and counted until its cause is fixed |
| `POST /alerts/run` | A | M1 | S4 | manual run, returns counts opened/closed |
| `GET /dashboards/admin?range=7\|30` | A | M2 | A1 | Period = the last 7 or 30 days ending yesterday. Besides the totals: `waste_rate {prepared, wasted, pct}` (pct = wasted / prepared x 100, null if nothing prepared), `waste_threshold_pct`, `coverage {days, days_with_sales, latest_sales_date}`, `forecast_next7` (7 rows `{date, qty, items}`; qty null = no forecast), `menu_items_active`, `stock {ingredients, out, low, rows}` (out first, then by usable / reorder level), `inventory_alerts` (one row per ingredient with an open stock, forecast-shortfall or expiry alert, or not ok: `status`, `usable`, `forecast {date, short_by}`, `expiry [{batch_no, qty, date, expired}]`, `severity`, `alert_ids`), `pre_orders` (confirmed, next 7 days: `rows`, `count`, `portions`, `by_item`), `recent_activity` (latest 10 stored events: `{time, kind, action, name, user, detail}`). `forecast_next7_total` is the sum of the 7 `forecast_next7` values. Opening it runs the alert check like `GET /alerts`. |
| `GET /dashboards/kitchen?date=` | K, A(R) | M1 | K1 | |
| `GET /dashboards/inventory` | I, A(R) | M1 | I1 | `requirements`: one row per ingredient that runs short over the next 7 days or needs ordering, most short first: `need` (7 days), `usable`, `covered_pct`, `why` (`short`, `below_minimum`, `on_order`), `suggestion {qty, supplier, supplier_id, lead_time_days}` or null, `on_order` and `orders [{id, status, qty}]`; `totals.requirements` is the full count; `expiring`: up to 10 usable batches that expire within 3 days (batches already expired are counted in `totals.expired_batches`, not listed) |
| `GET /reports/sales?from=&to=&group_by=day\|week\|month&item_id=` | A | M2 | A8 | rows plus totals plus top/bottom items |
| `GET /reports/waste?from=&to=&group_by=` | A | M2 | A11 | `food` and `ingredient` returned as two separate sections (assumption A6 in REQUIREMENTS); since 13 Oct 2026 `food.by_item` gives per menu item `planned` (decided plans only, else null), `prepared`, `sold`, `wasted`, `waste_pct` (wasted / prepared x 100), `days_prepared` and a `suggestion` when the rate is above the waste-risk limit (advice only; no forecast or plan is changed) |
| `GET /reports/stock-levels` | A | S (built 21 Sep) | A10, A13 | snapshot of every ingredient today (same rows as `/stock/levels`); `format=csv` |
| `GET /reports/inventory-trend?ingredient_id=&from=&to=` | A | S (built 21 Sep) | A13 | one ingredient day by day rebuilt from the movements: `opening`, per-day signed `stock_in`, `stock_out`, `wastage`, `adjustment`, and `closing`; the last closing equals on-hand stock; `format=csv` |
| `GET /reports/movements?from=&to=&ingredient_id=&type=` | A | S (built 21 Sep) | A13 | movements in a period, newest first; JSON shows at most 500 rows (`meta.total` is the full count), `format=csv` exports all |
| `GET /reports/analytics?from=&to=` | A | S (built 21 Sep) | A12 | plain averages and ratios of recorded data: `weekday` (average portions per day by weekday), `calendar` (public, Poya, school holiday and ordinary days), `promotion` (promotion running or not), `forecast_error` (per day MAE and WAPE), `waste` (per day prepared, wasted, rate); default range is the last 90 days; day groups describe the data and do not prove cause |
| `GET /reports/sales` and `/reports/waste` with `format=csv` | A | S (built) | A13 | the CSV is built from the same service rows as the JSON |
| `GET /reports/food-usage?from=&to=` | A | M2 (added 9 Oct 2026) | A11, K14 | other food use (staff meals, complimentary, samples, other) per type and per item in the period, with totals; `format=csv` |
| `GET /restaurant`, `PUT /restaurant` | A | S (built 21 Sep) | A6 | `{name, address?, contact?, opening_days?, opening_hours?}`; `name` required; `timezone` is returned but cannot be changed |
| `GET /settings`, `PUT /settings` | A | S (built) | A6, A7 | thresholds, data-source banner, alert type switches |
| `GET /reports/stock-movements` | A | S (not built) | A13 | use `GET /stock/movements` |

Reports and pages call the same service method, so a chart, its table and its CSV always agree (A8, A13).

## 4. Key payloads

### 4.1 Prep plan: `GET /recommendations/prep?date=2026-09-25`

```json
{"data": {
  "date": "2026-09-25", "buffer_pct": 10, "model": "v20260922-1 (xgboost)",
  "items": [{
    "menu_item_id": 1, "name": "Chicken Burger", "batch_size": 6, "is_available": true,
    "forecast_qty": 47.3, "forecast_method": "model", "weather_estimated": true,
    "preorder_qty": 0, "recommended_qty": 54,
    "status": "suggested", "final_qty": null, "override_reason": null,
    "prepared_so_far": 0, "served_so_far": 0, "prep_status": null
  }]},
 "meta": {"generated_at": "2026-09-25T02:10:00Z"}}
```

`status` is `suggested`, `accepted`, `overridden` or `no_forecast` (then `recommended_qty` is `null` and `forecast_qty` is `null`; the UI shows "No forecast yet"). When a decision exists, its `final_qty` is returned next to the *current* `recommended_qty`, so the UI can show if the forecast has since moved. `prep_status` is `null` without a decision, otherwise `planned`, `in_progress` or `done`.

### 4.2 Requirements: `GET /recommendations/requirements?date=2026-09-25`

```json
{"data": {
  "date": "2026-09-25",
  "ingredients": [
    {"ingredient_id": 1, "name": "Chicken", "unit": "kg", "required": 15.48,
     "usable_stock": 12.0, "status": "short", "short_by": 3.48}],
  "cannot_compute": [{"menu_item_id": 9, "name": "Iced Milo", "reason": "no_recipe"}],
  "basis": {"1": "final_qty", "4": "recommended_qty"}}}
```

`basis` says per menu item whether the accepted `final_qty` or the computed `recommended_qty` was used (rule B2).

### 4.3 Import result (dry run and commit share the shape)

```json
{"data": {"dry_run": true, "accepted": 118, "rejected": 2, "skipped_unchanged": 0,
  "errors": [{"row": 14, "field": "item", "message": "Unknown menu item 'Chiken Burger'"},
             {"row": 40, "field": "quantity", "message": "must be a number >= 0"}]}}
```

Rows are validated first; a commit saves the accepted rows and reports the same errors. An identical existing row counts as `skipped_unchanged`; a differing one is a `conflict` error unless `on_conflict=overwrite`. Unknown item names are reported, never created (A14).

### 4.4 Alerts: `GET /alerts?status=open`

```json
{"data": [{"id": 7, "alert_type": "projected_stockout", "severity": "critical",
  "entity_type": "ingredient", "entity_id": 1, "target_date": "2026-09-25",
  "message": "Chicken will run short on 2026-09-25 (short by 3.48 kg)",
  "status": "open", "created_at": "2026-09-25T02:11:00Z"}],
 "meta": {"total": 1, "counts": {"critical": 1, "warning": 0, "info": 0}}}
```

### 4.5 Reorder: `GET /recommendations/reorder`

```json
{"data": [{"ingredient_id": 1, "name": "Chicken", "unit": "kg", "supplier": "Ceylon Poultry",
  "lead_time_days": 2, "need_over_lead_time": 29.5, "safety_stock": 5.0, "usable_stock": 12.0,
  "on_order": 0, "raw_qty": 22.5, "pack_size": 5, "min_order_qty": 10, "suggested_qty": 25}]}
```

Ingredients whose result is 0 are omitted.

### 4.6 Train: `POST /model-versions`

```json
{"data": {"version_id": 4, "version_label": "v20260922-1", "algorithm": "xgboost",
  "beats_baseline": true, "selection_reason": "lowest hold-out MAE",
  "holdout": {"start": "2026-07-27", "end": "2026-09-20", "days": 56},
  "comparison": [{"model": "naive_lag7", "mae": 9.8, "rmse": 13.1, "mape": 14.2, "wape": 12.9, "r2": 0.88, "bias": 0.4},
                 {"model": "xgboost", "mae": 6.1, "rmse": 8.3, "mape": 9.0, "wape": 8.1, "r2": 0.95, "bias": -0.2}]}}
```

(Numbers are placeholders.) Full `metrics` JSON shape: `ML_PLAN.md` section 6.

## 5. Page-to-API map

Each page's data calls are listed in the UI plan. Page routes (HTML) return the shell and never the numbers, except where a service result is embedded through `{{ data|tojson }}`.

## 6. Alert visibility (service constant)

| Alert type | Severity | Admin | Kitchen | Inventory |
|---|---|---|---|---|
| `low_stock` | warning | yes | no | yes |
| `critical_stock` | critical | yes | no | yes |
| `projected_stockout` | warning (critical when within 2 days) | yes | yes | yes |
| `expiry_warning` | warning (critical when already expired) | yes | no | yes |
| `waste_risk` | warning | yes | yes | no |
| `forecast_failed` | critical (failed), warning (skipped) | yes | no | no |
| `manual_shortage` (S) | critical | yes | no | yes |

## 7. CLI (same services, no HTTP)

| Command | Purpose |
|---|---|
| `flask smartrest seed [--reset]` | outlet, users, settings, catalog, suppliers, opening stock |
| `flask smartrest generate-data [--start --end --seed]` | synthetic history, loaded through the import services |
| `flask smartrest train [--activate]` | train, compare, save (`POST /model-versions`) |
| `flask smartrest activate <version_label>` | `POST /model-versions/{id}/activate` |
| `flask smartrest forecast [--as-of D] [--from D --to D]` | run forecast (`--as-of` today at the latest and not in the past); `--from/--to` is the backfill used for accuracy views, refused before the active model's hold-out start so every backfilled forecast is out-of-sample |
| `flask smartrest alerts` | evaluate alerts (`POST /alerts/run`) |
| `flask smartrest create-user` / `set-setting <key> <value>` | admin helpers, used until the S-tier pages exist |
