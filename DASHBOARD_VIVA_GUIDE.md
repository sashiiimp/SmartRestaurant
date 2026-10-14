# Admin Dashboard: viva guide

SmartRestaurant, CSE5015 final project (Team ForeSight). This guide covers the Administrator dashboard at `/admin`, as redesigned on 13 Oct 2026 (branch `dashboard-redesign`).

> **Second pass, 13 Oct 2026 (branch `system-integration`):** the Inventory alerts card now has one row per ingredient with **Now / Forecast / Expiry** columns, there is an **Upcoming confirmed pre-orders** card, the Alerts card has **Open / History** tabs, Recent activity shows plain sentences with the user, and the forecast total is the sum of the 7 day values. Pre-orders, BOM, waste and the full system are explained in `SMARTRESTAURANT_VIVA_GUIDE.md` (sections 6 to 10).

The figures quoted as examples come from the **staging copy** of the synthetic demo data (sales recorded up to 8 Oct 2026, viewed on 13 Oct 2026). On the live site the numbers will differ, but the meaning and the formulas are the same.

---

## 1. සරල සිංහල පැහැදිලි කිරීම (Simple explanation in Sinhala)

**Dashboard එක කියන්නේ මොකක්ද?**
Dashboard එක කියන්නේ Administrator log වුණාම මුලින්ම පෙනෙන පිටුවයි. අවන්හලේ තත්ත්වය එක බැල්මකින් තේරුම් ගන්න එය උදව් කරනවා. ඒකේ තියෙන හැම අංකයක්ම database එකේ ඇත්තටම තියෙන records වලින් හරි, ML model එක හදපු forecasts වලින් හරි එන්නේ. Dashboard එක තමන්ගේම කියලා අංක හදන්නේ නැහැ.

**කොටස් 5ක් තියෙනවා:**

1. **ප්‍රධාන අංක (KPI) කාඩ් 4ක්**
   - *Portions sold*: තෝරාගත් කාලයේදී (පසුගිය දින 7 හෝ 30) විකුණපු portions ගණන. `sales_records` table එකෙන් එකතු කරනවා.
   - *Portions wasted*: ඒ කාලයේදී නාස්ති වුණු (විසි කරපු) portions ගණන. `food_waste` table එකෙන් එනවා.
   - *Food waste rate*: හදපු (prepare කරපු) portions වලින් කීයෙන් කීයක් නාස්ති වුණාද කියන ප්‍රතිශතය. සූත්‍රය: **නාස්ති වූ portions ÷ හදපු portions × 100**. උදා: 182 ÷ 1,767 × 100 = 10.3%. Settings වල තියෙන සීමාව (15%) ඉක්මවුවොත් කාඩ් එක කහ පාටින් පෙන්නනවා.
   - *Low stock ingredients*: දැන් අඩු මට්ටමේ හෝ සම්පූර්ණයෙන්ම ඉවර වෙලා තියෙන අමුද්‍රව්‍ය ගණන.

2. **Food demand forecast (ඉල්ලුම් පුරෝකථනය)**: අද සහ ඉදිරි දින 6 (මුළු දින 7) සඳහා ML model එක (XGBoost) අනාවැකි කියපු portions ගණන, bar chart එකකින් පෙන්නනවා. මේවා **අනාවැකි (predictions)** මිසක් සැබෑ විකුණුම් නෙවෙයි. ඒ නිසා "Prediction" කියන නිල් label එක දාලා තියෙනවා, ඒවා නිල් පාටින් පෙන්නන්නේත් ඒ නිසයි. Forecast එකක් නැති දවසක් තිබුණොත් ඒක 0 කියලා පෙන්නන්නේ නැහැ. "No forecast yet" කියලා නම සඳහන් කරනවා.

3. **Sales and waste trend (ඉතිහාසය)**: තෝරාගත් කාලයේ දිනපතා විකුණුම් (කොළ පාට රේඛාව) සහ නාස්තිය (තැඹිලි පාට රේඛාව). මේවා **සැබෑවටම සටහන් කරපු** අංක. Record එකක් නැති දවසක් රේඛාවේ හිස් තැනක් (gap) විදිහට පෙන්නනවා. ඒක 0 කියලා පෙන්නන්නේ නැහැ.

