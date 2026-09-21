# SmartRestaurant: UI plan

Read `REQUIREMENTS.md` (NFR1, NFR4, A13), `ARCHITECTURE.md` section 7.5 and `API.md` first. Tier labels (M1, M2, S) are defined in `PLAN.md`.

## 1. Principles

1. **Non-technical staff first (NFR1).** Each role's home page answers one question: kitchen "what do I make today?", inventory "what do I need to buy?", admin "is the system healthy and are forecasts any good?".
2. **Show why, not just what.** Every recommendation shows the numbers behind it (forecast, buffer, pre-orders, batch size; reorder terms). K3 and I9 require it.
3. **One number, one source.** Pages show values from `/api/v1`; charts and tables read the same response, so they cannot disagree.
4. **Bootstrap 5 defaults, no custom design system.** Time goes into flows, not styling. One `app.css` of about 100 lines.
5. **Mobile-first for the kitchen** (a phone or tablet near the pass), desktop-first for inventory and admin. Everything stays usable at 360 px wide with no page-level horizontal scroll (NFR4).
6. **Honest labelling.** A banner reads "Synthetic demo data" (from setting `data_source_label`). Estimated weather and baseline forecasts carry visible tags. Empty and missing data always say what is missing (NFR3).

## 2. Stack and structure

| Item | Choice |
|---|---|
| Layout | Jinja2 `base.html`: navbar (role links, alert bell, user menu), synthetic-data banner, `<main class="container-fluid">`, flash area. CSRF token in `<meta name="csrf-token">`. |
| Interactivity | Vue 3 global build (`vue.global.prod.js`), one `createApp` per page in `static/js/pages/<page>.js`, mounted on `#app`. **Delimiters `[[ ]]`** (set on every app) so Jinja's `{{ }}` is untouched. |
| Charts | Chart.js 4, wrapped in two small components (line, bar). |
| Vendored files | `static/vendor/`: Vue, Bootstrap CSS and JS, Chart.js. Fetched once by `scripts/vendor.sh`, committed, versions listed in `static/vendor/VERSIONS.txt`. No CDN at demo time. |
| API access | `static/js/api.js`: `api.get/post/put/patch(path, body)`; adds CSRF header, unwraps `data`, throws `{code, message, fields}` on error, redirects to `/login` on 401. |
| Shared components (`static/js/components.js`) | `sr-stat-tile`, `sr-status-badge`, `sr-alert-list`, `sr-field-error`, `sr-date-nav` (previous, today, next), `sr-empty`, `sr-confirm` (modal), `sr-csv-import` (choose file, dry run, result table, confirm), `sr-line-chart`, `sr-bar-chart`. |
| Formatting | `static/js/ui.js`: LKR money, quantity with unit, date `Mon 25 Sep`, toast. All display formatting lives here, never in services. |

Page skeleton (every page follows it):

```html
{% extends "base.html" %}
{% block content %}
<div id="app" v-cloak>...markup using [[ value ]]...</div>
<script>window.PAGE = {{ initial|tojson }};</script>   {# only for cheap initial data #}
<script src="{{ url_for('static', filename='js/pages/kitchen_prep.js') }}"></script>
{% endblock %}
```

```js
Vue.createApp({ delimiters: ['[[', ']]'], data() { return { rows: [], loading: true, error: null }; },
  async mounted() { /* api.get(...) then set rows, loading=false */ } }).mount('#app');
```

## 3. Navigation and pages

Login redirects by role (C1). Menus are role-specific and **also** enforced server-side (C2). The alert bell shows the count of open alerts visible to the role and opens a dropdown of the latest five.

Tier here is the tier of the page; the service behind it may be built earlier.

### 3.1 Kitchen (`/kitchen`, mobile-first)

