# Preservation checklist (role dashboards, October 2026)

Baseline: production commit `d26b1e9` (14 Oct 2026). Branch: `role-dashboards`. This list is generated from
`tests/preservation_baseline.json`, which `scripts/preservation_audit.py` reads from the code, and
`tests/api/test_preservation.py` checks every item against the new version. **Status: all kept** unless a row says
otherwise; nothing was removed or disabled.

## 1. Summary

| Area | Items in the baseline | How it is checked | Result |
|---|---|---|---|
| API routes and page addresses (method + path + allowed roles) | 122 | PRES-1: same methods, same roles | kept, roles identical |
| Menu pages, groups and tabs | 14 pages, 16 tabs | PRES-2: identical | kept |
| Reports & Analytics reports | 10 | PRES-3 | kept |
| Old addresses that redirect | 9 | PRES-3: each still redirects | kept |
| CLI commands (`flask smartrest ...`) | 11 | PRES-3 | kept |
| Page views (page or tab) | 24 | PRES-4, PRES-5 | kept; each role opens all of its views, none of another role's |
| Buttons and action links on those views | 125 | PRES-4 | kept |
| API calls made by those views | 117 | PRES-4 | kept; 2 dashboard calls now come from the dashboard endpoint (section 4) |
| ML: training, model comparison, activation, daily forecast, evaluation | code unchanged (`app/ml`, `forecasting_service`) | existing ML and forecast tests | kept |
| Database: tables, columns, migrations | no model or migration change (7 revisions, head `c4e1a7b9d052`) | `git diff` of `app/models`, `migrations` is empty | kept |
| Calculations: prep quantity, BOM requirements, reorder, waste rate, accuracy, stock status | unchanged services | existing tests + RD-1..RD-4 (section 5) | kept, verified |
| Role permissions | unchanged guards | PRES-1, PRES-5, existing RBAC tests | kept |
| Synthetic-data indicator | top-bar pill on every page | template unchanged; admin performance card also says so | kept |

## 2. Dashboards: every function before, and where it is now

