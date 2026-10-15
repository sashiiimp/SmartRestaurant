<!-- Notes for the team (delete before submission):
     1. Every file currently in docs/screenshots/ was taken BEFORE the UI redesign (top navigation bar) and none exists for the
        pages added on 21 Sep 2026. All figures in section 5 must be captured again, at 1280 px width, from the live demo. -->

# Milestone 1: User Interfaces and Navigation

## 1. Overview

SmartRestaurant is a web application with one interface per user role. The interfaces are server-rendered Flask pages with Vue components that read and write data through the REST API (`/api/v1`). The implementation has 23 role pages (eight for the Administrator, seven for Food Production, eight for Inventory & Procurement) and one login page.

**Login and role routing.** Every user logs in on `/login` with a username and password. After a successful login the system redirects to the home page of the user's role (`/admin`, `/kitchen` or `/inventory`). The address `/` does the same. Access is restricted by role at page level: a signed-in user who requests another role's page receives an "Access denied" (403) page with a button back to their own dashboard, and an anonymous request is redirected to the login page. A session ends after 30 minutes without activity or when the user presses *Log out*.

**Common layout.** All role pages share one layout:

- **Sidebar:** brand, a role label, the role's navigation links (the current page is highlighted), the signed-in user's name, and the *Log out* button. Below 992 px width the sidebar becomes a menu opened from a button in the top bar.
- **Top bar:** breadcrumb (role / page), a "Synthetic demo data" label (text set in the administrator's Settings page), and an **Alerts** button showing the number of open alerts. The Alerts button opens the role's dashboard, where the alert list is displayed.
- **Dashboards** show summary tiles, charts and an alert list in which alerts can be acknowledged.

The three roles are named in the interface *Administrator*, *Food Production* and *Inventory & Procurement*.

---

## 2. Administrator

**Dashboard:** *System overview* (`/admin`). The Administrator's sidebar has eight entries: Dashboard, Monitoring, Inventory, Models, Data, Menu & recipes, Users and Settings.

| Page (route) | Main purpose | Main actions |
|---|---|---|
| **Dashboard** (`/admin`) | Overview of sales, forecast, stock, waste, alerts and the forecasting model | Switch between last 7 and last 30 days; *Run alert check*; *Acknowledge* an alert; follow the tiles and links to Monitoring, Models, and Menu & recipes |
| **Monitoring** (`/admin/monitor`) | Review sales, forecasts, inventory and waste over a chosen period | Choose a tab: *Sales and revenue*, *Demand forecast* (next 7 days per menu item, from a chosen first day), *Forecast accuracy* (filter by menu item), *Analytics* (weekday demand, holiday and promotion days, forecast error and waste rate over time), *Inventory* (closing stock of one ingredient day by day), *Stock movements* (filter by ingredient and type), *Waste*; set From and To dates; group by day, week or month (sales and waste); *Download CSV* on every tab except Demand forecast and Analytics |
| **Inventory** (`/admin/inventory`) | Read-only overview of stock and predicted ingredient demand | Choose a tab: *Stock levels* (status tiles, table, *Download stock levels (CSV)*), *Ingredient demand* (7 days), *Batches and expiry*, *Recent movements* (filter by ingredient and type) |
| **Models** (`/admin/models`) | Manage forecasting models and forecast runs | *Train new model*; *Run forecast now*; *Activate* a model version; view the active model, the model comparison table, the version list and the forecast-run history |
| **Data** (`/admin/data`) | Load the data the forecast depends on | Import CSV files for sales, holidays and weather (choose skip or overwrite for existing rows, *Check file*, then *Save* the accepted rows); on the Promotions tab, *Add promotion* and switch a promotion on or off |
| **Menu & recipes** (`/admin/catalog`) | Maintain the menu and item recipes | *Add menu item*; *Edit*; *Recipe* (add, remove and save ingredient lines); *Deactivate* or *Activate* an item |
| **Users** (`/admin/users`) | Manage user accounts | *Add user* (name, username, email, role, initial password); change a user's role; *Deactivate* or *Reactivate* |
| **Settings** (`/admin/settings`) | Configure the restaurant, thresholds and alerts | Edit the **restaurant information** (name, address, contact, opening days and hours; the name shows in the sidebar) and *Save restaurant information*; edit the numeric thresholds and the data-source label; switch each alert type on or off; *Save settings* |

**Navigation.** All eight pages are reachable at any time from the sidebar. The dashboard adds direct links: the Portions sold and Food waste tiles and *Full report* open Monitoring; the Forecast tile opens Models; the warning banners link to Menu & recipes (*Add recipes*) and to Models (*Train and activate one*). The Inventory and Monitoring pages let the Administrator read, but not change, stock and movement records; purchase orders, kitchen requests and suppliers are handled by the other two roles and have no Administrator page.

**Navigation flow (Administrator):**

```
Login → Dashboard → Monitoring → Inventory → Models → Data → Menu & recipes → Users → Settings → Log out
                 └── Dashboard links: Monitoring, Models, Menu & recipes
```

---

## 3. Food Production Manager

**Dashboard:** *Kitchen* (`/kitchen`) for a selected date. The sidebar has seven entries: Dashboard, Prep plan, Forecast, Orders, Ingredients, Stock requests, and Served & waste.

| Page (route) | Main purpose | Main actions |
|---|---|---|
| **Dashboard** (`/kitchen`) | Daily overview of the preparation plan | Change the date (previous day, next day, date picker, *Today*); read the tiles (items to prepare, prepared against planned, ingredient shortages, open alerts), the forecast/recommended/prepared chart, today's plan table (items marked unavailable carry a badge) and the shortage list; *Acknowledge* an alert |
| **Prep plan** (`/kitchen/prep`) | See what to prepare for each menu item and decide | For each item: read the forecast, safety buffer, confirmed pre-orders, batch size and recommended quantity; *Accept* the recommendation, or *Override* with a quantity and a required reason (*Save override*); add a prepared quantity (*+ Add*); *Mark unavailable* or *Mark available*. Accept and Override are not offered for past dates |
| **Forecast** (`/kitchen/forecast`) | View the 7-day demand forecast | Change the start date; read the item-by-day table (`*` marks a simple estimate, `P` a Poya day); choose the item shown in the forecast chart |
| **Orders** (`/kitchen/orders`) | Keep the day's orders and the customer pre-orders | *Pre-orders* tab: filter by dates and status; *Add pre-order* (item, date, quantity, note, pending or confirmed); *Confirm*, *Edit* or *Cancel*. Only confirmed pre-orders raise the recommended preparation quantity. *Daily orders* tab: change the date; *Add order* (item, quantity, note; for today or an earlier day); *Edit*, mark *Fulfilled* or *Cancel* an open order. Daily orders are an internal record and change no forecast |
| **Ingredients** (`/kitchen/requirements`) | Check ingredient needs against usable stock for the plan | Change the date; read required quantity, usable stock, status and shortage per ingredient; see items that cannot be calculated (no recipe or no forecast); *Request stock* on a short row (opens a new stock request with the missing quantity filled in); *Report shortage* on any row (tells the inventory manager the store holds less than the system says) |
| **Stock requests** (`/kitchen/stock-requests`) | Ask the inventory section for ingredients and follow the answer | *New request* (needed-by date, note, ingredient lines); filter by status; read each request's status, issued quantities and the reject reason; *Cancel request* while it is pending |
| **Served & waste** (`/kitchen/record`) | Record end-of-day results and ingredient use | **Daily record** tab: one table, one row per item (Prepared, Sold / served, Wasted, Other use, Balance = prepared - served - wasted - other use), with a status line (served n of m, waste, other use, rows to check, unsaved). Type served quantities in the rows and *Save served quantities* (with an *Overwrite* confirmation when a different value already exists). *Waste / other* opens a panel under the row: *Record waste* (portions, reason, optional note; adds to the day) and *Record other use* (use type, portions, note; one figure per type, *Change* or *Clear*). Negative balances and served or waste above prepared are marked in red. **Ingredient usage** tab: expected use = portions prepared x the admin's recipe (bill of materials); clicking the figure shows the calculation per item (*Show calculations* for all). Confirm actual use with *Matches* (records the expected amount), *Confirm all as expected*, or type the amount (with its unit) and *Save*; the difference shows in the unit and in percent (equal, over, under). *Clear*, add another ingredient. Usage figures never change the stock |

**Navigation.** All seven pages are reachable from the sidebar. On the dashboard, the Items to prepare tile and *Open prep plan* open the Prep plan, and the Ingredient shortages tile opens Ingredients. On Ingredients, *Request stock* leads to Stock requests. The Dashboard, Prep plan, Forecast, Ingredients and Served & waste pages have a date control (on Forecast it sets the start of the 7-day window); Orders and Stock requests use their own filters.

**Navigation flow (Food Production Manager), following the daily working sequence:**

```
Login → Dashboard → Forecast → Orders (pre-orders, daily orders) → Prep plan (Accept / Override, availability, add prepared)
      → Ingredients (Request stock / Report shortage) → Stock requests → Served & waste (served, waste, ingredient usage) → Log out
                 └── Dashboard links: Prep plan, Ingredients        Ingredients link: Stock requests
```

---

## 4. Inventory & Procurement Manager

**Dashboard:** *Inventory and purchasing* (`/inventory`). The sidebar has eight entries: Dashboard, Stock, Record stock, Ingredient demand, Reorder, Purchase orders, Kitchen requests and Suppliers.

| Page (route) | Main purpose | Main actions |
|---|---|---|
| **Dashboard** (`/inventory`) | Overview of stock status, reorder needs, expiry, kitchen requests and alerts | Read the tiles (Stock OK, Low, Out of stock, open alerts), the top five reorder suggestions, the 7-day need against usable stock, batches expiring soon, the stock-status chart, the number of kitchen requests waiting and the alert list; *Acknowledge* an alert |
| **Stock** (`/inventory/stock`) | View stock levels, maintain ingredient settings and check the data | Search by name and filter by status; *Add ingredient*; *Edit* (name, unit, category, default supplier, minimum stock, reorder level, pack size, minimum order quantity, shelf life); *Run data check* (compares the stored stock with the recorded movements and lists expired stock; it changes nothing) |
| **Record stock** (`/inventory/movements`) | Record stock movements | Choose *Stock in* (quantity, received date, expiry date, batch number, unit cost), *Stock out*, *Wastage* (date and reason) or *Adjustment* (counted quantity, date and a required reason; the page shows the system quantity and the difference); view the latest 30 movements (filter by ingredient) and the batches in stock, earliest expiry first |
| **Ingredient demand** (`/inventory/forecast`) | See ingredient need for the next 7 days | Read-only table: usable stock, daily need, 7-day need, days of cover and the date the ingredient runs short |
| **Reorder** (`/inventory/reorder`) | See reorder suggestions, how each is calculated, and order them | Read supplier, lead time, need over lead time, safety stock, usable stock, on order, raw quantity, pack size and suggested order; tick the ingredients (those with a supplier) and *Create purchase order* (one draft order per supplier, using the suggested quantities) |
| **Purchase orders** (`/inventory/purchase-orders`) | Create and follow purchase orders | Filter by status; *New purchase order* (supplier, expected date, notes, ingredient lines with quantity and optional unit cost); open an order to *Mark as sent* (by hand, nothing is transmitted), *Receive stock* (per line: quantity, expiry date, batch number, unit cost, date received; partial receipts allowed) or *Cancel order* (only while nothing has been received) |
| **Kitchen requests** (`/inventory/requests`) | Answer the kitchen's ingredient requests | Filter by status (pending requests first); open a request to *Approve*, *Reject* (a reason is required and shown to the kitchen) or *Issue stock* (per-line quantity against the usable stock, with the option to close a partly issued request) |
| **Suppliers** (`/inventory/suppliers`) | Maintain supplier details | *Add supplier* (name, contact, phone, email, lead time, notes); *Edit*; *Deactivate* or *Activate* (an inactive supplier cannot be chosen for new ingredients or orders) |

**Navigation.** All eight pages are reachable from the sidebar. On the dashboard, the Stock OK, Low and Out of stock tiles and *View stock* open Stock, *All suggestions* opens Reorder, and *Open requests* opens Kitchen requests. On Reorder, *Create purchase order* leads to Purchase orders (a single new order opens directly).

**Navigation flow (Inventory & Procurement Manager), following the working sequence:**

```
Login → Dashboard → Kitchen requests (Approve / Reject / Issue) → Reorder → Purchase orders (Send, Receive)
      → Record stock (Stock in / out / Wastage / Adjustment) → Stock (Data check) → Suppliers → Log out
                 └── Dashboard links: Stock, Reorder, Kitchen requests        Reorder link: Purchase orders
```

---

## 5. Screenshots for the Milestone 1 report

Nineteen figures are recommended, grouped by role in the order a reader meets the system. Sixteen are core; the three marked *optional* can be dropped if space is short (renumber the rest). Take them at 1280 px width from the running demo with a full-page capture, and keep the "Synthetic demo data" label in view. Old files in `docs/screenshots/` must not be used: they show the previous layout, and there are none for the new pages.

**Capture them during one run of the demo script** (`DEMO_NEW_FEATURES.md`): the states below occur naturally in that order, and no extra data has to be invented. The "Demo step" column says when to press the key.

| Fig | Role and page | Must be visible (set the screen up like this) | Demo step | Caption | |
|---|---|---|---|---|---|
| 1 | Logged out, `/login` | The whole split layout with the "Welcome back" form. | none | **Figure 1:** Login page. Every role signs in here and is sent to its own dashboard. | core |
| 2 | Administrator, `/admin` | Sidebar with all eight links, the four tiles, sales and waste trend, alerts chart, alert list, model card. | after 3.1 | **Figure 2:** Administrator dashboard (System overview). | core |
| 3 | Administrator, `/admin/models` | Active model card with the comparison table, Train and Run buttons (not pressed), versions and forecast runs. | any | **Figure 3:** Forecast models page: the active model, the comparison against the baselines, versions and forecast runs. | core |
| 4 | Administrator, `/admin/inventory` | *Stock levels* tab: the four status tiles, the table and the *Download stock levels (CSV)* button. | 3.2 | **Figure 4:** Read-only inventory overview for the Administrator (stock levels, ingredient demand, batches, movements). | core |
| 5 | Administrator, `/admin/monitor`, **Analytics** tab | Both bar charts and both line charts, the period and data-source line, and the "does not prove" note. | 3.5 | **Figure 5:** Analytics: demand by weekday, holiday and promotion days against ordinary days, forecast error and waste rate over time. | core |
| 6 | Administrator, `/admin/settings` | The **Restaurant information** card filled in, and the restaurant name showing in the sidebar. | 3.8 | **Figure 6:** Restaurant information and settings. | optional |
| 7 | Food Production, `/kitchen` | Sidebar with seven links, four tiles, the chart, today's plan table, shortages and alerts. | before 1.1 | **Figure 7:** Food Production dashboard: the day's plan, ingredient shortages and alerts. | core |
| 8 | Food Production, `/kitchen/forecast` | Model and last-run line, the item-by-day table with the `*` and `P` legend, the chart with the item selector. | any | **Figure 8:** Seven-day demand forecast by menu item. | core |
| 9 | Food Production, `/kitchen/prep` | Item cards with *Confirmed pre-orders*, recommended quantity, Accept and Override, and one card showing the red *Unavailable* badge with its *Mark available* button. | 1.1 | **Figure 9:** Preparation plan with the recommendation, pre-orders and the availability control. | core |
| 10 | Food Production, `/kitchen/orders` | *Pre-orders* tab with two rows: the pending one and the confirmed one (Chicken Burger, 120). | 1.4 | **Figure 10:** Orders: pre-orders (confirmed ones raise the preparation quantity) and, on the second tab, daily orders. | core |
| 11 | Food Production, `/kitchen/requirements` | The Chicken row in red (short by 9.28 kg) with *Request stock* and *Report shortage*, other rows sufficient. | 1.7 | **Figure 11:** Ingredient requirements against usable stock, with shortages highlighted and the request and report actions. | core |
| 12 | Food Production, `/kitchen/stock-requests` | Two request cards: one *Pending* and one *Rejected* showing the reason. Capture after Scene 2 step 2. | after 2.2 | **Figure 12:** Kitchen stock requests with their status and the inventory manager's reject reason. | core |
| 13 | Food Production, `/kitchen/record` | The **Ingredient usage** card with one row saved (expected, actual, +0.22 difference, note). | 1.6 | **Figure 13:** Ingredient usage: expected use (prepared x recipe) against the amount actually used. | optional |
| 14 | Inventory & Procurement, `/inventory` | Sidebar with eight links, the four tiles, the **Kitchen requests** card showing a count, reorder table, alerts including the Potato shortage report. | 2.1 | **Figure 14:** Inventory & Procurement dashboard with stock status, reorder suggestions, kitchen requests and alerts. | core |
| 15 | Inventory & Procurement, `/inventory/movements`, **Adjustment** tab | The tab open with the ingredient chosen, *System on hand* and the live *difference*, and the movement history beside it. | 2.8 | **Figure 15:** Record stock, with the Adjustment tab (counted quantity against the system quantity, reason required). | core |
| 16 | Inventory & Procurement, `/inventory/reorder` | Both rows ticked and the *Create purchase orders (2 suppliers)* button. Take it before pressing the button. | 2.4 | **Figure 16:** Reorder suggestions with the calculation shown, and purchase orders created per supplier. | core |
| 17 | Inventory & Procurement, `/inventory/purchase-orders` | The Chicken order open, status *Partially received*, lines ordered, received and outstanding, plus the order list beneath. | 2.5 | **Figure 17:** Purchase orders: status, received and outstanding quantities, and stock receipt. | core |
| 18 | Inventory & Procurement, `/inventory/requests` | A request open in the detail card with the *Issue stock* form (per-line quantity, usable stock), and the request list beneath. | 2.3, before pressing Issue | **Figure 18:** Kitchen requests handled by the inventory manager: approve, reject with a reason, or issue stock. | core |
| 19 | Inventory & Procurement, `/inventory/suppliers` | Supplier table with one *Inactive* supplier. | 2.10 | **Figure 19:** Supplier management. | optional |

File names: `fig01_login.png` to `fig19_suppliers.png` (for example `fig10_kitchen_orders.png`), so they line up with the captions.

**Also available if there is room:** the Stock page with the **Data check** panel showing "No problems found" (2.9); Monitoring *Inventory* (closing stock trend) and *Stock movements* tabs with the linked `purchase_order #` and `stock_request #` references (3.6, 3.7); the Monitoring *Demand forecast* tab (3.3).
