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

Since 14 Oct 2026 several of the pages below are tabs of one merged page, and their old addresses redirect to that tab; see section 11.

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
| `/kitchen/orders` | Pre-orders: list (#, date and pickup time, customer, item, quantity, status) with date and status filters; add, edit, confirm, complete, cancel, and a details panel (13 Oct 2026). Two tabs: **Pre-orders** and **Daily orders** (K10, built 21 Sep: the day's orders with a date control, add, edit, mark fulfilled or cancelled; internal record only, no effect on forecasts). Confirmed and completed pre-orders count in the prep quantity. | K10 | S (built 21 Sep) | `kitchen/pre-orders` |

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
| `/admin` | Dashboard (redesigned 13 Oct 2026, light theme with green accent): reporting period 7/30 days ending yesterday, with a note when only part of it has sales records and a synthetic-data note; KPI tiles portions sold, portions wasted, food waste rate (wasted / prepared, amber above the waste-risk limit) and low-stock ingredients; food demand forecast for today + 6 days as a bar chart labelled "Prediction" (total = sum of the 7 day values; missing days named), model, hold-out MAE/WAPE and last run underneath; sales and waste trend with every date on the axis (no records = gap, not zero); inventory alerts, one row per ingredient with Now (usable vs reorder level), Forecast (first shortfall) and Expiry; upcoming confirmed pre-orders with portions by item; alerts with Open and History tabs (bell target `#alerts`); recent activity as plain sentences from stored events (audit log, forecast runs, user stock movements) with user and repeat count; quick actions (Generate forecast, Manage BOM, View inventory, View reports); "items without recipe" and "no active model" warnings | A1 | M2 | `dashboards/admin`, `alerts` |
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

- **Menus are grouped** under short headings, with plain names (URLs unchanged; the menu itself was shortened again on 14 Oct 2026, section 11). Administrator: *Overview* (Dashboard, Reports, Inventory overview), *Forecasting* (Forecast models, Import data), *Setup* (Menu & recipes, Users, Settings). Food Production: *Today* (Dashboard, Demand forecast, Prep plan, Served & waste), *Ingredients* (Ingredient needs, Stock requests), *Orders* (Orders & pre-orders). Inventory & Procurement: *Stock* (Dashboard, Stock levels, Record stock, Kitchen requests), *Purchasing* (Ingredient demand, Reorder, Purchase orders, Suppliers). Defined in `utils/navigation.py`.
- **Dashboards** follow one order: summary tiles, the main work, then "Needs attention". Repeated numbers were removed (alerts doughnut, stock doughnut, kitchen bar chart, open-alerts tile on inventory). Alert lists load the full role list from `/alerts` after the dashboard call (never in parallel, so the alert check runs once) and show 5 (kitchen 3) with *Show all*; `sr-alert-list` takes an optional `limit`.
- **Admin "Forecast performance"** reads the active model's hold-out MAE and the `naive_lag7` baseline from `/model-versions`.
- **"Check alerts now"** moved from the admin dashboard to Settings > Alert types (same `POST /alerts/run`).
- **Prep plan:** the buffer, weather note and model are shown once in the page header; each card shows forecast and recommended, and the calculation opens under *How was this worked out?*. All actions are unchanged.
- **Served & waste:** four tabs (Served, Waste, Other use, Daily balance with ingredient usage); `#waste` etc. open a tab directly. All forms are unchanged.

## 11. Merged pages (14 Oct 2026)

Related pages became tabs of one page, so the menus have 14 entries instead of 23. No function was removed, and no API,
service rule, model, ML or database change was needed (the one service addition is `alert_service.visibility()`, a
read-only list of the existing alert rule).

| Role | Menu (heading: pages) | Tabs of a merged page |
|---|---|---|
| Administrator | *Overview*: Dashboard, Reports, Forecasting. *Setup*: Menu & recipes, Administration | **Reports** (`/admin/monitor`) gained Stock levels, Ingredient demand and Batches and expiry from the old Inventory overview (its Recent movements tab was already covered by Stock movements). **Forecasting** (`/admin/models`): Historical data, ML models, Forecast generation (since the final UI pass, section 12). **Administration** (`/admin/users`): Users, Settings & alerts, Role access |
| Food Production | *Today*: Dashboard, Plan & prepare, Served & waste. *Supplies & orders*: Ingredients, Orders & pre-orders | **Plan & prepare** (`/kitchen/prep`): Prep plan, 7-day forecast. **Ingredients** (`/kitchen/requirements`): Needs & shortages, Stock requests |
| Inventory & Procurement | *Today*: Dashboard, Kitchen requests. *Stock & buying*: Stock, Purchasing | **Stock** (`/inventory/stock`): Stock levels, Record stock. **Purchasing** (`/inventory/reorder`): Reorder, Ingredient demand, Purchase orders, Suppliers |

- **How it works.** `utils/navigation.py` holds the menus (`NAV_GROUPS`), the merged pages (`HUBS`: tab key, label and
  the existing page template) and the old addresses (`REDIRECTS`). A merged page keeps the URL of its first tab and
  takes `?tab=`; the controller renders that tab's template, which extends `hub.html` (page name and the tab strip).
  Tabs are plain links, so a tab can be bookmarked and Back works. A missing or unknown `?tab=` opens the first tab.
  Reports switches its tabs inside the page as before and now also reads `?tab=` and keeps it in the address.
- **Old addresses keep working.** `/admin/data`, `/admin/settings`, `/admin/inventory`, `/kitchen/forecast`,
  `/kitchen/stock-requests`, `/inventory/movements`, `/inventory/forecast`, `/inventory/purchase-orders` and
  `/inventory/suppliers` redirect (302) to their tab and keep their other query arguments (`?open=`, `?ingredient=&qty=`).
  The role guard runs before the redirect, so another role still gets 403.
- **Role access tab** (Administration): which role can open each menu page (read from the blueprint guard the server
  applies, not from the menu) and which roles receive each alert type (the same rule `GET /alerts` uses). Roles stay
  fixed (A8); the role of a user is changed on the Users tab.
- **Look.** The tab strip of a merged page is a segmented control (CSS section 13) so it is not confused with the
  underlined tabs inside a section (Reports, Import data, Orders, Served & waste). Each tab's own heading is now an `h2`.

## 12. Final UI pass (14 Oct 2026, branch `ui-final`)

Presentation only: templates, page scripts, CSS, the menu labels and one default-tab setting in `utils/navigation.py`.
No service, model, ML, migration, API or permission change (checked: `git diff` of those folders is empty, and 42 API
responses are identical between the base build and this one on copies of the same data).

- **One design language.** Every role now has the light sidebar, grey canvas and green accent that the administrator
  had; the role keeps its own colour on the role chip and avatar only (`--role`). CSS section 1 and 12.
- **One tab standard.** The main sections of a page are a segmented bar (`.hub-tabs`, `.sr-tabs`, `.nav-pills`, same
  look, selected section filled green); sub-sections use the underlined `.nav-tabs`. Orders and Served & waste moved to
  the segmented bar. On phones the underlined tabs scroll inside their bar.
- **Admin dashboard.** A one-line flow (sales history → forecast → prep plan → ingredient needs → stock & reorder),
  four summary tiles (Sales, Forecast demand next 7 days, Food waste, Inventory status), forecast and trend charts,
  *Needs attention* (alerts, Recommended actions), then pre-orders, activity, quick actions. The per-ingredient
  inventory table moved to Reports (its figures are on Stock levels, Ingredient demand, Batches and expiry).
- **Reports & Analytics** (renamed): the 10 reports under 4 groups (Sales; Forecasting; Inventory; Waste & Analytics),
  group bar plus sub-tabs; `?tab=` still opens any report directly.
- **Forecasting**: tabs in workflow order, Historical data → ML models → Forecast generation, with a numbered step
  strip; `/admin/models` still opens ML models (`DEFAULT_TAB`). All metrics and actions kept.
- **Menu & recipes**: summary chips, a full-width table, and the recipe (BOM) opens under its item, per portion and per
  batch, with Edit recipe. Daily availability is shown read-only (it stays a kitchen action).
- **Kitchen**: dashboard workflow steps (forecast → plan → prepare → record); Plan & prepare shows a comparison table at
  1200 px and wider (cards below), with a summary line; Ingredients lists short items first with counts.
- **Inventory**: dashboard workflow steps (check stock → kitchen requests → reorder → receive) and a plain intro on
  every tab.
- **Phones**: the Role access tables become a stacked list below 576 px.


## 13. Release check fixes (14 Oct 2026, branch `release-check`)

- **Served & waste, Served tab**: a real table (Item, Prepared, Waste, Served or sold) with a totals row and a link to
  Daily balance; the old grid let the Waste and Served headings run together.
- **Purchasing on phones** (below 576 px): Reorder, Ingredient demand, Purchase orders and Suppliers become card lists,
  so the suggested quantity, 7-day need, status and Edit / Open actions are in view without a sideways table; the
  working stays under "How was this worked out?" / "Need per day". Wider screens keep the tables. Only one view is
  rendered, so the checkboxes and ids stay unique.

## 14. Viva polish: the workflow everywhere (14 Oct 2026, branch `viva-polish`)

Presentation only. No service, ML, model, migration, API or permission change; the menus are unchanged.

- **Six-step workflow strip** (`sr-workflow` in `components.js`, CSS section 15) on the Admin, Kitchen and Inventory
  dashboards: Historical sales → ML demand forecast → Preparation recommendations → BOM & ingredient requirements →
  Inventory decisions → Food waste monitoring. Each step shows a figure from data the page already reads (admin also
  reads today's prep plan, requirements and reorder list; kitchen the daily summary and its stock requests; inventory
  the full reorder list; all read-only), says which role does it, and links to its page when the viewer may open it.
  Steps of other roles stay visible, muted. The strip replaces the dashboards' summary tiles (their figures are in it).
- **Step marker** in the top bar of every page that belongs to one step ("Step 3 of 6 · Preparation recommendations"),
  from `PAGE_STEP` in `utils/navigation.py`; dashboards and Reports & Analytics cover several steps and show none.
- **Admin chart**: recorded sales (line, last 7 days) and the 7-day ML forecast (bars) on one axis.
- **Reports & Analytics**: each group names the workflow step it covers. Short intros on Users and Settings.


## 15. Minimal pass: less wording, compact workflow (14 Oct 2026, branch `ui-minimal`)

Presentation only. No service, ML, model, migration, API, permission or navigation change.

- **Workflow strip** is one row of six on desktop (three below 1200 px, two on phones): number, title, figure and a
  short caption. The role that does a step moved to the step's tooltip; other roles' steps stay muted.
- **Repeated text removed**: the admin purpose paragraph and the synthetic-data note (the top-bar pill already says
  it), dashboard subtitles that restated the workflow, card subtitles that restated the heading, report group notes,
  quick-action descriptions, the login role strip.
- **Shortened, not removed**: every page intro (one line), formulas (prep quantity, reorder suggestion, waste rate,
  daily balance), alert behaviour, CSV formats, model metrics, the accuracy method note. Warnings and empty states keep
  their meaning; the partial-sales warning stays on the admin dashboard.

## 16. Role dashboards (14 Oct 2026, branch `role-dashboards`)

Each role has its own dashboard, built the same way: figures, then **Needs attention** (`sr-action-list`: the issue,
what the system recommends, one action button), then the detail. Pages, tabs, menus, permissions, ML and the database
are unchanged; `docs/PRESERVATION_CHECKLIST.md` lists every function and where it is.

- **Administrator:** workflow row (management view of the whole chain), Needs attention (management decisions),
  Forecasting performance (active model, hold-out MAE vs baseline, accuracy on the period), one chart for recorded sales,
  waste and the 7-day forecast, alerts, upcoming pre-orders, recent activity.
- **Kitchen:** forecast, to prepare, prepared, served / wasted; Needs attention; the day's pre-orders; plan; shortages;
  alerts.
- **Inventory:** usable stock, kitchen requests, short in 7 days, expiry; Needs attention; open kitchen requests;
  reorder; stock-out risk; expiring batches; alerts.
- Read-only additions to `dashboard_service`: `day` on the kitchen dashboard, `totals` and `requests` on the inventory
  dashboard, `accuracy` on the admin dashboard, all from existing service functions. Counts are no longer cut at the
  length of the list shown.

## 17. Simplification (14 Oct 2026, branch `simplify`)

Approved list M1-M8, R1, R2 (`docs/PRESERVATION_CHECKLIST.md` section 7): one Ask inventory action with two choices;
kitchen requests shown one step at a time (Approve, then Issue to kitchen; still two operations); no Start button (the
first prepared quantity starts an item); Served & waste as End of day + Daily balance; Reports with Stock & expiry and
Stock history (8 reports); Role access under Users; one word per operation (Food waste, Stock wastage, Issue to
kitchen); no step marker in the top bar; unused CSS and dashboard fields removed. CSS section 17.

## 18. Redesign (16 Oct 2026, branch `ux-redesign`)

One design system for every page (CSS section 25), the login page and the three dashboards. Front end only: no service,
API, permission, ML or database change. Every page keeps its buttons and API calls (`tests/api/test_preservation.py`).

- **Look:** Inter (vendored in `static/vendor/fonts`, SIL OFL 1.1, served from the app, so the CSP is unchanged) on a soft
  neutral canvas; white cards with a hairline border; green only for the main action on a page, the active menu entry and
  "good" states. Secondary buttons, page tabs and section tabs are neutral (white or a grey segmented control), so a
  colour always means something. Tables use sentence-case headers; toasts are one dark line with a coloured dot.
- **Shell:** the top bar shows where you are, the business date, the synthetic-data label and the alerts bell; the role is
  under the user's name at the bottom of the menu.
- **Figures:** `sr-stat-tile` gains `unit` (small text after the number) and `flag` (one status line in the tile's
  tone); the number itself is always dark, the tone shows in the icon and the flag.
- **Login:** one centred card, no imagery: brand, "Welcome back", username, password with show / hide, one Sign in button,
  the server's generic error and the Caps Lock hint. Field names, ids, CSRF token and checks are unchanged.
- **Administrator dashboard:** four figures (Sales, Forecast next 7 days, Ingredients low or out, Food waste); the sales,
  waste and forecast chart beside Forecasting performance (model and baseline hold-out error as two bars); Needs
  attention beside Restaurant today (kitchen preparation, ingredients for today, purchasing, pre-orders: what the
  six-step strip showed, read from the same endpoints); alerts beside Quick access and recent activity. The six-step
  strip (`sr-workflow`, CSS section 15) is removed.
- **Kitchen dashboard:** four figures (To prepare, Prepared with progress, Pre-orders, Served & waste); Needs attention
  only when something needs doing; the preparation plan beside ingredient shortages with Request stock; the day's
  pre-order list only when there are pre-orders; alerts.
- **Inventory dashboard:** four figures (Ingredients in stock, Kitchen requests, To reorder, Expiry); Needs attention
  beside open kitchen requests; one Ingredient requirements table (7-day need, usable stock, cover, the reorder
  suggestion and supplier) replaces the separate Reorder now and Stock-out risk lists; expiring batches; alerts.
- Alert messages show their stored ISO dates as "Fri 16 Oct" (display only).

## 19. Plan & prepare, second pass (16 Oct 2026, branch `prep-polish`)

Front end only; the prep formula, the API calls and the auto-approval on the first entry are unchanged.

- **One list for every screen** (a six-column row from 1280 px, a card below) instead of a table and a separate card
  template. Columns: Item, Recommended (with "forecast N"; the full calculation is the tooltip and is shown in the
  Change plan form), Planned (with Suggested / Approved / Changed), Prepared (with a bar), Remaining, Add prepared.
- **Consistent figures:** Remaining = planned − prepared for an unfinished item, never below 0; portions above the plan
  are shown as "+N extra"; a finished item shows Done (and "N short of plan" if it stopped below). The four summary
  figures are the sums of what the rows show. The kitchen dashboard's "still to prepare" uses the same rule.
- **Actions by state:** while cooking, an entry box (placeholder = what is left) and Add prepared; once the plan is
  reached, Finish preparation becomes the main button and "Add more" opens the box; a finished item has only its ⋯ menu.
  Change plan, Use new N, finishing below the plan, Reopen and Mark unavailable are in the row's ⋯ menu.
- **Over-preparation:** an entry that would take an item above its plan asks once in the row ("Adding 80 makes 80
  prepared, 10 more than the plan of 70"); finishing below the plan also asks once. Finishing at or above the plan
  needs no confirmation.
- **Undo last entry** (17 Oct 2026): the ⋯ menu offers "Undo last entry (N)" for the latest entry of an item today
  while it is not finished (reopen a finished item first). An in-row confirm says what changes ("Remove the entry of 300
  added at 12:02? Prepared goes from 312 to 12."). Only the latest entry can be undone, so one cook never removes
  another's newer entry; the plan and its approval stay as they are and the removed entry stays in the audit log.
- The six-column row starts at 1280 px (was 1200), where Add more, Finish preparation and ⋯ fit on one line.
- Labels: "How?" removed; "Auto-accepted" and "Accepted" are both "Approved" (the tooltip says how); Done replaces
  Completed on the dashboard; the dashboard tile and table say Planned, like this page. When every item is done the page
  points to Served & waste. A future date shows one note instead of a message on every row.

## 20. Live review fixes (17 Oct 2026, branch `ui-review-fixes`)

From the review of the live screens (SmartRestaurant_Live_UI_Review.pdf). Staging only until approved.

- **A1 One alert number.** The bell, the severity badges, the Open tab and "Show all" all count every unresolved alert,
  acknowledged or not (they disagreed: 25 vs 34). Acknowledging marks an alert as seen and dims it; it stays counted
  until its cause is fixed.
- **A2 One row per ingredient.** An ingredient that is low or out now and also short in the plan was two alerts; for
  admin and inventory it is now one row ("Chicken is critically low: 0 kg usable (minimum 20); short by 55.68 on Sat 17
  Oct"), acknowledged together. The kitchen, which sees only the projected alert, is unchanged. Quantities in alert
  messages lose padded decimals (66 pcs, not 66.00 pcs).
- **I1 Nothing left out silently.** An ingredient whose need is covered by an open purchase order is not suggested again
  (unchanged rule; a draft counts as on order), but it is now named: Purchasing lists it under "Already on order, so not
  suggested" with the order and its status ("PO #1 draft, not sent to the supplier yet"); the dashboard row shows "on
  order 200" and the draft; Needs attention says which shortage the draft covers. An ingredient without a supplier says
  "No supplier: set one".
- **I4 Real figures in every row.** The Ingredient requirements table is built by the server, so every row carries its
  7-day need (rows past the first ten used to show "–"); "below minimum stock" is said on desktop as on phones.
- **A3** Forecasting says the selection reason is from that version's own training run, shows each version's hold-out
  period, and points out a trained version with a lower error, noting when it was tested on a different period.
- **K1** Ingredients & requests: "Ask inventory" only on short rows; sufficient rows have a quiet "Ask" with the same
  two choices (Request stock, Report shortage).
- **I2** Stock levels: "540 pcs expired" under On hand, linking to Record stock (wastage).
- **I3** A request still open after its needed-by day is marked Overdue on the inventory list, the dashboard and the
  kitchen's list.
- **A4** On a phone the 14-day chart skips date labels (5 shown) instead of overlapping them; desktop keeps all 14.
- **I5** The request filter is wide enough for "All requests".

## 21. Final review fixes (17 Oct 2026, branch `final-review-fixes`)
From the final UI review of the staging screens (release cd07c48). Phones first; no function removed.
- **1, 2 Phone tables.** Ingredients & requests and Stock levels become one stacked row per ingredient below 768 px
  (`m-stack`): name and status, then the figures with their labels, then the action (Ask inventory on short rows; Edit).
  Nothing is hidden in a sideways scroll any more; the responsive smoke check now also fails when a stacked table
  scrolls inside its own box.
- **3 Purchasing on phones.** The order button is pinned to the bottom of the screen ("Create purchase order (3 items)")
  next to the ticks. The missing-forecast warning is one line on every screen, with the items behind a toggle.
- **4 Admin dashboard.** Low/out of stock and "run short within 7 days" are one Needs attention line; Restaurant today
  has one ingredients row (shortfall, with what inventory has to reorder) instead of two; Quick access keeps the three
  tasks that are not in the sidebar (Manage BOM, Run forecast, Import sales data). The Alerts card stays: the bell links
  to it.
- **5 Inventory dashboard.** Expiring soon lists only batches that are still usable and expire within 3 days; the
  batches already expired are one line ("Already expired: 12 batches"), their action stays in Needs attention. The
  Alerts card stays as the bell's target.
- **6 Plan & prepare cards.** When the plan equals the recommendation, the card shows one Planned box ("forecast 100"
  under it) instead of two equal boxes; the desktop table keeps both columns.
- **7 BOM overview.** Recipes are closed by default and open from the item name ("Open all recipes" opens every one);
  a search opens the items it finds.
- **8 Forecasting.** The numbered step cards are removed (the tabs lead to the same three sections); the model
  comparison is sorted by MAE, best first.
- **9 Dates and totals.** Reports show periods in the app's date style ("Sat 19 Sep", "Week of …", "Sep 2026") in the
  table and on the chart, and report totals from LKR 1,000 up without cents. Date pickers follow the browser's
  language (dd/mm/yyyy in a Sri Lankan or UK browser), which the app does not override.
