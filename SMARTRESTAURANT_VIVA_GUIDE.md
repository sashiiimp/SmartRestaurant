# SmartRestaurant: viva guide (whole system)

CSE5015 final project, Team ForeSight. This guide covers the whole system as of 13 Oct 2026 (branch `system-integration`). `DASHBOARD_VIVA_GUIDE.md` goes deeper into the Admin Dashboard alone.

All numbers here come from the code, the tests or the stored model metrics. Where a number depends on the day you run the demo, the guide says so.

---

## 1. The system in one page

### සිංහලෙන් (Sinhala)

SmartRestaurant කියන්නේ ශ්‍රී ලංකාවේ fast-food අවන්හලකට **ආහාර නාස්තිය** සහ **අමුද්‍රව්‍ය හිඟවීම** අඩු කරගන්න උදව් කරන web පද්ධතියක්.

1. පසුගිය විකුණුම් දත්ත, නිවාඩු දින (Poya, public, school), promotions සහ කාලගුණය උපයෝගී කරගෙන **XGBoost** නම් machine learning model එකක් ඉදිරි **දින 7** සඳහා හැම menu item එකකම ඉල්ලුම (portions කීයක් විකිණෙයිද) අනාවැකි කියනවා.
2. ඒ අනාවැකියට 10% ආරක්ෂිත ප්‍රමාණයක් (safety buffer) එකතු කරලා, තහවුරු කරපු **pre-orders** ගණනටත් වඩා අඩු නොවෙන විදිහට, batch size එකට වට කරලා, කුස්සියට **කොච්චර හදන්නද** කියලා යෝජනා කරනවා (Prep plan).
3. ඒ ප්‍රමාණය **BOM / recipe** එකෙන් (portion එකකට අමුද්‍රව්‍ය කොච්චරද) ගුණ කරලා, **අමුද්‍රව්‍ය අවශ්‍යතාව** ගණනය කරනවා. ඒක කල් ඉකුත් නොවූ තොගය එක්ක සංසන්දනය කරනවා.
4. තොගය මදි නම් හෝ ඉක්මනින් ඉවර වෙනවා නම් **alerts** සහ **reorder** යෝජනා පෙන්නනවා.
5. කුස්සිය හදපු, විකුණපු, නාස්ති වුණු ප්‍රමාණ සටහන් කරනවා. ඉන් **waste rate** (නාස්ති ÷ හදපු × 100) ගණනය කරලා reports වල පෙන්නනවා.

වැදගත්: මේ demo එකේ දත්ත **synthetic (කෘතිමව හදපු)** දත්ත. ඇත්ත අවන්හලක දත්ත නෙවෙයි. ඒ බව පද්ධතියේ හැම තැනම label කරලා තියෙනවා. ML model එක දත්ත වලින් ඉගෙන ගන්නවා මිසක්, අනාවැකිය කවදාවත් හිතලා දාපු අංකයක් නෙවෙයි.

**කවුද පාවිච්චි කරන්නේ:** Administrator (සම්පූර්ණ දළ විශ්ලේෂණය, models, reports, setup), Food Production / Kitchen (prep plan, pre-orders, හදපු/නාස්ති සටහන්), Inventory (තොග, reorder, purchase orders).

### In English

SmartRestaurant is a web system that helps a Sri Lankan fast-food outlet **waste less food and run out of ingredients less often**. It:

1. **forecasts** how many portions of each menu item will be sold on each of the next 7 days, with an XGBoost model trained on past sales, holidays, promotions and weather;
2. turns that into a **preparation plan**: forecast + safety buffer, never below committed pre-orders, rounded up to the batch size;
3. multiplies the plan by each item's **recipe (BOM)** to get **ingredient needs**, and compares them with **usable** (non-expired) stock;
4. raises **alerts** and **reorder suggestions** when stock is low now or will run short within the 7 days;
5. records what the kitchen **prepared, served and wasted**, and reports the **waste rate**.

There are three roles: Administrator, Food Production (kitchen) and Inventory & Procurement. Each sees only its own pages, and the server enforces this on every request.

---

## 2. Architecture