4. **Inventory alerts (තොග අනතුරු ඇඟවීම්)**: අමුද්‍රව්‍යයක දැනට භාවිතා කළ හැකි (කල් ඉකුත් නොවූ) තොගය එහි reorder level එකට වඩා අඩු නම් "Low" කියලත්, 0 නම් "Out of stock" කියලත් පෙන්නනවා. Minimum මට්ටමටත් වඩා අඩු නම් "below minimum" කියලා රතු පාටින් පෙන්නනවා. ඒ ළඟම තියෙන *Open alerts* කාඩ් එකේ system එක හදපු හැම alert එකක්ම පෙනෙනවා (stock-out අවදානම, expiry, waste risk, forecast failure වගේ).

5. **Quick actions (ඉක්මන් ක්‍රියා)**: Forecast එකක් හදන්න, BOM (recipes) කළමනාකරණය කරන්න, inventory බලන්න, reports බලන්න කෙලින්ම අදාළ පිටුවට යන links.

**වැදගත්ම කරුණු:**
- **ඉතිහාසය (historical)** සහ **අනාවැකි (predicted)** කවදාවත් මිශ්‍ර කරන්නේ නැහැ. කාඩ් වෙනස්, පාට වෙනස්, label වෙනස්.
- Reporting කාලය **ඊයේ දිනයෙන් අවසන් වෙනවා**. අද දවසේ දත්ත තවම සටහන් වෙමින් පවතින නිසා අද දිනය ඇතුළත් කරන්නේ නැහැ.
- මේ demo එකේ දත්ත **synthetic (කෘතිමව හදපු)** දත්ත. ඒ බව පිටුවේ ඉහළින්ම පැහැදිලිව කියනවා.
- තෝරාගත් කාලයේ සමහර දවස් වලට විකුණුම් සටහන් වෙලා නැත්නම්, "Sales are recorded for 3 of the 7 days" වගේ පණිවිඩයක් පෙන්නනවා. එතකොට අඩු එකතුවක් සම්පූර්ණ සතියක එකතුව කියලා කවුරුත් වරදවා තේරුම් ගන්නේ නැහැ.

---

## 2. What each part is for, where the value comes from, and how it is calculated

> **Since the viva polish (14 Oct 2026)** the four tiles are replaced by the six-step workflow strip (Historical sales,
> ML demand forecast, Preparation recommendations, BOM & ingredient requirements, Inventory decisions, Food waste
> monitoring), each with today's figure: the same tile values plus today's prep plan, ingredient shortages and reorder
> count, read from the existing recommendation endpoints. The forecast chart also shows the last 7 recorded days as a
> line before the 7 forecast bars. The Kitchen and Inventory dashboards use the same strip.
>
> **Layout since 14 Oct 2026 (final UI pass).** Top: four tiles, **Sales**, **Forecast demand (next 7 days)**,
> **Food waste** (rate, with portions and value in the hint) and **Inventory status** (ingredients low or out). Then the
> forecast chart and the sales and waste trend. Then **Needs attention**: Alerts and **Recommended actions** (plain
> rules over the same figures: reorder, forecast shortfall, expired batches, waste above the limit, missing recipes,
> confirmed pre-orders; each links to the report that holds the detail). Bottom: upcoming pre-orders, recent activity,
> quick actions. The per-ingredient inventory table moved off the dashboard: the same figures are in Reports &
> Analytics, Inventory group (Stock levels, Ingredient demand, Batches and expiry). No formula changed; the rows below
> still describe where every number comes from.

The reporting period is **the last 7 or 30 days, ending yesterday**. If today is 13 Oct, "Last 7 days" means 6 Oct to 12 Oct. Today is left out because sales and waste for today are still being recorded.

