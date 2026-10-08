# Demo script: the functions added on 21 Sep 2026

**Figures in this script are for the university demonstration on Monday 12 October 2026**, with the demo data and model
of the 8 Oct reset (`v20261008-1`). They were computed from that data with the app's own calculations; a different day
or a rehearsal that is not rolled back changes them.

About 17 minutes, three roles, one story: **the kitchen plans a busy day, finds a chicken shortage, and the inventory manager fixes it while the administrator watches.** It covers all 15 new functions and the proposal function each one delivers. Trim points are marked *(optional)*.

Run it at `https://smartrest.developerstudio.space` (since 7 Oct 2026; gunicorn itself listens only on `127.0.0.1:39500` behind nginx). Use the three demo accounts (`admin`, `kitchen1`, `inventory1`) with the passwords from `.env`: `SEED_PASSWORD` for `kitchen1` and `inventory1`, `SEED_PASSWORD_ADMIN` for `admin` (since 7 Oct 2026; `flask smartrest demo-reset` sets them the same way). Open each role in its own browser profile or private window so you can switch without logging out.

## Which model is live: read before showing the Models or Monitoring pages

The demo was rebuilt with `flask smartrest demo-reset` on **8 October 2026**. That regenerated the synthetic history up
to 7 Oct and trained a new model, so **the live model is not the model evaluated in the research report**. The
report's results, methodology and conclusions belong to the original model and are unchanged; the demo model only
shows the system working on a fresh run of the same pipeline.

