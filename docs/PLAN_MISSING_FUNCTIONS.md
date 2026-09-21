# Development plan: functions still missing from the proposal

**Status: proposed, not approved. No code has been written.** Per `CLAUDE.md` and `PLAN.md` section 10, approval must be followed by an edit to `PLAN.md` (tiers, hours, ladder) *before* any code. Everything below is stay-in-scope: no POS or payments, no automatic supplier ordering or supplier integration, no accounting, no staff scheduling, no multi-branch. A purchase order is an internal record; "send" only marks it as sent by hand.

Basis: audit of 21 Sep 2026 against `docs/proposal.pdf`. Deadline Mon 28 Sep; `PLAN.md` freezes features on Sun 27 at noon.

## 1. Summary

Estimates include tests, API, page and doc updates. The assumed capacity is 8 h a day for one builder (please confirm).

| # | Function | Role | Tier | h | New tables | Builds on (existing) |
|---|---|---|---|---|---|---|
| 1 | Manage Suppliers | Inventory | 1 | 2.0 | none | `suppliers`, `inv.create_supplier`, `GET /suppliers` |
| 2 | Stock Adjustment | Inventory | 1 | 2.5 | none | `stock_movements` (`adjustment` already allowed), `_draw_down` |
| 3 | Manage Purchase Orders | Inventory | 1 | 7.0 | none | `purchase_orders`, `purchase_order_lines`, `inv.on_order_map`, `record_stock_in` |
| 4 | Manage Food Availability | Kitchen | 1 | 1.5 | none | `menu_items.is_available`, `PATCH /menu-items/{id}/availability`, `toggleAvailable()` in `kitchen_prep.js` |
| 5 | Manage Pre-Order | Kitchen | 1 | 4.0 | none | `pre_orders`, `_preorder_totals`, prep-plan `preorder_qty` |
| 6 | Inventory Monitoring and Inventory Demand Forecast Monitoring | Admin | 1 | 2.0 | none | `GET /stock/levels`, `/stock/movements`, `/recommendations/ingredient-forecast` (already admin-permitted) |
| 7 | Request Kitchen Stock and Manage Kitchen Stock Requests | Kitchen and Inventory | 2 | 8.0 | `stock_requests`, `stock_request_lines` | `_draw_down`, `/kitchen/requirements` shortage rows |
| 8 | Validate Inventory Data (consistency check) | Inventory | 2 | 1.5 | none | `inv.stock_invariant_violations` |
| 9 | Food Demand Forecast Monitoring | Admin | 2 | 2.0 | none | `GET /forecasts` and its `item_id` filter (already admin-permitted) |
| 10 | System Reports (inventory and movements) | Admin | 2 | 2.5 | none | `csv_response`, existing report tabs |
| 14 | Shortage Reporting (added after a second check of the proposal) | Kitchen | 2 | 2.0 | none | `alerts` (`manual_shortage` type), `alert_service` |
| 15 | Restaurant Information Management (added after a second check) | Admin | 2 | 1.5 | none | `outlets` (name, address, contact, opening days and hours) |
| 11 | Manage Daily Order | Kitchen | 3 | 3.5 | `orders` | pattern of function 5 |
| 12 | Record Ingredient Usage | Kitchen | 3 | 3.5 | `ingredient_usage` | `preparation_records`, `recipe_lines` |
| 13 | System Analytics | Admin | 3 | 4.0 | none | `dashboard_service`, chart components |

Tier 1 is 19.0 h, Tier 2 is 17.5 h (with functions 14 and 15), Tier 3 is 11.0 h. Cross-cutting work (regression, docs, `TEST_LOG.md`) is about 4 h. The total is about 52 h.

## 2. Design per function

Every function follows the project order: service and its tests, then API (add the row to `API.md` first), then page. Writes are role-restricted with `@roles_required`; new routes are picked up automatically by `tests/api/test_rbac.py`.

**1. Suppliers (Inventory).**
- API: `POST /suppliers` and `PATCH /suppliers/{id}` (includes `is_active`); `GET` exists. Add `update_supplier` to `inventory_service` next to `create_supplier`.
- Rules: name is unique (`uq_suppliers_outlet_name`), lead time is at least 0, and an inactive supplier cannot be chosen for a new ingredient or purchase order. Existing references are kept.
- Page: `/inventory/suppliers` (list, add, edit, deactivate); nav entry "Suppliers" in `app/utils/navigation.py`.

**2. Stock adjustment (Inventory).**
- API: `POST /stock/adjustments` with `{ingredient_id, counted_quantity, movement_date, note}`; the note is mandatory.
- Rule (from `DATABASE.md`): difference = counted minus on-hand. A negative difference draws down batches like a stock-out; a positive one creates batch `ADJ-<date>` (no expiry) plus a `+` movement. A zero difference is rejected.
- Page: a fourth tab "Adjustment" on `/inventory/movements`.
- Test: the movement-sum invariant (INV-1) must still hold.