| Route | Page | Stories | Tier | API calls |
|---|---|---|---|---|
| `/kitchen` | Dashboard: today's tiles (items to prepare, prepared so far, ingredient shortages, open alerts) and a compact plan table | K1 | M1 | `dashboards/kitchen`, `alerts` |
| `/kitchen/forecast` | 7-day forecast per item (table, line chart for the selected item); "No forecast yet" states | K2 | M1 | `forecasts` |
| `/kitchen/prep` | **The core screen.** One card per item: forecast, buffer, pre-orders, recommended, Accept / Override (qty and reason), and "prepared so far" with a quick add | K3, K5 | M1 | `recommendations/prep`, `.../decisions`, `kitchen/prepared` |
| `/kitchen/record` | End-of-day entry: served quantity per item; record waste (item, qty, reason) | K6, K7 | M1 | `kitchen/daily-summary`, `sales/served`, `kitchen/waste` |
| `/kitchen/requirements` | Ingredient requirements for the day, shortage rows highlighted, "cannot compute" list | K9 | M1 | `recommendations/requirements` |
| `/kitchen/orders` | Pre-orders: list with date, status and item filters; add, edit, confirm, cancel. One page for pre-orders and (Tier 3) daily orders, as tabs. Only confirmed pre-orders count in the prep quantity. | K10 | S (built 21 Sep) | `kitchen/pre-orders` |

The availability toggle (K13, built 21 Sep) is a *Mark unavailable / available* button and an *Unavailable* badge on each `/kitchen/prep` card, and the badge shows in the dashboard plan table. "Report shortage" (K12) will be a small control on `/kitchen/requirements`.

### 3.2 Inventory (`/inventory`, desktop-first)

| Route | Page | Stories | Tier | API calls |
|---|---|---|---|---|
| `/inventory` | Dashboard: status counts (OK, low, out), open alerts, 7-day need vs stock, top reorder suggestions, expiring-soon batches | I1, I8 | M1 | `dashboards/inventory`, `alerts` |
| `/inventory/stock` | Stock levels table (on hand, usable, status, last movement) with search and status filter; add or edit ingredient (modal) including min stock, reorder level, pack size | I2, I3, I4 | M1 | `stock/levels`, `ingredients` |
| `/inventory/movements` | Three forms (stock-in, stock-out, wastage) in tabs, and a movement history table with filters. **Adjustment** is a fourth tab (I14, built 21 Sep): counted quantity, date and a required reason, with the system on-hand and the difference shown live. | I5, I6, I13 | M1 | `stock/in`, `.../out`, `.../wastage`, `stock/movements`, `stock/batches` |
| `/inventory/forecast` | Ingredient demand for the next 7 days per ingredient, days of cover, "unknown" items | I7 | M1 | `recommendations/ingredient-forecast` |
| `/inventory/reorder` | Reorder suggestions with all terms of the calculation | I9 | M1 | `recommendations/reorder` |
| `/inventory/suppliers` | List, add, edit, deactivate suppliers; inactive ones cannot be chosen for new ingredients or orders | I10 | S (built 21 Sep) | `suppliers` |
| `/inventory/purchase-orders` | Order list with status filter; new order form; order detail with *Mark as sent*, *Receive stock* (per-line quantity, expiry, batch, cost; partial receipts) and *Cancel*. `/inventory/reorder` gains row tick-boxes and *Create purchase order* (one draft per supplier). | I11 | S (built 21 Sep) | `purchase-orders`, `recommendations/reorder` |
| `/inventory/expiry` | Expiry list (batches by expiry date) | I12 | S | `stock/batches` (page not built; batches are listed on `/inventory/movements` and the dashboard) |

### 3.3 Admin (`/admin`, desktop-first)

