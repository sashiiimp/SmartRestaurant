<!-- Capture note (delete before submission): every file currently in docs/screenshots/ was taken BEFORE the UI redesign
     (top navigation bar). Figures 1-10 below must be re-captured from the current sidebar layout at 1280 px width. -->

# Milestone 1: User Interfaces and Navigation

## 1. Overview

SmartRestaurant is a web application with one interface per user role. The interfaces are server-rendered Flask pages with Vue components that read and write data through the REST API (`/api/v1`). The implementation has 17 role pages and one login page.

**Login and role routing.** Every user logs in on `/login` with a username and password. After a successful login the system redirects to the home page of the user's role (`/admin`, `/kitchen` or `/inventory`). The address `/` does the same. Access is restricted by role at page level: a signed-in user who requests another role's page receives an "Access denied" (403) page with a button back to their own dashboard, and an anonymous request is redirected to the login page. A session ends after 30 minutes without activity or when the user presses *Log out*.

**Common layout.** All role pages share one layout:

- **Sidebar:** brand, a role label, the role's navigation links (the current page is highlighted), the signed-in user's name, and the *Log out* button. Below 992 px width the sidebar becomes a menu opened from a button in the top bar.
- **Top bar:** breadcrumb (role / page), a "Synthetic demo data" label (text set in the administrator's Settings page), and an **Alerts** button showing the number of open alerts. The Alerts button opens the role's dashboard, where the alert list is displayed.
- **Dashboards** show summary tiles, charts and an alert list in which alerts can be acknowledged.

The three roles are named in the interface *Administrator*, *Food Production* and *Inventory & Procurement*.

---

## 2. Administrator

**Dashboard:** *System overview* (`/admin`). The Administrator's sidebar has seven entries: Dashboard, Monitoring, Models, Data, Menu & recipes, Users and Settings.

| Page (route) | Main purpose | Main actions |
|---|---|---|
| **Dashboard** (`/admin`) | Overview of sales, forecast, stock, waste, alerts and the forecasting model | Switch between last 7 and last 30 days; *Run alert check*; *Acknowledge* an alert; follow the tiles and links to Monitoring, Models, and Menu & recipes |
| **Monitoring** (`/admin/monitor`) | Review sales and revenue, forecast accuracy and waste over a chosen period | Choose the tab (Sales and revenue, Forecast accuracy, Waste); set From and To dates; group by day, week or month (sales and waste); *Download CSV* |
| **Models** (`/admin/models`) | Manage forecasting models and forecast runs | *Train new model*; *Run forecast now*; *Activate* a model version; view the active model, the model comparison table, the version list and the forecast-run history |
| **Data** (`/admin/data`) | Load the data the forecast depends on | Import CSV files for sales, holidays and weather (choose skip or overwrite for existing rows, *Check file*, then *Save* the accepted rows); on the Promotions tab, *Add promotion* and switch a promotion on or off |
| **Menu & recipes** (`/admin/catalog`) | Maintain the menu and item recipes | *Add menu item*; *Edit*; *Recipe* (add, remove and save ingredient lines); *Deactivate* or *Activate* an item |
| **Users** (`/admin/users`) | Manage user accounts | *Add user* (name, username, email, role, initial password); change a user's role; *Deactivate* or *Reactivate* |
| **Settings** (`/admin/settings`) | Configure thresholds and alerts | Edit the numeric thresholds and the data-source label; switch each alert type on or off; *Save settings* |

**Navigation.** All seven pages are reachable at any time from the sidebar. The dashboard adds direct links: the Portions sold and Food waste tiles and *Full report* open Monitoring; the Forecast tile opens Models; the warning banners link to Menu & recipes (*Add recipes*) and to Models (*Train and activate one*).

**Navigation flow (Administrator):**

```
Login → Dashboard → Monitoring → Models → Data → Menu & recipes → Users → Settings → Log out
                 └── Dashboard links: Monitoring, Models, Menu & recipes
```

---

## 3. Food Production Manager

**Dashboard:** *Kitchen* (`/kitchen`) for a selected date. The sidebar has five entries: Dashboard, Prep plan, Forecast, Ingredients, and Served & waste.

| Page (route) | Main purpose | Main actions |
|---|---|---|
| **Dashboard** (`/kitchen`) | Daily overview of the preparation plan | Change the date (previous day, next day, date picker, *Today*); read the tiles (items to prepare, prepared against planned, ingredient shortages, open alerts), the forecast/recommended/prepared chart, today's plan table and the shortage list; *Acknowledge* an alert |
| **Prep plan** (`/kitchen/prep`) | See what to prepare for each menu item and decide | For each item: read the forecast, safety buffer, batch size and recommended quantity; *Accept* the recommendation, or *Override* with a quantity and a required reason (*Save override*); add a prepared quantity (*+ Add*). Accept and Override are not offered for past dates |
| **Forecast** (`/kitchen/forecast`) | View the 7-day demand forecast | Change the start date; read the item-by-day table (`*` marks a simple estimate, `P` a Poya day); choose the item shown in the forecast chart |
| **Ingredients** (`/kitchen/requirements`) | Check ingredient needs against usable stock for the plan | Change the date; read required quantity, usable stock, status and shortage per ingredient; see items that cannot be calculated (no recipe or no forecast) |
| **Served & waste** (`/kitchen/record`) | Record end-of-day results | Enter served quantities per item and *Save served quantities* (with an *Overwrite* confirmation when a different value already exists); *Record waste* (item, quantity, reason, optional note) |

**Navigation.** All five pages are reachable from the sidebar. On the dashboard, the Items to prepare tile and *Open prep plan* open the Prep plan, and the Ingredient shortages tile opens Ingredients. Every Food Production page has a date control; on Forecast it sets the start of the 7-day window.

**Navigation flow (Food Production Manager), following the daily working sequence:**

```
Login → Dashboard → Forecast → Prep plan (Accept / Override, add prepared) → Ingredients → Served & waste → Log out
                 └── Dashboard links: Prep plan, Ingredients
```

---

## 4. Inventory & Procurement Manager

**Dashboard:** *Inventory and purchasing* (`/inventory`). The sidebar has five entries: Dashboard, Stock, Record stock, Ingredient demand and Reorder.

| Page (route) | Main purpose | Main actions |
|---|---|---|
| **Dashboard** (`/inventory`) | Overview of stock status, reorder needs, expiry and alerts | Read the tiles (Stock OK, Low, Out of stock, open alerts), the top five reorder suggestions, the 7-day need against usable stock, batches expiring soon, the stock-status chart and the alert list; *Acknowledge* an alert |
| **Stock** (`/inventory/stock`) | View stock levels and maintain ingredient settings | Search by name and filter by status; *Add ingredient*; *Edit* (name, unit, category, default supplier, minimum stock, reorder level, pack size, minimum order quantity, shelf life) |
| **Record stock** (`/inventory/movements`) | Record stock movements | Choose *Stock in* (quantity, received date, expiry date, batch number, unit cost), *Stock out* or *Wastage* (date and reason); view the latest 30 movements (filter by ingredient) and the batches in stock, earliest expiry first |
| **Ingredient demand** (`/inventory/forecast`) | See ingredient need for the next 7 days | Read-only table: usable stock, daily need, 7-day need, days of cover and the date the ingredient runs short |
| **Reorder** (`/inventory/reorder`) | See reorder suggestions and how each is calculated | Read-only table: supplier, lead time, need over lead time, safety stock, usable stock, on order, raw quantity, pack size and suggested order |

**Navigation.** All five pages are reachable from the sidebar. On the dashboard, the Stock OK, Low and Out of stock tiles and *View stock* open Stock, and *All suggestions* opens Reorder.

**Navigation flow (Inventory & Procurement Manager):**

```
Login → Dashboard → Stock → Ingredient demand → Reorder → Record stock (Stock in / out / Wastage) → Log out
                 └── Dashboard links: Stock, Reorder
```

---

## 5. Screenshots for the Milestone 1 report

Ten screenshots are recommended, three to four per role, taken at 1280 px width from the current interface, using the seeded synthetic data. The file names are those used by `tests/ui/smoke.py`. Figure 1 has no existing file name.

| Figure | Screenshot (file) | Caption |
|---|---|---|
| 1 | Login page (`login.png`, new) | **Figure 1:** Login page. All roles sign in here and are redirected to their own dashboard. |
| 2 | `a_dashboard.png` | **Figure 2:** Administrator dashboard (System overview) with summary tiles, sales and waste trend, alerts by severity, open alerts and model status. |
| 3 | `a_models.png` | **Figure 3:** Administrator Models page showing the active model, the model comparison table, versions and forecast runs. |
| 4 | `k_dashboard.png` | **Figure 4:** Food Production dashboard showing the daily plan, ingredient shortages and alerts. |
| 5 | `k_forecast.png` | **Figure 5:** Food Production 7-day demand forecast by menu item, with the forecast chart. |
| 6 | `k_prep.png` | **Figure 6:** Preparation plan with the recommended quantity per item and the Accept and Override actions. |
| 7 | `k_requirements.png` | **Figure 7:** Ingredient requirements against usable stock, with shortages highlighted. |
| 8 | `i_dashboard.png` | **Figure 8:** Inventory & Procurement dashboard showing stock status, reorder suggestions, expiring batches and alerts. |
| 9 | `i_movements.png` | **Figure 9:** Record stock page for stock in, stock out and wastage, with movement history and batches. |
| 10 | `i_reorder.png` | **Figure 10:** Reorder suggestions with the calculation shown for each ingredient. |

Other screenshots are available if space allows: `a_monitor_sales.png` and `a_monitor_forecast.png` (Monitoring), `a_data.png`, `a_catalog.png`, `a_users.png`, `i_stock.png`, `i_forecast.png`, `k_record.png` and `k_prep_after.png` (a plan after an item is accepted).