```
Browser (Jinja2 page + Vue 3, Chart.js; vendored, no build step)
   │  JSON over HTTPS (/api/v1/...), CSRF token on every write
   ▼
Controllers  app/controllers/        parse request, check role, call ONE service, map errors to status codes
   ▼
Services     app/services/           all business logic, validation, transactions
   │   forecasting_service ──► app/ml (pure pandas / scikit-learn / XGBoost, no database)
   ▼
Models       app/models/  (SQLAlchemy) ──► MySQL 8.4 (production), SQLite (tests)
```

- **MVC with a service layer.** The controllers never calculate anything, and `tests/test_architecture.py` enforces which service may call which.
- **Services:** `auth_service`, `data_management_service` (menu, recipes, imports), `forecasting_service`, `recommendation_service` (prep plan, ingredient needs, reorder), `inventory_service`, `kitchen_service` (prepared/served/waste, orders, pre-orders), `alert_service`, `dashboard_service` (read-only totals for dashboards and reports).
- **Deployment:** gunicorn behind nginx over HTTPS at `smartrest.developerstudio.space`. It runs as an unprivileged `smartrest` user under systemd, with a private MySQL instance. A systemd timer (`deploy/systemd/smartrest-forecast.timer`) runs the daily forecast.

---

## 3. Database relationships (main tables)

```
menu_items ──< recipe_lines >── ingredients ──< stock_batches ──< stock_movements
    │                                   └──< (alerts: low, critical, projected stock-out, expiry)
    ├──< sales_records        (portions served per item per day: the training target)
    ├──< preparation_records  (portions prepared)
    ├──< food_waste           (portions wasted, with reason)
    ├──< pre_orders           (customer, pickup time, status)
    ├──< forecasts >── forecast_runs >── model_versions
    └──< recommendations      (the accepted or overridden prep plan per item and day)
users ──< audit_logs  (who did what, when)
```

- **Stock is never one running number.** Usable stock = the sum of `qty_remaining` in batches that are not expired. Every change is an immutable `stock_movements` row.
- **Forecasts are never overwritten.** A new run inserts new rows and moves the `is_latest` flag, so old forecasts stay available for accuracy checks.
- **Pre-orders** (`app/models/sales.py`, `PreOrder`): `customer_name`, `customer_contact`, `menu_item_id`, `quantity`, `target_date` (preparation date), `pickup_time`, `status` (pending/confirmed/completed/cancelled), `customer_note`, `created_at`, `completed_at`. Migration `c4e1a7b9d052` added the customer and pickup columns, all nullable so older rows stay valid.

---

## 4. The ML model

| | |
|---|---|
| **What it predicts** | Portions sold per menu item per day (the `quantity_sold` in `sales_records`), for today and the next 6 days. |
| **Algorithm** | XGBoost regressor (the active model). Random Forest and two simple baselines are trained alongside for comparison. |
| **Features** (`app/ml/features.py`) | calendar: `dow`, `is_weekend`, `month`; holidays: `is_public_holiday`, `is_poya`, `is_school_holiday`; promotion: `promo_discount_pct`; weather: `rain_mm`, `temp_c` (seasonal average when unknown); history: `lag_7`, `lag_14`, `lag_21`, `lag_28`, `roll_mean_7`, `roll_mean_28`; one column per menu item. |
| **Baselines** | `naive_lag7` (same day last week) and `seasonal_mean4` (average of the same weekday over the last 4 weeks). |
| **Evaluation** | Chronological hold-out: train on the earlier data, test on the last weeks the model never saw. Metrics are MAE, RMSE, MAPE, WAPE, R² and bias. Plus 6 × 28-day rolling cross-validation (`flask smartrest evaluate`, `docs/ML_EVALUATION.md`). |
| **Live model** | `v20261008-1`, hold-out 13 Aug to 7 Oct 2026. XGBoost MAE **9.00** portions per item per day (WAPE 14.1%) vs naive baseline MAE **13.29** (WAPE 20.9%); Random Forest MAE 9.00. |
| **Training code** | `app/ml/train.py`, `app/ml/evaluate.py`; called only by `forecasting_service.train_model`. |
| **Forecast code** | `forecasting_service.run_forecast` → `app/ml/predict.py`; stored in `forecasts`. |

