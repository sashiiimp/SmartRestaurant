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
| `/kitchen` | Dashboard: preparation progress, ingredient shortages and open alerts tiles; today's plan table (forecast, to prepare, prepared bar, status); shortages with *Request stock*; top 3 alerts; buttons to Prep plan and Served & waste | K1 | M1 | `dashboards/kitchen`, `alerts` |
| `/kitchen/forecast` | 7-day forecast per item (table, line chart for the selected item); "No forecast yet" states | K2 | M1 | `forecasts` |
| `/kitchen/prep` | **The core screen.** One card per item: forecast, buffer, pre-orders, recommended, Accept / Override (qty and reason), and "prepared so far" with a quick add; since 9 Oct 2026 (K4) a status badge (Planned, In progress, Done), a progress bar of prepared against the plan and *Start*, *Mark done* and *Reopen* buttons; Accept and Override are hidden once an item is done | K3, K4, K5 | M1 | `recommendations/prep`, `.../decisions`, `.../status`, `kitchen/prepared` |
| `/kitchen/record` | End-of-day entry: served quantity per item; record waste (item, qty, reason); **Ingredient usage** card (K8, built 21 Sep): expected use = prepared x recipe, an optional actual amount per ingredient with the difference, save, clear, add another ingredient; never changes stock; since 9 Oct 2026 (K14) an **Other food use** card under Record waste (item, use type, portions, note, list with Clear) and a full-width **Daily balance** table (prepared, served, waste, other use, unaccounted; negative rows highlighted) | K6, K7, K8, K14 | M1 | `kitchen/daily-summary`, `sales/served`, `kitchen/waste`, `kitchen/food-usage` |
| `/kitchen/requirements` | Ingredient requirements for the day, shortage rows highlighted, "cannot compute" list | K9 | M1 | `recommendations/requirements` |
| `/kitchen/stock-requests` | Request ingredients from the inventory section (needed-by date, note, ingredient lines; can be pre-filled from a short row on `/kitchen/requirements`); list with status, issued quantities, the reject reason, and *Cancel* while pending | K11 | S (built 21 Sep) | `kitchen/stock-requests` |
| `/kitchen/orders` | Pre-orders: list with date, status and item filters; add, edit, confirm, cancel. Two tabs: **Pre-orders** and **Daily orders** (K10, built 21 Sep: the day's orders with a date control, add, edit, mark fulfilled or cancelled; internal record only, no effect on forecasts). Only confirmed pre-orders count in the prep quantity. | K10 | S (built 21 Sep) | `kitchen/pre-orders` |

The availability toggle (K13, built 21 Sep) is a *Mark unavailable / available* button and an *Unavailable* badge on each `/kitchen/prep` card, and the badge shows in the dashboard plan table. "Report shortage" (K12, built 21 Sep) is a button on every row of `/kitchen/requirements`; the same page offers *Request stock* on short rows.

### 3.2 Inventory (`/inventory`, desktop-first)

| Route | Page | Stories | Tier | API calls |
|---|---|---|---|---|
| `/inventory` | Dashboard: low, out, expiring-in-3-days and kitchen-request tiles; top 5 reorders; stock-out risk (only ingredients whose 7-day need is above usable stock); 5 expiring batches; top 5 alerts; buttons to Record stock and Reorder | I1, I8 | M1 | `dashboards/inventory`, `alerts` |
| `/inventory/stock` | Stock levels table (on hand, usable, status, last movement) with search and status filter; add or edit ingredient (modal) including min stock, reorder level, pack size | I2, I3, I4 | M1 | `stock/levels`, `ingredients` |
| `/inventory/movements` | Three forms (stock-in, stock-out, wastage) in tabs, and a movement history table with filters. The Stock page also has a **Data check** panel (I16, built 21 Sep). **Adjustment** is a fourth tab (I14, built 21 Sep): counted quantity, date and a required reason, with the system on-hand and the difference shown live. | I5, I6, I13 | M1 | `stock/in`, `.../out`, `.../wastage`, `stock/movements`, `stock/batches` |
| `/inventory/forecast` | Ingredient demand for the next 7 days per ingredient, days of cover, "unknown" items | I7 | M1 | `recommendations/ingredient-forecast` |
| `/inventory/reorder` | Reorder suggestions with all terms of the calculation | I9 | M1 | `recommendations/reorder` |
| `/inventory/suppliers` | List, add, edit, deactivate suppliers; inactive ones cannot be chosen for new ingredients or orders | I10 | S (built 21 Sep) | `suppliers` |
| `/inventory/purchase-orders` | Order list with status filter; new order form; order detail with *Mark as sent*, *Receive stock* (per-line quantity, expiry, batch, cost; partial receipts) and *Cancel*. `/inventory/reorder` gains row tick-boxes and *Create purchase order* (one draft per supplier). | I11 | S (built 21 Sep) | `purchase-orders`, `recommendations/reorder` |
| `/inventory/requests` | Kitchen requests: pending first; open one to *Approve*, *Reject* (reason) or *Issue stock* (per-line quantity against usable stock, optional close); the inventory dashboard shows a pending count | I15 | S (built 21 Sep) | `stock-requests` |
| `/inventory/expiry` | Expiry list (batches by expiry date) | I12 | S | `stock/batches` (page not built; batches are listed on `/inventory/movements` and the dashboard) |

### 3.3 Admin (`/admin`, desktop-first)

| Route | Page | Stories | Tier | API calls |
|---|---|---|---|---|
| `/admin` | Dashboard: 7/30-day sales, waste, low-stock count and next-7-day forecast tiles; sales and waste trend; forecast performance (active model's hold-out error vs the naive baseline); top 5 alerts with severity counts; management links; 10 recent activities in plain English (5 shown); "items without recipe" warning | A1 | M2 | `dashboards/admin` |
| `/admin/users` | User list, create, edit role, deactivate | A2, A3 | M2 | `users` |
| `/admin/catalog` | Menu items table with edit modal; "Recipe" button opens a recipe editor (ingredient rows with quantity, unit shown read-only) | A4, A5 | M2 | `menu-items`, `.../recipe`, `ingredients` |
| `/admin/data` | Tabs: Sales import, Holidays, Weather, Promotions. Import tabs use `sr-csv-import`; promotions use a form and a list | A14, A15 | M2 | `sales/import`, `holidays`, `weather`, `promotions` |
| `/admin/settings` (addition) | A **Restaurant information** card (name, address, contact, opening days and hours; the name shows in the sidebar) above the thresholds and alert switches | A6 | S (built 21 Sep) | `restaurant` |
| `/admin/inventory` | Read-only inventory overview with tabs: Stock levels (status tiles and table), Ingredient demand (7 days), Batches and expiry, Recent movements (filters). Same endpoints as the inventory pages, so numbers match. | A10 | S (built 21 Sep) | `stock/levels`, `recommendations/ingredient-forecast`, `stock/batches`, `stock/movements` |
| `/admin/models` | Active model card (algorithm, trained date, hold-out metrics vs baseline), version list with Activate, **Train** and **Run forecast now** buttons, forecast run history with status and reason | A16, A9 | M2 | `model-versions`, `forecast-runs` |
| `/admin/monitor` | Tabs: **Sales** (A8), **Demand forecast** (A9, next-7-day table per item with totals and a chart), **Forecast accuracy** (A9, forecast vs actual line plus MAE/WAPE/bias table, with an item filter), **Analytics** (A12, built 21 Sep: demand by weekday, holiday and promotion days against ordinary days, forecast error and waste rate over time; range and data source stated, no CSV), **Inventory** (A13, closing stock per ingredient day by day), **Stock movements** (A13, filters by ingredient and type), **Waste** (A11, food and ingredient sections); CSV on every tab except Demand forecast and Analytics. Date range filter shared by all tabs. | A8, A9, A11 | M2 | `reports/sales`, `forecasts/accuracy`, `reports/waste` |
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

**Kitchen dashboard (desktop, simplified 11 Oct 2026):**

```
+---------------------------------------------------------------+
| Today's kitchen  Mon 12 Oct   [<][date][>][Today] [Open prep plan] [Record served & waste] |
| [Preparation progress 52% ====    ] [Shortages 1] [Alerts 5]  |
+--------------------------------+------------------------------+
| Today's plan                    | Ingredient shortages          |
| item  forecast  to prepare      |  Chicken short by 13.48 kg    |
|       prepared (bar)  status    |  [Request stock]              |
|                                 | Alerts (top 3, Show all)      |
+--------------------------------+------------------------------+
```

**Inventory dashboard (simplified 11 Oct 2026):**

```
+---------------------------------------------------------------+
| Inventory  Mon 12 Oct                 [Record stock] [Reorder] |
| [Low 2: 18 of 20 OK] [Out 0] [Expiring in 3 days] [Kitchen requests] |
+------------------------------+--------------------------------+
| Reorder now (top 5)          | Needs attention                |
| Stock-out risk, next 7 days  |  top 5 alerts, Show all        |
|  one bar per at-risk item    |                                |
| Expiring soon (5)            |                                |
+------------------------------+--------------------------------+
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
- **Charts added from existing endpoints only:** Admin dashboard (sales and waste trend from `/reports/sales` and `/reports/waste`). Since 11 Oct 2026 the kitchen and inventory dashboards have no charts (their charts repeated the tables next to them); the Reports, forecast and need-versus-stock pages keep theirs.
- **Login** is a split layout (product panel and form) that collapses to the form on tablets and phones; error pages share the same look.

## 10. Simplified dashboards and menus (11 Oct 2026)

Display-only change after a UI audit; no API, service, model, ML or database change.

- **Menus are grouped** under short headings, with plain names (URLs unchanged). Administrator: *Overview* (Dashboard, Reports, Inventory overview), *Forecasting* (Forecast models, Import data), *Setup* (Menu & recipes, Users, Settings). Food Production: *Today* (Dashboard, Demand forecast, Prep plan, Served & waste), *Ingredients* (Ingredient needs, Stock requests), *Orders* (Orders & pre-orders). Inventory & Procurement: *Stock* (Dashboard, Stock levels, Record stock, Kitchen requests), *Purchasing* (Ingredient demand, Reorder, Purchase orders, Suppliers). Defined in `utils/navigation.py`.
- **Dashboards** follow one order: summary tiles, the main work, then "Needs attention". Repeated numbers were removed (alerts doughnut, stock doughnut, kitchen bar chart, open-alerts tile on inventory). Alert lists load the full role list from `/alerts` after the dashboard call (never in parallel, so the alert check runs once) and show 5 (kitchen 3) with *Show all*; `sr-alert-list` takes an optional `limit`.
- **Admin "Forecast performance"** reads the active model's hold-out MAE and the `naive_lag7` baseline from `/model-versions`.
- **"Check alerts now"** moved from the admin dashboard to Settings > Alert types (same `POST /alerts/run`).
- **Prep plan:** the buffer, weather note and model are shown once in the page header; each card shows forecast and recommended, and the calculation opens under *How was this worked out?*. All actions are unchanged.
- **Served & waste:** four tabs (Served, Waste, Other use, Daily balance with ingredient usage); `#waste` etc. open a tab directly. All forms are unchanged.