| Route | Page | Stories | Tier | API calls |
|---|---|---|---|---|
| `/admin` | Dashboard: 7/30-day sales, next-7-day forecast total, low-stock count, waste, alerts by severity, recent activity, "items without recipe" warning | A1 | M2 | `dashboards/admin` |
| `/admin/users` | User list, create, edit role, deactivate | A2, A3 | M2 | `users` |
| `/admin/catalog` | Menu items table with edit modal; "Recipe" button opens a recipe editor (ingredient rows with quantity, unit shown read-only) | A4, A5 | M2 | `menu-items`, `.../recipe`, `ingredients` |
| `/admin/data` | Tabs: Sales import, Holidays, Weather, Promotions. Import tabs use `sr-csv-import`; promotions use a form and a list | A14, A15 | M2 | `sales/import`, `holidays`, `weather`, `promotions` |
| `/admin/inventory` | Read-only inventory overview with tabs: Stock levels (status tiles and table), Ingredient demand (7 days), Batches and expiry, Recent movements (filters). Same endpoints as the inventory pages, so numbers match. | A10 | S (built 21 Sep) | `stock/levels`, `recommendations/ingredient-forecast`, `stock/batches`, `stock/movements` |
| `/admin/models` | Active model card (algorithm, trained date, hold-out metrics vs baseline), version list with Activate, **Train** and **Run forecast now** buttons, forecast run history with status and reason | A16, A9 | M2 | `model-versions`, `forecast-runs` |
| `/admin/monitor` | Tabs: **Sales** (A8, bar by day plus table), **Forecast** (A9, forecast vs actual line plus MAE/WAPE/bias table), **Waste** (A11, food and ingredient sections). Date range filter shared by all tabs. | A8, A9, A11 | M2 | `reports/sales`, `forecasts/accuracy`, `reports/waste` |
| `/admin/settings`, `/admin/inventory`, CSV buttons | Settings and alert configuration; read-only inventory overview; "Download CSV" on each monitor tab | A6, A7, A10, A13 | S | see API |

## 4. Wireframes (key screens)

**Kitchen prep card (360 px):**

```
+-----------------------------------+
| Chicken Burger        [Available] |
| Forecast 47.3  (+10% buffer)      |
| Pre-orders 0   Batch 6            |
| Recommended        54             |
| [ Accept 54 ]   [ Override ]      |
| Prepared so far: 24   [ + Add ]   |
| weather estimated                 |
+-----------------------------------+
```

After Accept the card shows "Accepted 54" with a grey Undo-by-override link. Override opens an inline quantity box and a required reason field.

**Kitchen dashboard (desktop):**

```
+---------------------------------------------------------------+
| Today Fri 25 Sep   [<] [Today] [>]                            |
| [To prepare: 10 items] [Prepared: 312/540] [Short: 2] [Alerts 3]|
+--------------------------------+------------------------------+
| Plan                            | Alerts                       |
| item  fcst rec final prepared   | ! Chicken short by 3.5 kg    |
| ...                             | ! Fried Chicken waste risk   |
+--------------------------------+------------------------------+
```

**Inventory dashboard:**

```
+---------------------------------------------------------------+
| Stock: [OK 14] [Low 4] [Out 1]    Open alerts: 5              |
+------------------------------+--------------------------------+
| Reorder now (top 5)          | Next 7 days: need vs stock     |
| Chicken   25 kg  Ceylon P.   |  bar per ingredient            |
| ...                          |                                |
+------------------------------+--------------------------------+
| Expiring soon: batch, qty, expiry (expired rows in red)        |
+---------------------------------------------------------------+
```

**Admin models page:**

```
+---------------------------------------------------------------+
| Active: v20260922-1  xgboost   trained 22 Sep                  |
| Hold-out (56 d): MAE 6.1 vs baseline 9.8  -> beats baseline    |
| [Train new model] [Run forecast now]                           |
+---------------------------------------------------------------+
| Versions: label | algorithm | MAE | WAPE | status | [Activate]  |
| Runs: time | as-of | status | reason | items                     |
+---------------------------------------------------------------+
```

## 5. Interaction rules