These accuracy figures are for **synthetic** data. They show the method works on data with realistic patterns, not how accurate it would be in a real restaurant.

---

## 5. The synthetic dataset

- Generated by `app/seed/generate.py` (`flask smartrest generate-data`, seed 42). It is loaded through the same import services as real data, so it passes the same validation.
- It covers 1 Sep 2024 up to the demo reset (live: up to 7 Oct 2026), for 10 menu items: Chicken Burger, Beef Burger, Veggie Burger, Fried Chicken 2 pc, Chicken Kottu, Veg Kottu, French Fries, Chicken Wrap, Iced Milo and Lime Juice.
- **Assumed effects**, all coded in the generator rather than measured:
  - day-of-week factors (Mon 0.85 … Sat 1.30);
  - Sri Lankan public, Poya and school holidays from `data/holidays_lk.csv`;
  - about one promotion a month (10–20% off one or two items) plus two storewide offers;
  - monsoon-season rain probabilities;
  - random noise.
- **Production and waste history:** prepared = sold + wasted, which is why the waste rate can be calculated for past days.
- The UI shows **"Synthetic demo data"** in the top bar and on the dashboard. Real public restaurant data (Yaz, US sandwich chain) was used only as an external check of the method, never mixed into the demo.

---

## 6. Seven-day forecasting workflow

1. **Every hour at :05 (Sri Lanka time)**, the timer runs `flask smartrest forecast-daily` (`forecasting_service.run_daily_forecast`).
2. If today's forecast already succeeded with the active model, it does nothing. It also waits if another run is in progress, and gives up after 3 failures that day, so you see an alert instead of a loop.
3. Otherwise `run_forecast(as_of=today, horizon=7)` builds the features for today … today + 6 and predicts every active item.
4. It locks the outlet row, so the timer and the "Run forecast now" button can't both create "latest" rows. It then inserts the new forecasts and moves `is_latest`.
5. The Dashboard, Prep plan, Ingredient needs, Reorder and Alerts all read the latest forecasts.

**Why there were only 5 days before:** forecasts only ran when someone pressed the button. The last live run was on 11 Oct (covering 11–17 Oct), so on 13 Oct, 18 and 19 Oct were missing. The daily job fixes this. Tested on a copy of production: 7 days × 10 items, no duplicates, and a second call does nothing.

**Missing values are never invented.** A day without a forecast is shown as "no forecast" (null), never as 0 or an average.

---

## 7. Preorder Management

- **Who:** the Food Production account, on the **Orders → Pre-orders** tab (`/kitchen/orders`). The administrator can view them (dashboard card, API) but not change them.
- **Fields:** ID, customer name, contact (optional), menu item, quantity, preparation date, pickup time, status, notes (optional), created time and creator.
- **Status flow** (`kitchen_service.PREORDER_TRANSITIONS`):
  ```
  pending ──► confirmed ──► completed (handed over; only on or after its date)
     │            │  └────► pending (back on hold)
     └────────────┴───────► cancelled
  completed and cancelled are final
  ```
- **Functions:** create, list, filter by dates and status, details panel, edit (pending/confirmed, today or later), confirm, cancel, mark completed. The dashboard lists confirmed pre-orders for the next 7 days.
- **Security:** login required; writes are kitchen-only (`@roles_required("kitchen")`); CSRF token on every POST/PATCH; all input validated in the service (name ≤ 100 characters, contact ≤ 60, pickup time HH:MM, quantity 1–10,000, date not in the past).
- **Code:** `app/services/kitchen_service.py` (`create_pre_order`, `update_pre_order`, `pre_order_detail`, `list_pre_orders`, `upcoming_pre_orders`); API in `app/controllers/api/kitchen.py`; page `app/templates/kitchen/orders.html` + `app/static/js/pages/kitchen_orders.js`.

### How pre-orders affect planning (no double counting)

The model learns from `sales_records`, every portion served, so pre-order pickups are already inside the history it learned from. **The forecast is total demand.** Adding pre-orders on top would count them twice. So pre-orders act as a **floor**:

```
committed pre-orders = confirmed + completed pre-orders for that item and day
recommended = roundUpToBatch( max( forecast × (1 + buffer%), committed pre-orders ) )
```