**3. Purchase orders (Inventory).**
- API: `GET /purchase-orders`, `GET /purchase-orders/{id}`, `POST /purchase-orders`, `POST .../send`, `.../receive`, `.../cancel`.
- Service: `po_number` is generated per outlet. Statuses are draft, sent, partially_received, received, cancelled. Receive is allowed from draft, sent or partially_received, and cancel only while nothing has been received.
- Receiving creates one batch and one `stock_in` movement per received line, sets `reference_type = "purchase_order"`, updates `qty_received`, and rejects a quantity above what remains. It needs `record_stock_in` extended with optional `purchase_order_id` and reference arguments. Existing calls must not change behaviour.
- "On order" already feeds the reorder formula, so no change to the formula. Add tests that a draft PO lowers the suggestion and a receipt clears it.
- Pages: `/inventory/purchase-orders` (list, detail, receive). On `/inventory/reorder`, add "Create purchase order" for selected rows, grouped by supplier.
- Uses row locks and `_retry_on_conflict`, as stock-out does.

**4. Food availability (Kitchen).**
- The API and service already exist. Add the missing control: an Available / Unavailable toggle and badge on each `/kitchen/prep` card, and the badge in the dashboard plan table.
- The flag stays a persistent on/off. It does not change the forecast or the recommendation. Audit each change.
- Optional phase 2 (about 2 h): suggest "unavailable" when usable stock cannot cover one batch, using `usable_map` and the recipes.

**5. Pre-orders (Kitchen).**
- API: `GET/POST/PATCH /kitchen/pre-orders` (already in `API.md`) with `{menu_item_id, target_date, quantity, customer_note, status}`; status is pending, confirmed or cancelled. Only confirmed pre-orders count in the recommendation, which already works.
- Page: `/kitchen/orders` with a "Pre-orders" tab (list, add, confirm, cancel). Show "Confirmed pre-orders N" on the prep card; the value is already returned.
- If a decision already exists and the recommendation changes, the card already shows "recommendation is now X".

**6. Admin inventory monitoring (Admin).**
- Page: `/admin/inventory` (nav "Inventory") with tabs Stock levels, Ingredient demand (7 days), and Recent movements. It is read-only and calls the existing endpoints, so numbers match the Inventory dashboard, as required by story A10. No new API.

**7. Kitchen stock requests (Kitchen and Inventory).**
- Tables `stock_requests` (requester, needed date, note, status, decided by and at, reject reason) and `stock_request_lines` (ingredient, quantity requested, quantity issued). Status is pending, approved, issued or rejected, plus cancelled by the requester while pending (proposed addition). One new Alembic migration.
- Logic lives in `inventory_service`, as the architecture table already assigns `StockRequest` to Inventory. This keeps `test_architecture` unchanged, because `kitchen_service` may not be called from inventory. The kitchen API controller calls the inventory service directly.
- Kitchen API: `POST /kitchen/stock-requests`, `GET /kitchen/stock-requests` (own), `POST .../{id}/cancel`.
- Inventory API: `GET /stock-requests`, `POST .../{id}/approve`, `.../reject` (reason required), `.../issue` (quantities per line).
- Issuing checks usable stock, draws down FEFO with reason `issued_to_kitchen`, sets `reference_type = "stock_request"`, and does it in one transaction. A request cannot be issued twice.
- Pages: `/kitchen/stock-requests` (create, status, reject reason) and a "Request" action on shortage rows of `/kitchen/requirements`. On the inventory side, `/inventory/requests` and a "Pending requests" tile on the Inventory dashboard.

**8. Validate inventory data (Inventory).**
- API: `GET /stock/consistency` returns `stock_invariant_violations` plus batches that are expired but still hold stock. Add a "Run data check" panel on `/inventory/stock` and a CLI command `flask smartrest check-stock`.

**9. Admin forecast monitoring (Admin).**
- Add a "Demand forecast" tab to `/admin/monitor`: the 7-day item-by-day table from the existing `GET /forecasts`. Add an item selector to the Forecast accuracy tab, using the existing `item_id` parameter. No new API.

**10. Admin reports (Admin).**
- Add "Inventory" and "Movements" tabs to `/admin/monitor` with date filters and CSV export, through `GET /reports/inventory` and `GET /reports/movements` in `dashboards.py`. Exported figures must equal the on-screen figures (story A13).

**14. Shortage reporting (Kitchen).**
- API: `POST /kitchen/shortage-reports` (in `API.md`) with `{ingredient_id, note}` creates a high-priority `manual_shortage` alert, visible to Inventory and Admin (rule already in `alert_service.VISIBLE_TO`). It stays open until the inventory manager acknowledges it. A "Report shortage" control on the shortage rows of `/kitchen/requirements`.