| Topic | Rule |
|---|---|
| Forms | Labels on every input; server errors (`422 fields`) shown under the field with the entered data kept (C4). Submit disables while saving; success shows a toast and refreshes the affected table. |
| Confirmations | Only where an action is hard to undo or overwrites: sales import commit, overwrite of an existing served record, model activation, user deactivation. |
| Loading | A spinner or skeleton row; never a blank page. |
| Empty | A sentence and a next step, for example "No forecast yet. Ask the administrator to run a forecast." |
| Errors | A dismissible banner with the API's message. A 500 shows "Something went wrong. Please try again" plus the request id. No stack traces (NFR3). |
| Status colour | Green ok, amber low or warning, red out or critical. **Every status also has a text label**, so meaning never depends on colour alone. |
| Numbers | Ingredient quantities show the unit; portions are integers; money is `LKR 1,234.50`. |
| Dates | Date inputs default to today (Colombo). Future dates are blocked for actual records (C4). |
| Touch | Kitchen buttons are at least 44 px high; number inputs use `inputmode="numeric"`. |
| Keyboard and a11y | Logical tab order, visible focus, `lang="en"`, buttons are `<button>`, modals trap focus (Bootstrap default). |
| Idle | After 30 minutes idle the next request returns 401 and the page redirects to login with a message (C3). |

## 6. Copy and empty-state strings (starting set)

| Situation | Text |
|---|---|
| Login error (any cause) | "Incorrect username or password." |
| Locked | "Too many attempts. Try again in a few minutes." |
| No forecast | "No forecast yet for this date." |
| Short history | "Not enough sales history to forecast this item." |
| Weather estimated | "Weather estimated (seasonal average)" |
| Baseline used | "Simple estimate (same day last week)" |
| Served above prepared | "Served is higher than prepared. Saved, and flagged for review." |
| Insufficient stock | "Only 4.2 kg usable stock is available." |
| Import result | "118 rows accepted, 2 rejected. Review the rejected rows, then confirm." |

## 7. Responsive and browser checks

- Widths tested: 360, 768, 1280 px on Chrome, Firefox and Edge (`TESTING.md` section 7).
- Kitchen `prep` and `record` render as cards (no table), so they need no responsive table handling. Other list pages use `.table-responsive` inside the container, and the page itself never scrolls sideways.
- Charts resize with their container (`responsive: true`); each chart has a title, axis labels with units, and the table beneath it shows the same numbers.

## 8. What is deliberately not built

Login-less kiosk mode, dark theme, i18n (English only, A11), print stylesheets, drag-and-drop, real-time push, offline mode, a PWA shell, a bespoke design system.

## 9. Visual design system (as built, 21 Sep 2026)

Display-only layer on top of the vendored Bootstrap; no data, API, route or business-logic change.

- **Shell:** dark left sidebar (off-canvas menu below 992 px) with brand, role chip, icon navigation and user/log-out block; sticky top bar with breadcrumb, the "Synthetic demo data" pill (text still comes from the `data_source_label` setting) and the alert bell.
- **Role accents** (one design system, colour set by `body[data-role]`): Administrator indigo, Food Production burnt orange, Inventory teal. Sidebar tint follows the role.
- **Tokens and components** are in `static/css/app.css` (CSS variables for colour, radius, shadow; semantic success/warning/danger/info colours are the same in every role). Shared Vue components in `components.js`: `sr-stat-tile` (icon, tone), `sr-status-badge`, `sr-alert-list` (severity icon and tag), `sr-empty` (icon), `sr-loading` (skeleton), `sr-icon`, and the Chart.js wrappers `sr-line-chart`, `sr-bar-chart`, `sr-doughnut-chart`.
- **Icons** are inline SVG from `static/js/icons.js`; no icon font, web font or CDN.
- **Charts added from existing endpoints only:** Admin dashboard (sales and waste trend from `/reports/sales` and `/reports/waste`; alerts by severity), Kitchen dashboard (forecast, recommended and prepared by item), Inventory dashboard (stock status). The Monitoring, forecast and need-versus-stock views keep their charts.
- **Login** is a split layout (product panel and form) that collapses to the form on tablets and phones; error pages share the same look.