| Example (Chicken Burger, batch 6, buffer 10%) | Forecast | Pre-orders | Calculation | Recommended |
|---|---|---|---|---|
| Normal day | 30 | 10 | max(33, 10) = 33 → next multiple of 6 | **36** |
| Large pre-order | 30 | 40 | max(33, 40) = 40 → next multiple of 6 | **42** |
| Simple addition (wrong here) | 30 | 10 | 33 + 10 = 43 | would over-prepare by about 10 |

- The **forecast stays visible separately**: the Prep plan card shows Forecast, Pre-orders and Recommended, and "How was this worked out?" shows the full calculation.
- **Completed** pre-orders keep counting for their day, so the plan doesn't drop as customers collect. Completing a pre-order records **no sale**; the kitchen's served total already includes it.
- If a pre-order changes after the plan was accepted, the kitchen gets a warning to re-check the Prep plan. The stored plan is not silently changed.
- Code: `recommendation_service.compute_recommended`, `_preorder_totals`, `get_prep_plan`; documented in `docs/ML_PLAN.md` section B1.

---

## 8. BOM and ingredient calculation

The **BOM (Bill of Materials)** is the recipe: the quantity of each ingredient per portion, in that ingredient's own unit (kg, pcs, L). The administrator maintains it on **Menu & recipes** (`/admin/catalog`).

Chicken Burger recipe (live data): chicken 0.120 kg, burger bun 1 pcs, lettuce 0.015 kg, tomato 0.020 kg, cheese slice 1 pcs, mayonnaise 0.015 kg.

```
Required ingredient = planned portions × quantity per portion   (summed over all items that use it)
```

| For 36 Chicken Burgers | Calculation | Required |
|---|---|---|
| Chicken | 36 × 0.120 kg | 4.32 kg |
| Burger bun | 36 × 1 | 36 pcs |
| Lettuce | 36 × 0.015 kg | 0.54 kg |
| Tomato | 36 × 0.020 kg | 0.72 kg |
| Cheese slice | 36 × 1 | 36 pcs |
| Mayonnaise | 36 × 0.015 kg | 0.54 kg |

If Fried Chicken (0.300 kg chicken each) is also planned at 30, chicken becomes 4.32 + 9.00 = 13.32 kg. A tested example (`test_requirements_match_the_hand_calculation`): 54 burgers + 30 fried chicken = 15.48 kg chicken, against 12 kg usable (a 5 kg expired batch is not counted), so the shortfall is 3.48 kg.

- **Which quantity is used:** the accepted or overridden plan if there is one, otherwise the recommended quantity. Items with no forecast or no recipe are **listed**, not silently counted as zero.
- **Usable stock** excludes expired batches.
- **No stock is deducted** by forecasting or planning (tested). Stock goes down only when Inventory records a stock-out, issue or wastage.
- **Units:** each recipe line is entered in the ingredient's own unit, so no conversion is needed. The system doesn't convert between units (e.g. g ↔ kg); a recipe for an ingredient kept in kg must be entered in kg.
- Code: `recommendation_service._requirements_for`, `get_requirements` (one day), `get_ingredient_forecast` (7 days, days of cover, first shortfall), `get_reorder_suggestions`.

---

## 9. Inventory optimisation

- **Status now** (`inventory_service.stock_status`): `out` if usable ≤ 0, `low` if usable ≤ reorder level, and also *critical* if usable ≤ minimum stock.
- **Forecast shortfall:** the 7-day ingredient needs are added up day by day. The first day the running total exceeds usable stock is the "first shortfall".
- **Reorder suggestion** (`_reorder`): need over the supplier lead time + safety stock − usable − already on order, rounded up to the pack size (and at least the reorder quantity).
- **FEFO** (first expiry, first out) when stock is issued, with row locks so two users can't take the same batch.
- **Alerts** (`alert_service.evaluate`) are worked out from the data each time:
  - each condition has one open alert at most, so there are no duplicates (enforced by a unique key);
  - an alert closes by itself when the condition clears, and stays in the History tab;
  - **Acknowledge** only means "seen". It does not close the alert or pretend stock was received.