| Dashboard part | Purpose | Source (database table) | Calculation |
|---|---|---|---|
| **Sales** tile (portions sold) | How much was sold | `sales_records` | Sum of `quantity_sold` for dates in the period. The revenue hint is the sum of `quantity_sold x unit_price`, using the price stored on each record. |
| Food waste tile hint (portions wasted) | How much prepared food was thrown away | `food_waste` | Sum of `quantity` in the period. The value hint is the sum of `quantity x unit_price` (the selling price, not the ingredient cost). |
| **Food waste** tile (rate) | Waste as a share of production | `food_waste` and `preparation_records` | `wasted / prepared x 100`, rounded to 1 decimal place. Shows "No data" if nothing was prepared (never a misleading 0%). It turns amber above `waste_risk_threshold_pct` in `settings` (default 15%). The waste-risk alert and the Analytics chart use the same ratio. |
| **Inventory status** tile | How many ingredients need reordering now | `ingredients` and `stock_batches` | For each active ingredient, *usable stock* = the sum of `qty_remaining` over batches that are not expired. Status: `out` if usable ≤ 0; `low` if usable ≤ `reorder_level`; otherwise `ok`. "Below minimum" means usable ≤ `min_stock`. The tile counts out + low. |
| **Food demand forecast** | Expected demand for planning | `forecasts` (only rows with `is_latest = true`), plus `forecast_runs` and `model_versions` | For each day from today to today + 6: the sum of `predicted_qty` over all menu items. A day with no forecast rows is `null` and is named in a warning. The total is the sum over the 7 days. "Test error" is the model's hold-out MAE (mean absolute error) stored at training time, shown next to the naive "same day last week" baseline. |
| **Sales and waste trend** | Day-by-day history | `sales_records` and `food_waste`, via the Reports endpoints | Quantity per day. Every date in the period is on the axis. A day with no sales records is a gap. Waste on a day with sales but no waste records counts as 0. |
| **Recommended actions** (was the inventory alerts table) | Which ingredients are low, short in the forecast or expired | Same as the Inventory status tile, plus projected stock-out alerts and batch expiry dates | The first four names are listed per line; the full per-ingredient detail is in Reports & Analytics, Inventory (Stock levels, Ingredient demand, Batches and expiry). |
| **Open alerts** | Everything the alert check found | `alerts` | Produced by `alert_service` (low/critical stock, projected stock-out, expiry, waste risk, forecast failure, manual shortage). Most severe first. **Acknowledge** marks an alert as seen. The bell in the top bar links here (`/admin#alerts`). |
| **Quick actions** | Shortcuts | none (links only) | Generate forecast → `/admin/models?tab=runs` (Forecasting, Forecast generation, "Run forecast now"); Manage BOM → `/admin/catalog`; View inventory → `/admin/monitor?tab=stock` (Reports, Stock levels); View reports → `/admin/monitor`. |
| **Recent activity** | Audit trail | `audit_logs` | The last 10 actions (5 shown), turned into plain English. |
| **Notes at the top** | Honesty about the data | `settings.data_source_label`, `sales_records` | The synthetic-data note shows when the data source label says synthetic/demo. The partial-period note shows when fewer days than the period length have sales records. |

**Example from staging, Last 7 days (6 to 12 Oct 2026, sales recorded 6 to 8 Oct only):**
1,585 sold + 182 wasted = 1,767 prepared, so the waste rate is 182 ÷ 1,767 × 100 = **10.3%**. The 7-day forecast for 13 to 19 Oct is 498.5 + 511.3 + 557.9 + 689.4 + 730.9 + 636.8 + 489.1 = 4,113.9, which shows as **4,114**. All of these were checked with direct SQL on the same database.

---

## 3. Source files and API endpoints

**Request flow:** browser page → Vue code → JSON API → controller → service → database. This is the MVC rule of the project: controllers do no calculations, services do all the logic.

| Layer | File | What it does |
|---|---|---|
| Page route | `app/controllers/admin.py` (`dashboard`) | Renders the HTML shell for `/admin` (administrator only). |
| Template (View) | `app/templates/admin/dashboard.html` | The layout: KPI tiles, the two charts, tables, alerts and actions. Display only. |
| Page script | `app/static/js/pages/admin_dashboard.js` | Calls the APIs, prepares chart data, formats numbers. No business formulas. |
| Shared components | `app/static/js/components.js` | `sr-stat-tile`, `sr-bar-chart`, `sr-line-chart`, `sr-alert-list`, `sr-empty`, `sr-loading` (Chart.js, vendored). |
| Styles | `app/static/css/app.css`, section 12 | Administrator green theme, light sidebar, dashboard layout. |
| API controller | `app/controllers/api/dashboards.py` (`admin_dashboard`) | `GET /api/v1/dashboards/admin?range=7\|30`: checks the role and calls one service method. |
| Service (Model logic) | `app/services/dashboard_service.py`: `admin_dashboard`, `_forecast_days`, `_stock_summary`, `_waste_rate`, `_coverage`, `sales_report`, `waste_report` | All the calculations. |
| Other services used | `forecasting_service.forecast_map`, `inventory_service.stock_levels` / `stock_status`, `alert_service.list_alerts`, `data_management_service.items_without_recipe` | Reused, so the dashboard numbers match the detail pages. |
| Tests | `tests/integration/test_admin_dashboard.py` | 8 tests with hand-calculated expected values (waste rate, missing forecast days, stock order, period dates). |

**API calls the page makes:**