**15. Restaurant information (Admin).**
- API: `GET/PUT /restaurant` for name, address, contact, opening days and hours (all columns already on `outlets`). A "Restaurant information" card on `/admin/settings`.

**11. Daily orders (Kitchen).**
- Table `orders`: item, date, quantity, status (open, fulfilled or cancelled), customer note. API `GET/POST/PATCH /kitchen/orders`, in the second tab of `/kitchen/orders`. It is an internal record only, with no prices or payments, and it does not feed any calculation.

**12. Ingredient usage (Kitchen).**
- Table `ingredient_usage` (date, ingredient, quantity, note). `GET /kitchen/ingredient-usage?date=` returns expected usage (prepared × recipe) next to the recorded amount and the variance. `POST /kitchen/ingredient-usage` records an actual amount. Per `DATABASE.md` DB8, usage does not change stock; the inventory manager still posts stock-outs. A card on `/kitchen/record`.

**13. Admin analytics (Admin).**
- A read-only `dashboard_service.analytics()` behind `GET /reports/analytics`, shown as an "Analytics" tab on `/admin/monitor`: demand by day of week, average sales on holidays and promotions against other days, forecast error over time, and the waste rate over time. It shows the date range and the "synthetic data" label. "Waste versus stock-out days" is dropped, because no daily stock snapshot exists.

## 3. Rules that apply to all of it

- Reads are role-restricted as in `API.md`; new routes and pages must appear in the RBAC matrix, and `test_architecture` must stay green.
- Stock only changes through immutable movements (never a running total). The movement-sum invariant test runs after every new flow (receive, adjust, issue).
- Quantities use `Decimal`, dates come from `today()`, every write is audited, CSRF and `[[ ]]` Vue delimiters as usual.
- Update in the same commit: `API.md`, `DATABASE.md` (new tables, statuses), `UI_PLAN.md`, `REQUIREMENTS.md` status, `PLAN.md` section 0, and `TEST_LOG.md`.
- One Alembic migration per feature that adds tables (functions 7, 11, 12), applied in sequence so there is a single head.
- Do not edit the seed. Hand-calculated demo numbers (`TESTING.md`) must stay valid.
- Work on a copy of the database. Run tests against `smartrest_test`, and run `flask db upgrade` on the live demo database only at the end, after a `mysqldump`. `tests/ui/smoke.py` and the perf tests must not run against the live demo data.

## 4. Schedule and cut ladder

| Day | Work | h |
|---|---|---|
| Tue 22 | Suppliers (1), Stock adjustment (2), Availability toggle (4), Admin inventory monitoring (6) | 8 |
| Wed 23 | Purchase orders (3) and regression | 8 |
| Thu 24 | Pre-orders (5), Data check (8), Admin forecast monitoring (9) | 8 |
| Fri 25 | Kitchen stock requests, both sides (7) | 8 |
| Sat 26 | Admin reports (10), hardening: full test suite, RBAC pass, 360 and 1280 px checks, docs and `TEST_LOG.md` | 8 |
| Sun 27 | Feature freeze at noon. Report and demo only. | |

Tier 3 (functions 11 to 13, about 11 h) does not fit in this schedule at 8 h a day. It is built only if capacity is higher or people work in parallel; the functions are independent by role. The migration chain and `app/utils/navigation.py` are the only shared edit points.

**Ladder if time slips (drop in this order; keep service and API, drop only the page):** Tier 3 in full, then Reports (10), Data check (8), Forecast monitoring (9), Stock requests (7). Never dropped: Suppliers, Purchase orders, Adjustment, Pre-orders, Availability, Inventory monitoring, and the tests.

## 5. Decisions to confirm before coding

1. **Capacity and freeze:** 8 h a day and the Sun 27 noon freeze; Sat 26 is used as a build day, not just a buffer.
2. **Daily order:** internal record with statuses open, fulfilled, cancelled; no feed into forecasts.
3. **Ingredient usage:** expected usage (prepared × recipe) plus an optional recorded amount; it does not move stock (DB8).
4. **Availability:** one persistent flag that the manager flips back; no automatic suggestion unless phase 2 is wanted.
5. **Stock request:** issue may be partial per line; the requester can cancel while pending (new status).
6. **PO receipt:** cannot exceed the quantity ordered; receiving is allowed without pressing "send" first.
7. **Adjustment basis:** counted quantity compared with on-hand (including expired stock), and a shortfall drawn from the earliest-expiry batches first.
8. **Orders page:** one `/kitchen/orders` page with two tabs, instead of the `/kitchen/pre-orders` page named in `UI_PLAN.md`.