- The **dashboard groups alerts per ingredient**, with three columns: **Now** (usable vs reorder level), **Forecast** (short by X from date D) and **Expiry** (expired or expiring batches).

---

## 10. Food waste management

- The kitchen records **prepared** portions (several entries per day add up), **served** portions (one per item per day, overwriting needs confirmation), and **waste** with a reason (overproduction, quality, expired, other). Since 13 Oct, prepared and waste entries also appear in the activity log.
- **Waste rate** = wasted ÷ prepared × 100. Example: prepared 35, sold 30, wasted 5 → 5 ÷ 35 × 100 = **14.29%**.
- Where it is shown:
  - **Dashboard tile** (selected period);
  - **Reports → Waste** (by period, top items, by reason, and since 13 Oct a **per-item table**: planned, prepared, sold, wasted, waste rate, suggestion);
  - **Analytics** (waste rate over time);
  - the kitchen's **daily summary** (prepared − served − wasted − other use = unaccounted).
- **Waste-risk alert:** an item whose last-7-day waste rate is above the limit in Settings (default 15%), with at least 20 portions prepared.
- **Adjustment strategy (documented):** waste never changes the ML forecast automatically. The report suggests "about N portions a day were wasted; consider planning that many fewer", and the kitchen manager decides with an **override and a reason**. The override is stored separately from the system's recommendation, so both stay visible.

---

## 11. How the modules communicate

```
Admin imports sales / holidays / promotions ─┐
Kitchen records prepared, served, waste ─────┼──► sales_records, preparation_records, food_waste
                                             │
forecast timer / button ──► forecasting_service ──► app/ml ──► forecasts (latest)
                                                         │
kitchen pre-orders ──► pre_orders ─┐                     ▼
                                   └──► recommendation_service.get_prep_plan ──► Prep plan (accept / override)
                                                         │
                     recipe_lines (BOM) ─────────────────┼──► ingredient needs, 7-day shortfall, reorder
                     stock_batches (usable stock) ───────┘
                                                         ▼
                                    alert_service.evaluate ──► alerts (open / closed history)
                                                         ▼
                       dashboard_service ──► Admin, Kitchen and Inventory dashboards, Reports
```

Every arrow is a function call within one Flask process. There are no background workers, apart from the daily forecast timer, which just runs the same service.

---

## 12. Live demonstration script (about 10 minutes)

Before the demo, check that the daily forecast ran today: Forecasting → Models & runs → Forecast runs should show today's date. If not, press **Run forecast now** once.

1. **Login** as admin. Point at the role in the sidebar and the "Synthetic demo data" label.
2. **Dashboard:**
   - the reporting period and the "recorded for N of 7 days" note;
   - the 4 KPIs. Explain the waste rate formula using the tile's own numbers;
   - the forecast chart: 7 labelled days, the "Prediction" badge, the total = the sum of the bars, and the model name, MAE vs baseline and last run time.
3. **Inventory alerts:** pick one ingredient and read **Now**, **Forecast** and **Expiry**. Open **Alerts → History** and explain that Acknowledge ≠ restocked.
4. **Recent activity:** the sentences come from stored events. Each one shows who did it and when.
5. Log out and log in as **kitchen**. Open **Orders → Pre-orders**:
   - add a pre-order for today (customer, item Chicken Burger, quantity larger than the forecast, pickup time) as *Confirmed*;
   - open **Details**: creator, "Counts in the prep plan".
6. **Plan & prepare → Prep plan** for today, Chicken Burger:
   - Forecast stays the same, Recommended rose to cover the pre-order;
   - open "How was this worked out?" and explain max(forecast × 1.1, pre-orders) and why we don't add them;
   - press **Accept**.
7. **Ingredients → Needs & shortages:** chicken and bun requirements went up. Compare them with usable stock.
8. Back on **Orders**, press **Complete** on the pre-order. The prep plan stays the same (completed still counts) and no sale is recorded.
9. **Served & waste:** record a few wasted portions with a reason.
10. Log in as **admin** again:
    - the dashboard's upcoming pre-orders card and the activity lines ("Pre-order #… created / completed", "Food waste recorded…");
    - **Reports → Waste** shows the per-item waste rate table.
11. **Forecasting → Models & runs:** the model comparison table (XGBoost vs Random Forest vs baselines) and the hold-out period.