| Endpoint | Used for |
|---|---|
| `GET /api/v1/dashboards/admin?range=7` or `range=30` | Everything except the trend and the model error |
| `GET /api/v1/alerts?status=open` | The Open alerts list |
| `GET /api/v1/reports/sales?from=…&to=…&group_by=day` | Sales line on the trend chart |
| `GET /api/v1/reports/waste?from=…&to=…&group_by=day` | Waste line on the trend chart |
| `GET /api/v1/model-versions` | Hold-out MAE of the active model vs the baseline |
| `POST /api/v1/alerts/{id}/acknowledge` | The Acknowledge button |

Note: opening the dashboard also runs the alert check (when the last check is older than 60 seconds). So the dashboard **reads** sales, waste and stock but can **write** new alerts. This is existing behaviour, unchanged.

---

## 4. Role of the dashboard in the whole system

```
 Data in                          Processing                        Decisions out
 ───────                          ──────────                        ─────────────
 Sales import (admin)  ─┐
 Kitchen: prepared,     │     ML forecasting (app/ml, XGBoost)  ─►  Prep plan (kitchen)
   served, waste       ─┼──►  Recommendation service            ─►  Ingredient needs, reorder (inventory)
 Stock in/out, batches ─┤     Alert service                     ─►  Alerts
 Holidays, promotions  ─┘     Dashboard service (read + sum)    ─►  ADMIN DASHBOARD (this page)
```

The dashboard is the **monitoring layer** for the administrator. It does not forecast and does not change stock. It brings together the results of the other modules (sales history, kitchen records, the inventory, the ML forecasts, the alerts), so the manager can see in one place whether the restaurant is wasting food, running out of ingredients, or about to face high demand. Each tile links to the detail page where the same numbers can be checked.

**Separation of duties:** the administrator cannot record kitchen production. Only the Food Production (kitchen) account can, on its Prep plan and Served & waste pages, and the server enforces this (`@roles_required("kitchen")` on `POST /kitchen/prepared`). That is why "Record kitchen production" is not a dashboard button; the dashboard explains this in one line.

---

## 5. Viva presentation script (about 3 minutes, simple English)

> "This is the Administrator dashboard of SmartRestaurant. It is the first page the manager sees after logging in.
>
> At the top you can see the reporting period. It is the last 7 days, ending yesterday, because today's sales are still being recorded. I can switch to the last 30 days here. Below that, the system says clearly that this is synthetic demo data, and it also warns me when sales are recorded for only part of the period.
>
> The first row has four key figures. Portions sold and portions wasted come straight from the sales and food-waste records. The food waste rate is wasted portions divided by prepared portions: here 182 out of 1,767, which is 10.3 percent. It turns amber when it goes above the 15 percent limit set in Settings. The last tile counts the ingredients whose usable, non-expired stock is at or below the reorder level.
>
> On the left is the food demand forecast for today and the next six days. These numbers are predictions from our XGBoost model, not actual sales, so they are marked 'Prediction' and drawn in blue. Underneath I show which model made them and its test error compared with a simple baseline. If a day has no forecast, the dashboard names that day instead of showing zero.
>
> On the right is the history: portions sold and wasted per day. A gap means no records for that day, not zero sales.
>
> Below that are the inventory alerts: which ingredients are out of stock or low, with their usable stock and reorder level, and the list of open alerts, which I can acknowledge.
>
> Finally, the quick actions take me to the pages where I generate a forecast, manage the recipes (the BOM), view the inventory and view the reports.
>
> Every number here comes from the database through one service, the dashboard service, which reuses the same functions as the report pages. So the dashboard always agrees with the detailed reports."

---

## 6. Likely examiner questions and answers

1. **Where do the dashboard numbers come from?**
   From the MySQL database, through one API, `GET /api/v1/dashboards/admin`. That API calls `dashboard_service.admin_dashboard`, which sums the sales, waste and production records and reads the latest forecasts and the current stock. Nothing on the page is typed in by hand or made up.

2. **How is the food waste rate calculated?**
   Portions wasted divided by portions prepared, times 100, over the same period. For example 182 ÷ 1,767 = 10.3%. If nothing was prepared, it shows "No data" instead of 0%.

3. **Why divide by prepared portions and not by sold portions?**
   Waste comes from what the kitchen prepared. Prepared = sold + wasted (+ other uses), so dividing by prepared gives the share of production that was lost. The waste-risk alert and the Analytics chart use the same definition, so the figures are consistent.

4. **Why does the period end yesterday?**
   Today's sales and waste are still being recorded during service. Including today would make the total look too low.

