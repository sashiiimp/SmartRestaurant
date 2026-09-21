# SmartRestaurant: API

Read `ARCHITECTURE.md` (envelope, RBAC, MVC rules) and `DATABASE.md` (fields) first. This is the contract between the Vue pages and the Flask controllers. Tier labels are defined in `PLAN.md`: M1 core, M2 rest of MVP, S stretch.

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

`/login` (form POST, rate-limited by lockout) and `/logout` (POST) are page routes, not API.

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
| `GET /stock/levels` | A(R) K(R) I | M1 | I3 | per ingredient: `on_hand`, `usable`, `status` (`ok`/`low`/`out`), `is_critical`, `last_movement_date` |
| `GET /stock/batches?ingredient_id=&expiring_within_days=` | A(R) I | M1 | I12 | sorted by expiry |
| `GET /stock/movements?ingredient_id=&type=&from=&to=` | A(R) I | M1 | I3 | paged |
| `POST /stock/in` | I | M1 | I5 | `{ingredient_id, quantity, received_date, expiry_date?, batch_no?, unit_cost?, supplier_id?}` |
| `POST /stock/out` | I | M1 | I6 | `{ingredient_id, quantity, movement_date, reason}`; 422 `insufficient_stock` with `available` |
| `POST /stock/wastage` | I | M1 | I13 | `{ingredient_id, quantity, movement_date, reason, batch_id?}` |
| `POST /stock/adjustments` | I | S | I14 | `{ingredient_id, counted_quantity, movement_date, note}` |
| `GET/POST/PATCH /suppliers` | I | S | I10 | |
| `GET/POST /purchase-orders`, `POST /purchase-orders/{id}/send`, `/receive`, `/cancel` | I | S | I11 | `POST` body can be built from a reorder row |

### 3.3 Sales, context, forecasting, models

| Method and path | Roles | Tier | Story | Notes |
|---|---|---|---|---|
| `POST /sales/import` | A | M1 | A14 | multipart `file`, form fields `dry_run` (default `true`), `on_conflict` = `skip`\|`overwrite` (default `skip`). Same call with `dry_run=false` commits (the file is re-sent; no server-side staging). |
| `POST /sales/served` | K | M1 | K6 | `{date, lines: [{menu_item_id, quantity}], confirm_overwrite?}`; writes `sales_records` with source `kitchen` |
| `GET /promotions`, `POST /promotions`, `PATCH /promotions/{id}` | A | M2 | A15 | `PATCH` can set `is_active` |
| `GET /holidays`, `POST /holidays/import` | A | M2 | A15 | CSV, same dry-run contract as sales import |
| `GET /weather?from=&to=`, `POST /weather/import` | A | M2 | A15 | CSV, same dry-run contract |
| `GET /forecasts?from=&to=&item_id=` | A K I | M1 | K2, S1 | latest version per item and date. `meta` has `active_model`, `last_run`, and `missing_dates` when a date has no forecast. |
| `GET /forecasts/accuracy?from=&to=&item_id=` | A | M2 | A9 | per item and overall MAE, WAPE, MAPE, bias, plus a daily forecast-vs-actual series (rule in DATABASE 2.6) |
| `GET /forecast-runs?limit=` | A | M1 | A9, S1 | includes failed/skipped with `reason` |
| `POST /forecast-runs` | A | M1 | S1 | `{as_of?, horizon_days?}` (defaults: today, 7). Synchronous, target under 5 s. |
| `GET /model-versions` | A | M1 | A16 | with metrics summary and active flag |
| `POST /model-versions` | A | M1 | A16 | trains synchronously (seconds to about a minute) and returns the comparison table. Not activated. |
| `POST /model-versions/{id}/activate` | A | M1 | A16 | audited; previous version stays available |

### 3.4 Recommendations and kitchen

| Method and path | Roles | Tier | Story | Notes |
|---|---|---|---|---|
| `GET /recommendations/prep?date=` | A(R) K | M1 | K3, S2 | one row per active item, computed live |
| `POST /recommendations/prep/decisions` | K | M1 | K3 | `{menu_item_id, date, action: "accept"\|"override", final_qty?, reason?}`; `override` needs `final_qty` and `reason` |
| `GET /recommendations/requirements?date=` | A(R) K I | M1 | K9, S3 | requirements and shortage flags for that day's plan |
| `GET /recommendations/ingredient-forecast?from=&days=7` | A(R) I | M1 | I7 | per ingredient per day |
| `GET /recommendations/reorder` | A(R) I | M1 | I9 | rows with the numbers behind each suggestion |
| `POST /kitchen/prepared` | K | M1 | K5 | `{menu_item_id, date, quantity}`; returns the new running total |
| `POST /kitchen/waste` | K | M1 | K7 | `{menu_item_id, date, quantity, reason, note?}`; 200 with `warnings` when waste exceeds prepared |
| `GET /kitchen/daily-summary?date=` | A(R) K | M1 | K1, K5-K7, S6 | per item: forecast, recommended, final, prepared, served, wasted |
| `GET/POST/PATCH /kitchen/pre-orders` | K | S | K10 | |
| `POST /kitchen/shortage-reports` | K | S | K12 | creates a `manual_shortage` alert |

### 3.5 Alerts, dashboards, reports

| Method and path | Roles | Tier | Story | Notes |
|---|---|---|---|---|
| `GET /alerts?status=open&type=&refresh=` | A K I | M1 | I8, S4 | filtered by role (section 6). Evaluates first if the last evaluation is over 60 s old, or when `refresh=true`. |
| `POST /alerts/{id}/acknowledge` | A K I | M1 | I8 | only for alerts the role can see |
| `POST /alerts/run` | A | M1 | S4 | manual run, returns counts opened/closed |
| `GET /dashboards/admin?range=7\|30` | A | M2 | A1 | |
| `GET /dashboards/kitchen?date=` | K, A(R) | M1 | K1 | |
| `GET /dashboards/inventory` | I, A(R) | M1 | I1 | |
| `GET /reports/sales?from=&to=&group_by=day\|week\|month&item_id=` | A | M2 | A8 | rows plus totals plus top/bottom items |
| `GET /reports/waste?from=&to=&group_by=` | A | M2 | A11 | `food` and `ingredient` returned as two separate sections (assumption A6 in REQUIREMENTS) |
| `GET /reports/stock-movements?...&format=csv` | A | S | A13 | `format=csv` on any report returns the same rows as a download |

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
    "prepared_so_far": 0, "served_so_far": 0
  }]},
 "meta": {"generated_at": "2026-09-25T02:10:00Z"}}
```

`status` is `suggested`, `accepted`, `overridden` or `no_forecast` (then `recommended_qty` is `null` and `forecast_qty` is `null`; the UI shows "No forecast yet"). When a decision exists, its `final_qty` is returned next to the *current* `recommended_qty`, so the UI can show if the forecast has since moved.

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

Each page's data calls are listed in `UI_PLAN.md`. Page routes (HTML) return the shell and never the numbers, except where a service result is embedded through `{{ data|tojson }}`.

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
| `flask smartrest forecast [--as-of D] [--from D --to D]` | run forecast; `--from/--to` is the backfill used for accuracy views |
| `flask smartrest alerts` | evaluate alerts (`POST /alerts/run`) |
| `flask smartrest create-user` / `set-setting <key> <value>` | admin helpers, used until the S-tier pages exist |