The demo writes to the live demo database. Run it on the deployed demo only as rehearsed, and expect the new rows to stay unless the demo is reset.

---

## 13. Likely viva questions and answers

1. **What problem does the system solve?**
   Fast-food outlets either prepare too much (waste) or too little (stock-outs and lost sales). SmartRestaurant predicts demand per item per day and turns it into preparation and ingredient decisions.

2. **What does the model predict exactly?**
   Portions sold per menu item per day, for today and the next 6 days, from the history in `sales_records`.

3. **Why XGBoost?**
   It handles non-linear effects (weekends, holidays, promotions) and works well on small tabular data. We also trained Random Forest and two simple baselines. XGBoost and Random Forest were close (MAE 9.00 each on the hold-out); both beat the naive baseline (13.29).

4. **What is MAE and what does 9.00 mean?**
   Mean Absolute Error: the average size of the error. Here the forecast is off by about 9 portions per item per day on average, on days the model never saw.

5. **Why compare with a naive baseline?**
   A model is only useful if it beats a trivial rule. "Same day last week" is what a manager might do without the system. We beat it by about 32% in MAE.

6. **How did you avoid data leakage?**
   We used a chronological hold-out (we test only on days after the training period). Lag features use past days only. And forecasts for past dates from a model that saw those days are refused (`run_forecast` raises a validation error).

7. **Why synthetic data, and is that a weakness?**
   No restaurant shared its data. The generator encodes realistic Sri Lankan patterns, and everything is labelled synthetic. It is a limitation: the accuracy shows the method works, not real-world accuracy. Real public datasets were used separately as an external check.

8. **Why did the dashboard show only 5 forecast days, and how did you fix it?**
   Forecasts only ran when someone pressed the button, so each day the window lost a day. We added a once-a-day job (`run_daily_forecast`) on a systemd timer that does nothing if today's forecast already exists. A row lock prevents duplicate "latest" forecasts.

9. **What happens if the forecast for a day is missing?**
   It is shown as "no forecast", never 0. The prep plan marks the item "no forecast", and the ingredient needs list it instead of counting zero.

10. **How do pre-orders affect planning?**
    Confirmed and completed pre-orders for a day are a floor: recommended = round up(max(forecast × 1.1, pre-orders)). The forecast stays visible separately.

11. **Why not just add pre-orders to the forecast?**
    The model is trained on all served portions, including pre-order pickups. So the forecast already contains typical pre-order demand, and adding them would count them twice.

12. **What is the weakness of the max() policy?**
    If an unusually large one-off pre-order comes in, max() guarantees it is prepared, but the normal walk-in demand on top may be under-planned. The manager can override with a reason. With real data, a better approach would be to record pre-orders separately in the history and forecast walk-in demand only.

13. **What do the pre-order statuses mean?**
    - Pending: not yet agreed, not counted.
    - Confirmed: committed, counted.
    - Completed: handed over, still counted for that day.
    - Cancelled: not counted.

    Completed and cancelled are final.

14. **Can completing a pre-order double count sales?**
    No. Completing it records no sale. The kitchen's end-of-day served total includes those portions once, and that is one record per item per day.

15. **What is a BOM and how are ingredient needs calculated?**
    The recipe per portion. Need = planned portions × quantity per portion, summed over all items using that ingredient. Example: 36 burgers × 0.120 kg = 4.32 kg chicken.

16. **Why compare with usable stock rather than total stock?**
    Expired batches can't be cooked. In the tested example, total chicken is 17 kg but usable is 12 kg, which changes "enough" into "short by 3.48 kg".

17. **Does generating a forecast or plan reduce stock?**
    No. Only real stock-out, issue or wastage records move stock (tested: `test_forecast_pre_order_plan_and_ingredients_chain_without_moving_stock`).

18. **How is the food waste rate calculated, and from which data?**
    Wasted portions (`food_waste`) ÷ prepared portions (`preparation_records`) × 100, over the same dates. Example: 5 ÷ 35 = 14.29%.

19. **Does today's waste reduce tomorrow's forecast?**
    No, never automatically. The waste report suggests planning fewer portions; the manager decides with an override, stored separately from the system's recommendation.