| Dashboard | Function before | Now |
|---|---|---|
| Admin | Reporting period 7 / 30 days | kept |
| Admin | Partial-sales warning | kept |
| Admin | Six-step workflow with today's figures, links to reports | kept (admin only: the management view of the whole chain) |
| Admin | Sales history + 7-day forecast chart | kept, now the whole period and food waste on the same chart |
| Admin | Separate sales and waste trend chart | merged into the chart above (same data, same endpoints) |
| Admin | Model name, hold-out MAE vs baseline, WAPE, last run | kept in Forecasting performance |
| Admin | - | new: accuracy on the reporting period (actual vs forecast made before the day), from the Forecast accuracy report's function |
| Admin | Forecast total, sales total, waste rate under the chart | shown once, in the workflow row (they were duplicated) |
| Admin | Alerts: open list, Acknowledge, History tab, counts | kept |
| Admin | Recommended actions | kept as Needs attention, each with a recommendation and an action button |
| Admin | Upcoming confirmed pre-orders | kept (compact) |
| Admin | Recent activity, Show more | kept |
| Admin | Quick actions (4 links) | removed from the dashboard: they repeated sidebar links (Forecasting, Menu & recipes, Reports, Stock levels); every target page is unchanged and also linked from Needs attention |
| Kitchen | Date navigation, Plan & prepare, Record served & waste buttons | kept |
| Kitchen | Six-step strip (other roles' steps muted) | replaced by four kitchen figures: forecast, to prepare, prepared, served / wasted |
| Kitchen | Today's plan table with prepared progress | kept |
| Kitchen | Ingredient shortages + Request stock | kept |
| Kitchen | Alerts with Acknowledge | kept |
| Kitchen | - | new: Needs attention (decisions, shortages, pending pre-orders, served not recorded) and the day's pre-orders |
| Inventory | Record stock, Reorder buttons | kept |
| Inventory | Six-step strip | replaced by four inventory figures: usable stock, kitchen requests, short in 7 days, expiry |
| Inventory | Reorder now (top 5) with link to all | kept; the link now gives the full count |
| Inventory | Stock-out risk, next 7 days | kept; says how many more are on Ingredient demand |
| Inventory | Expiring soon | kept; the count is now exact (was capped at 10) |
| Inventory | Alerts with Acknowledge and counts | kept |
| Inventory | - | new: Needs attention (requests, issue, expired, reorder, draft and awaited purchase orders, expiring) and open kitchen requests |

## 3. Pages and tabs

| Role | Menu group | Page | Address | Tabs |
|---|---|---|---|---|
| admin | Overview | Dashboard | `/admin` | - |
| admin | Overview | Reports & Analytics | `/admin/monitor` | - |
| admin | Overview | Forecasting | `/admin/models` | Historical data, ML models, Forecast generation |
| admin | Setup | Menu & recipes | `/admin/catalog` | - |
| admin | Setup | Administration | `/admin/users` | Users, Settings & alerts, Role access |
| kitchen | Today | Dashboard | `/kitchen` | - |
| kitchen | Today | Plan & prepare | `/kitchen/prep` | Prep plan, 7-day forecast |
| kitchen | Today | Served & waste | `/kitchen/record` | - |
| kitchen | Supplies & orders | Ingredients | `/kitchen/requirements` | Needs & shortages, Stock requests |
| kitchen | Supplies & orders | Orders & pre-orders | `/kitchen/orders` | - |
| inventory | Today | Dashboard | `/inventory` | - |
| inventory | Today | Kitchen requests | `/inventory/requests` | - |
| inventory | Stock & buying | Stock | `/inventory/stock` | Stock levels, Record stock |
| inventory | Stock & buying | Purchasing | `/inventory/reorder` | Reorder, Ingredient demand, Purchase orders, Suppliers |

Reports & Analytics: Sales and revenue, Demand forecast, Forecast accuracy, Analytics, Waste reports, Stock levels, Ingredient demand, Batches and expiry, Stock trends, Stock movements.

Old addresses that still redirect: `/admin/data`, `/admin/inventory`, `/admin/settings`, `/inventory/forecast`, `/inventory/movements`, `/inventory/purchase-orders`, `/inventory/suppliers`, `/kitchen/forecast`, `/kitchen/stock-requests`.

CLI: `activate`, `check-stock`, `create-user`, `demo-reset`, `evaluate`, `forecast`, `forecast-daily`, `generate-data`, `seed`, `set-setting`, `train`.

## 4. Actions and data on each page

Buttons and action links as written in the templates, and the API calls each page makes. All are kept. The two
dashboard calls marked *moved* now come from the dashboard endpoint, and the same call is still made by the page named.

**`/admin`** (admin/dashboard.html)

- Actions: (alert list with Acknowledge), History, Last 30 days, Last 7 days, Open ([[ alerts.length ]]), Try again
- Data: GET /alerts, GET /dashboards/admin, GET /model-versions, GET /recommendations/prep, GET /recommendations/reorder, GET /recommendations/requirements, GET /reports/sales, GET /reports/waste, POST /alerts/<id>

**`/admin/catalog`** (admin/catalog.html)

- Actions: Add ingredient, Add menu item, Cancel, Edit, Edit recipe, Remove, Save, Save recipe, [[ i.is_active ? 'Deactivate' : 'Activate' ]], [[ i.name ]], [[ view && view.item.id === i.id ? 'Hide recipe' : 'Recipe' ]]
- Data: GET /ingredients, GET /menu-items, GET /menu-items/<id>, PATCH /menu-items/<id>, POST /menu-items, PUT /menu-items/<id>

**`/admin/models?tab=data`** (admin/data.html)

- Actions: (CSV import /holidays/import), (CSV import /sales/import), (CSV import /weather/import), Add promotion, Cancel, Save, [[ t[1] ]]
- Data: GET /menu-items, GET /promotions, PATCH /promotions/<id>, POST /promotions

**`/admin/models?tab=models`** (admin/models.html)

- Actions: Activate, Run forecast now, Train new model
- Data: GET /forecast-runs, GET /model-versions, POST /forecast-runs, POST /model-versions, POST /model-versions/<id>

**`/admin/models?tab=runs`** (admin/models.html)

- Actions: Activate, Run forecast now, Train new model
- Data: GET /forecast-runs, GET /model-versions, POST /forecast-runs, POST /model-versions, POST /model-versions/<id>

**`/admin/monitor`** (admin/monitor.html)

- Actions: Download CSV, Download stock levels (CSV), [[ g[1] ]], [[ t[1] ]]
- Data: CSV /api/v1/forecasts/accuracy, CSV /api/v1/reports/inventory-trend, CSV /api/v1/reports/movements, GET /forecasts, GET /forecasts/accuracy, GET /ingredients, GET /menu-items, GET /recommendations/ingredient-forecast, GET /reports/analytics, GET /reports/food-usage, GET /reports/inventory-trend, GET /reports/movements, GET /reports/sales, GET /reports/waste, GET /stock/batches, GET /stock/levels

**`/admin/users?tab=roles`** (admin/roles.html)

- Actions: none (read-only view)
- Data: server-rendered

**`/admin/users?tab=settings`** (admin/settings.html)

- Actions: Check alerts now, Save restaurant information, Save settings
- Data: GET /restaurant, GET /settings, POST /alerts/run, PUT /restaurant, PUT /settings

**`/admin/users?tab=users`** (admin/users.html)

- Actions: Add user, Cancel, Create, [[ u.is_active ? 'Deactivate' : 'Reactivate' ]]
- Data: GET /users, PATCH /users/<id>, POST /users

**`/inventory`** (inventory/dashboard.html)

- Actions: (alert list with Acknowledge), Record stock, Reorder
- Data: GET /alerts, GET /dashboards/inventory, GET /recommendations/reorder (moved: the full count comes from `/dashboards/inventory`; Purchasing > Reorder still calls it), POST /alerts/<id>

**`/inventory/reorder?tab=demand`** (inventory/forecast.html)

- Actions: none (read-only view)
- Data: GET /recommendations/ingredient-forecast

**`/inventory/reorder?tab=orders`** (inventory/purchase_orders.html)

- Actions: Add ingredient, Cancel, Cancel order, Close, Mark as sent, New purchase order, Open, Receive stock, Record receipt, Remove, Save as draft
- Data: GET /alerts, GET /ingredients, GET /purchase-orders, GET /purchase-orders/<id>, GET /suppliers, POST /purchase-orders, POST /purchase-orders/<id>

**`/inventory/reorder?tab=reorder`** (inventory/reorder.html)

- Actions: Create purchase order 1">s ([[ supplierCount ]] suppliers)
- Data: GET /recommendations/reorder, POST /purchase-orders

**`/inventory/reorder?tab=suppliers`** (inventory/suppliers.html)

- Actions: Add supplier, Cancel, Edit, Save, [[ r.is_active ? 'Deactivate' : 'Activate' ]]
- Data: GET /suppliers, PATCH /suppliers/<id>, POST /suppliers

**`/inventory/requests`** (inventory/requests.html)

- Actions: Approve, Cancel, Close, Issue, Issue stock, Open, Reject, Reject request
- Data: GET /alerts, GET /stock-requests, GET /stock-requests/<id>, POST /stock-requests/<id>

**`/inventory/stock?tab=levels`** (inventory/stock.html)

- Actions: Add ingredient, Cancel, Edit, Run data check, Save
- Data: GET /stock/consistency, GET /stock/levels, GET /suppliers, PATCH /ingredients/<id>, POST /ingredients

**`/inventory/stock?tab=record`** (inventory/movements.html)

- Actions: Adjustment, Save, Stock in, Stock out, Wastage
- Data: GET /alerts, GET /ingredients, GET /stock/batches, GET /stock/levels, GET /stock/movements

**`/kitchen`** (kitchen/dashboard.html)

- Actions: (alert list with Acknowledge), (date navigation), Plan & prepare, Record served & waste, Request stock
- Data: GET /alerts, GET /dashboards/kitchen, GET /kitchen/daily-summary (moved: served and wasted come from `/dashboards/kitchen`; Served & waste still calls it), GET /kitchen/stock-requests, POST /alerts/<id>

**`/kitchen/orders`** (kitchen/orders.html)

- Actions: (date navigation), Add pre-order, Cancel, Close, Complete, Details, Edit, Fulfilled, Save, [[ actionLabel(s) ]], [[ oform.id ? 'Save changes' : 'Add order' ]], [[ t[1] ]]
- Data: GET /kitchen/orders, GET /kitchen/pre-orders, GET /kitchen/pre-orders/<id>, GET /menu-items, PATCH /kitchen/orders/<id>, PATCH /kitchen/pre-orders/<id>, POST /kitchen/orders, POST /kitchen/pre-orders

**`/kitchen/prep?tab=forecast`** (kitchen/forecast.html)

- Actions: (date navigation)
- Data: GET /forecasts

**`/kitchen/prep?tab=prep`** (kitchen/prep.html)

- Actions: (date navigation), + Add, Accept [[ it.recommended_qty ]], Cancel, Mark done, Override, Reopen, Save override, Start, [[ it.is_available ? 'Mark unavailable' : 'Mark available' ]]
- Data: GET /recommendations/prep, PATCH /menu-items/<id>, POST /kitchen/prepared, POST /recommendations/prep/decisions, POST /recommendations/prep/status

**`/kitchen/record`** (kitchen/record.html)

- Actions: (date navigation), Add row, Clear, Overwrite, Record other use, Record waste, Save, Save served quantities, [[ t.label ]]
- Data: GET /ingredients, GET /kitchen/daily-summary, GET /kitchen/food-usage, GET /kitchen/ingredient-usage, POST /kitchen/food-usage, POST /kitchen/ingredient-usage, POST /kitchen/waste, POST /sales/served

**`/kitchen/requirements?tab=needs`** (kitchen/requirements.html)

- Actions: (date navigation), Report shortage, Request stock
- Data: GET /recommendations/requirements, POST /kitchen/shortage-reports

**`/kitchen/requirements?tab=requests`** (kitchen/stock_requests.html)

- Actions: Add ingredient, Cancel, Cancel request, New request, Remove, Send request
- Data: GET /ingredients, GET /kitchen/stock-requests, POST /kitchen/stock-requests, POST /kitchen/stock-requests/<id>

## 5. Calculations verified with controlled test cases

| Figure on a dashboard | Source | Test (expected value worked out by hand) |
|---|---|---|
| Sales quantity and revenue, waste quantity and value, waste rate | dashboard_service.admin_dashboard | test_admin_dashboard.py (100 portions, 44,000; 20 portions, 9,000; 16.7 %) |
| Forecast accuracy this period (MAE, WAPE, bias, pairs) | forecasting_service.accuracy | RD-1: MAE 6.667, WAPE 22.22 %, bias +3.33, 3 pairs; a forecast made after the day is ignored |
| Kitchen forecast total, items decided, to prepare, prepared, served, wasted | kitchen_dashboard -> _kitchen_day | RD-2: 15.0 portions, 2 of 2 undecided, 17 to prepare (12 + 5), 6 prepared, served not recorded, 1 wasted |
| Kitchen pre-orders of the day | kitchen_service.list_pre_orders | RD-2: cancelled and other days left out; 1 pending, 3 confirmed portions |
| Prep quantity = forecast + buffer (or confirmed pre-orders), up to a whole batch | recommendation_service | RD-2 (12 and 5), test_kitchen_recommendation.py, E2E-1 |
| BOM ingredient need over 7 days, ingredients short | get_ingredient_forecast | RD-3: bun need 26 = 12 + 14, 15 usable -> 1 at risk |
| Reorder count (not capped at the 5 shown) | get_reorder_suggestions | RD-3: 7+ suggestions, list shows 5 |
| Expired and expiring batches (not capped at 10) | inventory_service.list_batches | RD-3: used-up expired batch not counted; 1 expired, 1 expiring |
| Kitchen requests waiting / approved; draft and awaited purchase orders | inventory_service | RD-3: 2 / 1; 1 draft, 2 awaiting |
| Dashboards write nothing except the alert check | all three | RD-4: recommendations, movements, sales, forecasts unchanged |
| Whole chain on one controlled dataset | all services | E2E-1 test_end_to_end_workflow.py (unchanged, passes) |

## 6. Routes and roles

| Method | Path | Roles |
|---|---|---|
| GET | `/` | (any / public) |
| GET | `/admin` | admin |
| GET | `/admin/catalog` | admin |
| GET | `/admin/data` | admin |
| GET | `/admin/inventory` | admin |
| GET | `/admin/models` | admin |
| GET | `/admin/monitor` | admin |
| GET | `/admin/settings` | admin |
| GET | `/admin/users` | admin |
| GET | `/api/v1/alerts` | admin, inventory, kitchen |
| POST | `/api/v1/alerts/<int:alert_id>/acknowledge` | admin, inventory, kitchen |
| POST | `/api/v1/alerts/run` | admin |
| GET | `/api/v1/dashboards/admin` | admin |
| GET | `/api/v1/dashboards/inventory` | admin, inventory |
| GET | `/api/v1/dashboards/kitchen` | admin, kitchen |
| GET | `/api/v1/forecast-runs` | admin |
| POST | `/api/v1/forecast-runs` | admin |
| GET | `/api/v1/forecasts` | admin, inventory, kitchen |
| GET | `/api/v1/forecasts/accuracy` | admin |
| GET | `/api/v1/holidays` | admin |
| POST | `/api/v1/holidays/import` | admin |
| GET | `/api/v1/ingredients` | admin, inventory, kitchen |
| POST | `/api/v1/ingredients` | inventory |
| PATCH | `/api/v1/ingredients/<int:ingredient_id>` | inventory |
| GET | `/api/v1/kitchen/daily-summary` | admin, kitchen |
| GET | `/api/v1/kitchen/food-usage` | admin, kitchen |
| POST | `/api/v1/kitchen/food-usage` | kitchen |
| DELETE | `/api/v1/kitchen/food-usage/<int:usage_id>` | kitchen |
| GET | `/api/v1/kitchen/ingredient-usage` | admin, kitchen |
| POST | `/api/v1/kitchen/ingredient-usage` | kitchen |
| DELETE | `/api/v1/kitchen/ingredient-usage/<int:usage_id>` | kitchen |
| GET | `/api/v1/kitchen/orders` | admin, kitchen |
| POST | `/api/v1/kitchen/orders` | kitchen |
| PATCH | `/api/v1/kitchen/orders/<int:order_id>` | kitchen |
| GET | `/api/v1/kitchen/pre-orders` | admin, kitchen |
| POST | `/api/v1/kitchen/pre-orders` | kitchen |
| GET | `/api/v1/kitchen/pre-orders/<int:pre_order_id>` | admin, kitchen |
| PATCH | `/api/v1/kitchen/pre-orders/<int:pre_order_id>` | kitchen |
| POST | `/api/v1/kitchen/prepared` | kitchen |
| POST | `/api/v1/kitchen/shortage-reports` | kitchen |
| GET | `/api/v1/kitchen/stock-requests` | admin, kitchen |
| POST | `/api/v1/kitchen/stock-requests` | kitchen |
| POST | `/api/v1/kitchen/stock-requests/<int:request_id>/cancel` | kitchen |
| POST | `/api/v1/kitchen/waste` | kitchen |
| GET | `/api/v1/me` | admin, inventory, kitchen |
| GET | `/api/v1/menu-items` | admin, inventory, kitchen |
| POST | `/api/v1/menu-items` | admin |
| PATCH | `/api/v1/menu-items/<int:item_id>` | admin |
| PATCH | `/api/v1/menu-items/<int:item_id>/availability` | kitchen |
| GET | `/api/v1/menu-items/<int:item_id>/recipe` | admin, inventory, kitchen |
| PUT | `/api/v1/menu-items/<int:item_id>/recipe` | admin |
| GET | `/api/v1/model-versions` | admin |
| POST | `/api/v1/model-versions` | admin |
| POST | `/api/v1/model-versions/<int:version_id>/activate` | admin |
| GET | `/api/v1/promotions` | admin |
| POST | `/api/v1/promotions` | admin |
| PATCH | `/api/v1/promotions/<int:promotion_id>` | admin |
| GET | `/api/v1/purchase-orders` | admin, inventory |
| POST | `/api/v1/purchase-orders` | inventory |
| GET | `/api/v1/purchase-orders/<int:po_id>` | admin, inventory |
| POST | `/api/v1/purchase-orders/<int:po_id>/cancel` | inventory |
| POST | `/api/v1/purchase-orders/<int:po_id>/receive` | inventory |
| POST | `/api/v1/purchase-orders/<int:po_id>/send` | inventory |
| GET | `/api/v1/recommendations/ingredient-forecast` | admin, inventory |
| GET | `/api/v1/recommendations/prep` | admin, kitchen |
| POST | `/api/v1/recommendations/prep/decisions` | kitchen |
| POST | `/api/v1/recommendations/prep/status` | kitchen |
| GET | `/api/v1/recommendations/reorder` | admin, inventory |
| GET | `/api/v1/recommendations/requirements` | admin, inventory, kitchen |
| GET | `/api/v1/reports/analytics` | admin |
| GET | `/api/v1/reports/food-usage` | admin |
| GET | `/api/v1/reports/inventory-trend` | admin |
| GET | `/api/v1/reports/movements` | admin |
| GET | `/api/v1/reports/sales` | admin |
| GET | `/api/v1/reports/stock-levels` | admin |
| GET | `/api/v1/reports/waste` | admin |
| GET | `/api/v1/restaurant` | admin |
| PUT | `/api/v1/restaurant` | admin |
| POST | `/api/v1/sales/import` | admin |
| POST | `/api/v1/sales/served` | kitchen |
| GET | `/api/v1/settings` | admin |
| PUT | `/api/v1/settings` | admin |
| GET | `/api/v1/stock-requests` | admin, inventory |
| GET | `/api/v1/stock-requests/<int:request_id>` | admin, inventory |
| POST | `/api/v1/stock-requests/<int:request_id>/approve` | inventory |
| POST | `/api/v1/stock-requests/<int:request_id>/issue` | inventory |
| POST | `/api/v1/stock-requests/<int:request_id>/reject` | inventory |
| POST | `/api/v1/stock/adjustments` | inventory |
| GET | `/api/v1/stock/batches` | admin, inventory |
| GET | `/api/v1/stock/consistency` | admin, inventory |
| POST | `/api/v1/stock/in` | inventory |
| GET | `/api/v1/stock/levels` | admin, inventory, kitchen |
| GET | `/api/v1/stock/movements` | admin, inventory |
| POST | `/api/v1/stock/out` | inventory |
| POST | `/api/v1/stock/wastage` | inventory |
| GET | `/api/v1/suppliers` | admin, inventory |
| POST | `/api/v1/suppliers` | inventory |
| PATCH | `/api/v1/suppliers/<int:supplier_id>` | inventory |
| GET | `/api/v1/users` | admin |
| POST | `/api/v1/users` | admin |
| PATCH | `/api/v1/users/<int:user_id>` | admin |
| POST | `/api/v1/users/<int:user_id>/password` | admin |
| GET | `/api/v1/weather` | admin |
| POST | `/api/v1/weather/import` | admin |
| GET | `/inventory` | inventory |
| GET | `/inventory/forecast` | inventory |
| GET | `/inventory/movements` | inventory |
| GET | `/inventory/purchase-orders` | inventory |
| GET | `/inventory/reorder` | inventory |
| GET | `/inventory/requests` | inventory |
| GET | `/inventory/stock` | inventory |
| GET | `/inventory/suppliers` | inventory |
| GET | `/kitchen` | kitchen |
| GET | `/kitchen/forecast` | kitchen |
| GET | `/kitchen/orders` | kitchen |
| GET | `/kitchen/prep` | kitchen |
| GET | `/kitchen/record` | kitchen |
| GET | `/kitchen/requirements` | kitchen |
| GET | `/kitchen/stock-requests` | kitchen |
| GET | `/login` | (any / public) |
| POST | `/login` | (any / public) |
| POST | `/logout` | admin, inventory, kitchen |

## 7. Approved simplifications (14 Oct 2026, branch `simplify`)

Approved by the project owner: M1, M2 (modified), M3, M4, M5, M6, M7, M8, R1, R2. No route, role, record, calculation,
ML function or proposal capability was removed; `tests/api/test_preservation.py` lists each change and checks where the
function now is.

| ID | Change | Capability kept, and where |
|---|---|---|
| M1 | Ingredients & requests: one **Ask inventory** button per ingredient opens two choices | Kitchen stock request (K11): *Request stock* opens the request form filled in. Shortage reporting (K12): *Report shortage* with an optional note, now inline instead of a browser prompt. Both endpoints unchanged |
| M2 | Kitchen requests: one step at a time. Pending shows **Approve** / **Reject**; approved shows **Issue to kitchen**; a step line shows who approved | Approve and Issue stay two separate, recorded operations (as instructed); the list says the next step. Server rules unchanged |
| M3 | Prep plan: the **Start** button is gone | Recording the first prepared quantity marks the item in progress (unchanged service rule, test_prep_workflow); Mark done and Reopen stay; the API still accepts `start` |
| M4 | Served & waste: four tabs become **End of day** (1 served, 2 food waste, 3 other food use) and **Daily balance** (balance + ingredient use) | K6, K7, K14, K8 unchanged; each section saves on its own; `#served`, `#waste`, `#other` open End of day at that section |
| M5 | Reports: Stock trends + Stock movements = **Stock history** | Day-by-day stock for one ingredient and the movement table; both CSV downloads; `?tab=inventory` and `?tab=movements` open it |
| M6 | Reports: Stock levels + Batches and expiry = **Stock & expiry** | Stock levels table and CSV, batch table with days to expiry; `?tab=batches` opens it at the batches |
| M7 | Administration: Role access is a section under **Users** | Same tables (read from the server's access rules); `?tab=roles` opens Users at that section |
| M8 | Wording: kitchen **Food waste**, inventory **Stock wastage**, **Issue to kitchen** (was Stock out / Issue stock), menu **Ingredients & requests** | Labels only; movement types, endpoints and records unchanged |
| R1 | The "Step n of 6" marker in the top bar is removed | The six-step workflow stays on the admin dashboard |
| R2 | 83 unused CSS rules; dashboard fields no page read: `low_stock_count` (= out + low, still in `stock`), kitchen `tiles.items_to_prepare`, `tiles.open_alerts` | `tiles.items_planned` / `items_done` kept (prep-workflow tests use them) |

Reports & Analytics now has 8 reports (was 10) under the same 4 groups; Administration has 2 tabs (was 3).