| | Original evaluated model (report) | Current demo model |
|---|---|---|
| Version | `v20261004-1` | `v20261008-1` |
| Trained | 4 Oct 2026 | 8 Oct 2026 (`demo-reset`) |
| Synthetic history | 1 Sep 2024 to 3 Oct 2026 (763 days), seed 42 | 1 Sep 2024 to 7 Oct 2026 (767 days), same generator and seed |
| Hold-out (last 56 days) | 9 Aug to 3 Oct 2026 | 13 Aug to 7 Oct 2026 |
| Training rows | 6,790 | 6,830 |
| Hold-out MAE: naive / mean of 4 weeks / Random Forest / XGBoost | 13.88 / 10.85 / 9.66 / **9.20** | 13.29 / 10.33 / 9.00 / **9.00** |
| Hold-out WAPE %: naive / XGBoost | 21.9 / 14.5 | 20.9 / 14.1 |
| XGBoost against naive (MAE) | 33.7% lower | 32.3% lower |
| Noise floor (MAE of the generator's expected demand) | 8.26 | 7.75 |
| Where its figures appear | `docs/ML_EVALUATION.md`, the report (Chapter 11, Appendix C) | Admin > Models; Admin > Monitoring > Forecast accuracy |

- **Quote the original model's figures** when discussing the research. The Models and Monitoring pages show the demo
  model's figures, which differ slightly.
- **The demo history is a new sample, not an extension.** Four more days shift the generator's random draws: comparing
  with the pre-reset backup, only 2.8% of the 7,630 item-days of 1 Sep 2024 to 3 Oct 2026 have the same quantity.
- **The demo model tells the same story.** XGBoost again cuts the naive error by about a third and is 1.25 portions
  above the noise floor; Random Forest and XGBoost are practically tied (MAE 9.0014 and 8.9978), in line with the
  report's statement that the two are not meaningfully different.
- The forecast-accuracy view shows the demo model's out-of-sample backfill for 13 Aug to 7 Oct, not the report's
  hold-out of 9 Aug to 3 Oct.
- If asked: *"The demo data was regenerated on 8 October for a fresh demonstration. The evaluation in the report is on
  the 4 October model; the regenerated run gives the same picture."*
- Every further `demo-reset` (needed after 14 Oct, when the current forecasts end) changes these figures again. The
  database with the original model is kept in `/root/smartrest/backups/smartrest_before_demo_reset_20261008_040726/`
  and its model file in `instance/models/v20261004-1/`; restoring that dump brings the original model back, but its
  data ends on 3 Oct and its forecasts on 10 Oct.

## Before you start (5 minutes, once)

1. **Take a dump so you can put the demo back afterwards.** From `/srv/smartrest`, as root (backups stay in the root-only `/root/smartrest/backups`):
   ```
   mariadb-dump --no-defaults -uroot -S .mariadb/mysql.sock --single-transaction smartrest > /root/smartrest/backups/before_demo.sql
   ```
   Restore later with `mariadb --no-defaults -uroot -S .mariadb/mysql.sock smartrest < /root/smartrest/backups/before_demo.sql`. Do not restore the older `before_deploy` or `before_tier1` dumps: they predate the new tables.
2. **Check the starting state on 12 Oct** (figures from the 8 Oct demo data, model `v20261008-1`; the 4 Oct figures used
   earlier are replaced; to check on the day, run `runuser -u smartrest -- .venv/bin/python scripts/usability_answers.py`):
   - Kitchen `/kitchen/prep`: Chicken Burger forecast **72.96**, recommended **84** (+10%, whole batches of 6).
   - Kitchen `/kitchen/requirements`: **Chicken** needs 40.68 kg, has 30 kg, short by **10.68 kg**; **Potato** needs 37.5 kg, has 35 kg, short by **2.5 kg**.
   - Inventory `/inventory/reorder`: **Chicken 80 kg** (Ceylon Poultry & Meats) and **Potato 50 kg** (Colombo Fresh Produce).
   - Inventory `/inventory`: Potato "critically low", Chicken "will run short today", two expired batches (Chicken
     `CHK-EXPIRED` 5 kg, Burger bun `BUN-OLD` 60 pcs) and several opening batches that expire on 12, 13 or 15 Oct.
3. Make sure the demo has a forecast for today: the Kitchen **Forecast** page must show numbers for 12 to 14 Oct (see
   "What looks different on 12 October" below for 15 to 18 Oct).
4. **Rehearse, then roll back.** The scenes create real records (pre-orders, requests, orders, stock). After a
   rehearsal, restore the dump from step 1 so the figures above hold on the day.

---

## Scene 1: Kitchen plans the day (about 6 minutes) — log in as `kitchen1`

| # | Do | You should see | Say |
|---|---|---|---|
| 1 | **Prep plan** (`/kitchen/prep`). Point at one card. On **Iced Milo** press **Mark unavailable**. | Card shows a red *Unavailable* badge; each card now has a *Confirmed pre-orders* line (0). Open **Dashboard**: the badge shows in the plan table. Press **Mark available** again. | *Manage Food Availability*: the manager can take an item off for the day. It does not change the forecast. |
| 2 | **Orders** > **Pre-orders** > **Add pre-order**: Chicken Burger, tomorrow, quantity **120**, note "Corporate lunch", status *Pending* > **Save**. | Row shows *Pending*. | *Manage Pre-Order*. |
| 3 | **Prep plan**, press the date arrow to **tomorrow**. | Chicken Burger: confirmed pre-orders **0**, recommended **84** (the pending pre-order is ignored). | Only confirmed pre-orders count. |
| 4 | Back to **Orders**, press **Confirm** on the pre-order, then repeat step 3. | Confirmed pre-orders **120**, recommended now **120** (120 is already whole batches of 6). | The prep quantity is `max(forecast x 1.10, pre-orders)` rounded up to whole batches. |
| 5 | **Orders** > **Daily orders** > add Chicken Burger, quantity **6**, note "Table 4", then **Fulfilled**. | Row moves to *Accepted*; no buttons any more. Try tomorrow's date: no form, the page points to Pre-orders. | *Manage Daily Order*: an internal record only, no prices or payments, no effect on the forecast. |
| 6 | **Prep plan** (today): on Chicken Burger type **24** in *Quantity* and **+ Add**. Then **Served & waste**, scroll to **Ingredient usage**. | Chicken expected **2.88 kg** (24 x 0.12), Burger bun 24, and so on. Type **3.1** for Chicken, note "extra for the sauce", **Save**. | Difference **+0.22** shows. *Record Ingredient Usage*: expected is prepared x recipe; the kitchen records what was actually used. It never changes stock. |
| 7 | **Ingredients** (`/kitchen/requirements`). | Chicken row in red: short by **10.68 kg**, with **Request stock** and **Report shortage** buttons. | *Ingredient Requirements* and *Shortage Reporting*. |
| 8 | On **Potato** press **Report shortage**, type "crate looks half empty" > OK. | Toast "Shortage reported to Inventory". | The report becomes a critical alert for Inventory and Admin. |
| 9 | **Stock requests** > **New request**: Cooking oil **10** L, note "Fryer top-up" > **Send request**. Send a second one: Egg **500** pcs, note "Breakfast batch". | Two cards, both *Pending*. | *Request Kitchen Stock*. |

*(Optional, 20 seconds)* On **Ingredients**, press **Request stock** next to Chicken: the form opens with Chicken and 10.68 kg filled in. Press **Cancel**; the real fix for a buying gap comes from procurement in Scene 2.

---

## Scene 2: Inventory and Procurement fixes it (about 7 minutes) — log in as `inventory1`

| # | Do | You should see | Say |
|---|---|---|---|
| 1 | **Dashboard**. | A **Kitchen requests** card: **2 waiting for a decision**. In *Alerts*: the critical *Kitchen reports a shortage of Potato*, plus the Chicken and Potato stock-out alerts. | The kitchen's shortage report arrived as an alert. |
| 2 | **Kitchen requests**. Open the **Egg** request > **Reject** > reason "Next delivery is Thursday" > **Reject request**. | Status *Rejected*. | *Manage Kitchen Stock Requests*: a reason is required, and the kitchen sees it. |
| 3 | Open the **Cooking oil** request > **Approve** > **Issue stock** (quantity is prefilled with 10) > **Issue**. | Status *Issued*. Then **Record stock**: the history has a stock-out with note "Kitchen request #..". | Issuing checks that every line can be covered by usable stock, takes the earliest-expiry batch first, and never issues expired stock. Partial issue is allowed. |
| 4 | **Reorder**. Tick **Chicken** and **Potato**. The button now reads *Create purchase orders (2 suppliers)*. Press it. | You land on **Purchase orders** with two drafts (one per supplier). Open **Reorder** again: it now says *Nothing needs reordering right now*, because a draft already counts as "on order". | *Manage Purchase Orders*, created straight from the recommendation. Nothing is sent to a supplier: "sent" is marked by hand. |
| 5 | Open the **Chicken** order > **Mark as sent** > **Receive stock**: change the quantity to **40**, set an expiry date about a week ahead > **Record receipt**. | *Partially received*, outstanding **40 kg**. | Receiving creates the stock batch and the stock-in record linked to the order. A line can never receive more than is outstanding (try 100 first: the page refuses it next to the line). |
| 6 | Receive the remaining **40 kg**, then open the **Potato** order and receive **50**. | Both orders *Received*. | The reorder formula already counted "on order" and stock, so it needed no change: the recommendation, the order and the stock all agree. |
| 7 | **Record stock** > **Wastage**: Chicken, **5**, reason *Expired*. Then Burger bun, **60**, reason *Expired* (on 12 Oct the old bun batch has expired too). | Both expired batches are written off (expired stock is taken first). | *Inventory Wastage Recording* (already existed). We do it now so the next step is clean. |
| 8 | **Adjustment** tab: pick Chicken. The page shows *System on hand: N kg*. Enter **N minus 2**, reason "Stock take: 2 kg spillage" > **Save**. | The live line shows *difference -2*; history shows an *adjustment* of -2. | *Stock Adjustment*: you enter the counted quantity, the system posts the difference, and a reason is mandatory. Enter the same number again and it says there is nothing to adjust. |
| 9 | **Stock** > **Data check** > **Run data check**. | Green "No problems found", checked 20 ingredients, no expired stock listed (both expired batches were written off in step 7). | *Validate Inventory Data*: the recorded movements add up exactly to the stock in the batches. (Also available as `flask smartrest check-stock`.) |
| 10 | **Suppliers** > **Add supplier** "Island Spice Traders", lead time 2 > **Save**, then **Deactivate** it. Open **Purchase orders** > **New purchase order**. | The supplier list does **not** include Island Spice Traders. | *Manage Suppliers*. A deactivated supplier keeps its history but cannot be chosen for new orders. |

---

## Scene 3: The Administrator watches (about 4 minutes) — log in as `admin`

| # | Do | You should see | Say |
|---|---|---|---|
| 1 | **Dashboard** > **Run alert check**. | The Chicken projected stock-out and the Potato critical-stock alerts are gone; the *shortage of Potato* report has closed by itself (the ingredient was restocked). Expiry warnings for opening batches that expire today or soon stay, which is correct. | Alerts clear when the cause is fixed. |
| 2 | **Inventory** (new sidebar entry). Walk through the four tabs; on *Stock levels* press **Download stock levels (CSV)**. | Stock levels, 7-day ingredient demand, batches with expiry, recent movements. | *Inventory Monitoring* and *Inventory Demand Forecast Monitoring*: read-only, same numbers as the inventory manager's screens. |
| 3 | **Monitoring** > **Demand forecast**. | Next 7 days per item, with totals and a chart. Model name and last run at the top. | *Food Demand Forecast Monitoring*. |
| 4 | **Forecast accuracy**: choose **Chicken Burger** in *Menu item*. | The forecast-versus-actual chart and the error table follow the item; the CSV link keeps the filter. | Accuracy per item, not just overall. |
| 5 | **Analytics**. | Average portions by weekday (Friday to Sunday highest), holiday and promotion days against ordinary days, forecast error over time, waste rate over time. The period and "Synthetic demo data" are stated. | *System Analytics*. Read the small print aloud: differences between kinds of day describe the data; they do not prove that a holiday or promotion caused them. |
| 6 | **Inventory** tab, ingredient **Chicken**. | Closing stock day by day: today's steps up with the two receipts and down with the adjustment. **Download CSV**. | *System Reports*: rebuilt from the recorded movements, and the last figure equals the stock on hand. |
| 7 | **Stock movements** tab, type **Stock in**. | The receipts appear with **Linked to: purchase_order #..**. Set the type to *Stock out*: the oil issue shows **stock_request #..**. | Everything is traceable to the order or request that caused it. |
| 8 | **Settings** > **Restaurant information**: change the name to "Lanka Bites", **Save**, reload. | The name appears in the sidebar under the brand. Change it back afterwards. | *Restaurant Information Management*. |
| 9 | Switch to the `kitchen1` window and open `/inventory/requests`. | **Access denied (403)**. | Role-based access: the kitchen cannot open the inventory manager's pages. |

---

## Proposal functions covered

| Function (proposal) | Scene and step |
|---|---|
| Manage Food Availability | 1.1 |
| Manage Pre-Order | 1.2 to 1.4 |
| Manage Daily Order | 1.5 |
| Record Ingredient Usage | 1.6 |
| Shortage Reporting | 1.8 (arrives in 2.1, closes in 3.1) |
| Request Kitchen Stock | 1.9 |
| Manage Kitchen Stock Requests | 2.2, 2.3 |
| Manage Purchase Orders | 2.4 to 2.6 |
| Stock Adjustment | 2.8 |
| Validate Inventory Data | 2.9 |
| Manage Suppliers | 2.10 |
| Inventory Monitoring, Inventory Demand Forecast Monitoring | 3.2 |
| Food Demand Forecast Monitoring | 3.3, 3.4 |
| System Analytics | 3.5 |
| System Reports (inventory and movements, CSV) | 3.6, 3.7 |
| Restaurant Information Management | 3.8 |

## What looks different on 12 October (expected, not faults)

The demo data ends on 7 Oct and the forecasts run from 8 to 14 Oct (8 Oct reset). On 12 Oct, therefore:

- **Forecast pages** (Kitchen **Forecast**, Admin **Monitoring** > *Demand forecast*) show 12 to 14 Oct and "No forecast yet" for
  15 to 18 Oct.
- **Reorder** and **Ingredient demand** show a yellow note that the menu items have no forecast for 4 of the next 7 days, so
  their quantities cover 12 to 14 Oct only. The note is correct: it is the safeguard added on 7 Oct.
- **No sales after 7 Oct** are in the demo data, so "yesterday" on the dashboards is empty and the 7-day sales chart on the
  Admin dashboard only has 5 to 7 Oct.
- **Forecast accuracy** (default period 14 Sep to 11 Oct) has 240 forecast-vs-actual pairs, the last on 7 Oct; for
  **Chicken Burger** MAE **11.47**, WAPE **13.1%**.
- **Alerts on 12 Oct:** Chicken low; Chicken and Potato will run short on 12 Oct (by 10.68 kg and 2.50 kg); Potato critically
  low; Chicken `CHK-EXPIRED` and Burger bun `BUN-OLD` expired; opening batches of Chicken, Burger bun, Kottu roti, Lettuce and
  Mixed vegetables expire on 12 Oct, Beef patty, Tomato and Milk on 13 Oct, Wrap tortilla and Lime on 15 Oct; waste risk on
  Veggie Burger (19%).
- **Safety buffer example** (usability task A4 or a question): raising the buffer from 10% to 12% changes only **Veggie
  Burger, 24 to 28**; the other items stay the same because recommendations are rounded up to whole batches.
- **Pre-order steps** (Scene 1, steps 3 and 4) are unchanged: tomorrow, 13 Oct, Chicken Burger is recommended **84**, and
  **120** once the pre-order of 120 is confirmed.

## If something looks different

- **Different numbers:** the forecast run changes them slightly. The logic still holds (for example, the recommendation with a confirmed pre-order is the larger of the two rounded up to the batch size).
- **A screen says "No forecast yet" for 15 to 18 Oct:** expected on 12 Oct (see below). **Do not press Run forecast now during
  the demo**: a new run replaces the forecasts for 12 to 14 Oct and changes every figure in this script.
- **An alert did not clear straight away:** alerts refresh at most once a minute; press **Run alert check** on the Admin dashboard.
- **You want to repeat the demo:** restore `backups/before_demo.sql` (see above), or ask for a reset to the seeded demo state.

## After the demo

Restore the dump, or delete what you created: cancel or leave the draft orders, and set the restaurant name back. The purchase orders, requests, pre-order and adjustment are real records in the demo database.