20. **How do alerts avoid duplicates?**
    Each condition has a key (e.g. `critical_stock:ingredient:5`) with a unique constraint for open alerts. Re-checking updates the existing alert instead of creating a new one. When the condition clears, the alert closes and moves to history.

21. **Does acknowledging an alert mean the problem is fixed?**
    No. It only records that someone saw it. The alert closes by itself only when the data changes, for example when stock is received.

22. **What is the difference between "Now" and "Forecast" on Inventory alerts?**
    Now = today's usable stock against the reorder level and minimum. Forecast = the first day in the next 7 days on which the planned recipes need more than today's usable stock.

23. **Where does Recent activity come from?**
    Only stored events: audit log entries, forecast runs and stock movements entered by a user. It shows each event's time and user. Repeated identical events are shown once with a count.

24. **How is the system secured?**
    - Hashed passwords, login lockout, session protection;
    - role checks on every page and API route (tested route by route);
    - CSRF on all writes, parameterised queries, escaped output;
    - HTTPS, and an unprivileged service user.

25. **How did you test it?**
    - **Automated:** 395 fast tests (SQLite) and 14 MySQL tests, with hand-calculated expected values for the formulas.
    - **Migration:** rehearsed up, down and up on a copy of the production database.
    - **Browser:** a smoke test in Chromium, Firefox and WebKit, and checks at 360–1440 px.

26. **Why MVC with a service layer?**
    Controllers stay thin and testable, and every calculation lives in one place. The dashboard and reports call the same functions, so their numbers always agree. An architecture test stops a controller from containing logic.

27. **What would you improve with more time?**
    - real sales data from a partner restaurant;
    - recording pre-orders separately in the history, to forecast walk-in demand;
    - per-item buffers learned from forecast errors;
    - unit conversion in recipes;
    - push notifications for critical alerts.

---

## 14. Source file map

| Topic | Files and functions |
|---|---|
| Forecast (daily) | `app/services/forecasting_service.py`: `run_daily_forecast`, `run_forecast`, `_do_run`, `forecast_map`; `app/cli.py` (`forecast-daily`); `deploy/systemd/smartrest-forecast.{service,timer}` |
| ML | `app/ml/features.py` (`build_features`), `app/ml/train.py`, `app/ml/predict.py`, `app/ml/evaluate.py`, `app/ml/experiments.py` |
| Prep plan | `app/services/recommendation_service.py`: `compute_recommended`, `_preorder_totals`, `get_prep_plan`, `decide`, `set_prep_status`; page `app/templates/kitchen/prep.html` |
| Pre-orders | `app/services/kitchen_service.py`: `PREORDER_TRANSITIONS`, `create_pre_order`, `update_pre_order`, `pre_order_detail`, `list_pre_orders`, `upcoming_pre_orders`; `app/models/sales.py` (`PreOrder`); migration `migrations/versions/c4e1a7b9d052_pre_order_details.py`; page `app/templates/kitchen/orders.html` |
| BOM and ingredients | `recommendation_service._recipes`, `_requirements_for`, `get_requirements`, `get_ingredient_forecast`, `_reorder`; recipes edited in `app/templates/admin/catalog.html` |
| Inventory | `app/services/inventory_service.py`: `usable_map`, `stock_status`, `stock_levels`, FEFO stock-out |
| Alerts | `app/services/alert_service.py`: `_desired`, `evaluate`, `list_alerts`, `acknowledge` |
| Kitchen records and waste | `kitchen_service.record_prepared`, `record_served`, `record_waste`; `dashboard_service.waste_report`, `_waste_by_item`, `kitchen_daily_summary` |
| Admin dashboard | `dashboard_service.admin_dashboard`, `_inventory_alerts`, `recent_activity`, `_waste_rate`, `_coverage`, `_forecast_days`; `app/templates/admin/dashboard.html`; `app/static/js/pages/admin_dashboard.js` |
| Tests | `tests/integration/test_pre_orders.py`, `test_admin_dashboard.py`, `test_requirements_reorder_alerts.py`, `test_forecast_service.py`, `tests/test_architecture.py`, `tests/api/test_rbac.py`, `tests/ui/smoke.py` |