5. **How do you separate actual data from predictions?**
   They come from different tables: `sales_records` and `food_waste` are actual, `forecasts` are predicted. They are in separate cards, the forecast card has a "Prediction" label, forecasts are blue and history is green and orange.

6. **What happens if there is no forecast for some day?**
   That day is `null`, not 0. The chart leaves it empty and a warning names the missing days, with a link to run a forecast.

7. **How is "low stock" decided?**
   Usable stock = the remaining quantity in batches that are not expired. If it is 0 or less the ingredient is "out"; if it is at or below the reorder level it is "low"; at or below the minimum stock it is also flagged "below minimum".

8. **Why do you use usable stock and not total stock?**
   Expired stock cannot be used for cooking. Counting it would hide a real shortage.

9. **Which ML model produces the forecast, and how good is it?**
   The active model is XGBoost (Random Forest and two simple baselines were also trained and compared). On the hold-out period of the synthetic data, its error is about 9 portions per item per day, against about 13 to 14 for the "same day last week" baseline. These figures are for synthetic data and do not prove real-world accuracy.

10. **Did you change the ML algorithm for the dashboard?**
    No. The dashboard only reads the stored forecasts. The models in `app/ml` and the forecasting service were not changed.

11. **Is the data real?**
    No. The demo uses synthetic data generated for a Colombo fast-food outlet, and the page says so. Real public restaurant data was only used separately, as an external check of the method.

12. **What does "Sales are recorded for 3 of the 7 days" mean?**
    The demo history stops on a fixed date, so the latest week is only partly filled. The dashboard counts the days that have sales records and warns me, so a short total is not mistaken for a full week.

13. **Why can't the administrator record kitchen production from the dashboard?**
    Separation of duties: only the kitchen role records prepared, served and wasted food. The server enforces it with role checks on those API endpoints, and the RBAC tests check every route against every role.

14. **How do you make sure the dashboard agrees with the reports?**
    The dashboard calls the same service functions as the Reports page (`sales_report`, `waste_report`, `stock_levels`, `forecast_map`). I also checked the numbers with direct SQL queries, and the automated tests use hand-calculated expected values.

15. **How did you test the dashboard?**
    8 new automated tests for the calculations, the full fast suite (373 tests passing), the existing browser smoke test in Chromium, Firefox and WebKit, and a check at 360, 768, 1280 and 1440 pixels wide for layout problems and console errors.

16. **Is the dashboard secure?**
    The page and the API are for the admin role only (`roles_required("admin")`). Every write needs a CSRF token. The Vue templates escape all output. The API returns only aggregated numbers.

17. **What happens if an API call fails?**
    If the main call fails, an error box with a "Try again" button appears. If only the trend fails, the trend card says so and the other cards still work. While loading, grey placeholders are shown.

18. **Why Vue and Chart.js without a build step?**
    The project is small and has one builder. Vue 3 and Chart.js are vendored files loaded directly, so there is no npm build, no CDN dependency, and the server stays simple to deploy.

19. **What is the BOM?**
    The Bill of Materials: the recipe for each menu item, giving the quantity of each ingredient per portion. It turns the portion forecast into ingredient needs. It is managed on the Menu & recipes page.

20. **What would you add with more time?**
    A daily scheduled forecast job (currently the forecast must be run by hand or by a timer that is only on staging), real sales data from a partner restaurant, and a per-item drill-down from the forecast chart.

---

## 7. What to learn before the viva (beginner checklist)

1. **The request flow:** page → Vue `api.get(...)` → Flask controller → service → SQLAlchemy model → database. Be able to point at each file in section 3.
2. **The four formulas:** portions sold (sum), portions wasted (sum), waste rate (wasted ÷ prepared × 100), stock status (usable vs reorder level and minimum).
3. **Historical vs predicted:** which tables hold actual data (`sales_records`, `food_waste`, `preparation_records`) and which hold predictions (`forecasts`, with `is_latest`).
4. **The ML basics:** what a feature is (day of week, lag 7, rolling mean, holidays, promotions), what MAE means (the average size of the error, in portions), why a model is compared with a naive baseline, and why a hold-out period must come after the training data.
5. **Roles (RBAC):** admin, kitchen and inventory, and why each can only do its own tasks.
6. **Synthetic data honesty:** why it is labelled, and why its accuracy is not real-world accuracy.
7. **Practise the demo:** switch between 7 and 30 days, point at the "Prediction" label, open one alert, and follow one quick action to its page.
