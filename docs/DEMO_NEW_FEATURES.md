# Demo script: the functions added on 21 Sep 2026

About 17 minutes, three roles, one story: **the kitchen plans a busy day, finds a chicken shortage, and the inventory manager fixes it while the administrator watches.** It covers all 15 new functions and the proposal function each one delivers. Trim points are marked *(optional)*.

Run it at `https://smartrest.developerstudio.space` (since 7 Oct 2026; gunicorn itself listens only on `127.0.0.1:39500` behind nginx). Use the three demo accounts (`admin`, `kitchen1`, `inventory1`) with the `SEED_PASSWORD` value from `.env` (the demo was rebuilt with `flask smartrest demo-reset` on 4 Oct 2026, which resets all three passwords to it). Open each role in its own browser profile or private window so you can switch without logging out.

## Before you start (5 minutes, once)

1. **Take a dump so you can put the demo back afterwards.** From `/srv/smartrest`, as root (backups stay in the root-only `/root/smartrest/backups`):
   ```
   mariadb-dump --no-defaults -uroot -S .mariadb/mysql.sock --single-transaction smartrest > /root/smartrest/backups/before_demo.sql
   ```
   Restore later with `mariadb --no-defaults -uroot -S .mariadb/mysql.sock smartrest < /root/smartrest/backups/before_demo.sql`. Do not restore the older `before_deploy` or `before_tier1` dumps: they predate the new tables.
2. **Check the starting state** (the figures below are from the `demo-reset` of 4 Oct 2026 with the corrected holiday calendar, model `v20261004-1`; a different run or day changes them slightly):
   - Kitchen `/kitchen/requirements`: **Chicken** needs 47.48 kg, has 30 kg, short by **17.48 kg**; **Potato** short by 17.5 kg.
   - Inventory `/inventory/reorder`: **Chicken 80 kg** (Ceylon Poultry & Meats) and **Potato 60 kg** (Colombo Fresh Produce).
   - Inventory `/inventory`: Potato "critically low", Chicken "will run short today", one expired chicken batch (5 kg).
3. Make sure the demo has a forecast for today: the Kitchen **Forecast** page must show numbers, not "No forecast yet".

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
| 7 | **Ingredients** (`/kitchen/requirements`). | Chicken row in red: short by **17.48 kg**, with **Request stock** and **Report shortage** buttons. | *Ingredient Requirements* and *Shortage Reporting*. |
| 8 | On **Potato** press **Report shortage**, type "crate looks half empty" > OK. | Toast "Shortage reported to Inventory". | The report becomes a critical alert for Inventory and Admin. |
| 9 | **Stock requests** > **New request**: Cooking oil **10** L, note "Fryer top-up" > **Send request**. Send a second one: Egg **500** pcs, note "Breakfast batch". | Two cards, both *Pending*. | *Request Kitchen Stock*. |

*(Optional, 20 seconds)* On **Ingredients**, press **Request stock** next to Chicken: the form opens with Chicken and 17.48 kg filled in. Press **Cancel**; the real fix for a buying gap comes from procurement in Scene 2.

---

## Scene 2: Inventory and Procurement fixes it (about 7 minutes) — log in as `inventory1`

| # | Do | You should see | Say |
|---|---|---|---|
| 1 | **Dashboard**. | A **Kitchen requests** card: **2 waiting for a decision**. In *Alerts*: the critical *Kitchen reports a shortage of Potato*, plus the Chicken and Potato stock-out alerts. | The kitchen's shortage report arrived as an alert. |
| 2 | **Kitchen requests**. Open the **Egg** request > **Reject** > reason "Next delivery is Thursday" > **Reject request**. | Status *Rejected*. | *Manage Kitchen Stock Requests*: a reason is required, and the kitchen sees it. |
| 3 | Open the **Cooking oil** request > **Approve** > **Issue stock** (quantity is prefilled with 10) > **Issue**. | Status *Issued*. Then **Record stock**: the history has a stock-out with note "Kitchen request #..". | Issuing checks that every line can be covered by usable stock, takes the earliest-expiry batch first, and never issues expired stock. Partial issue is allowed. |
| 4 | **Reorder**. Tick **Chicken** and **Potato**. The button now reads *Create purchase orders (2 suppliers)*. Press it. | You land on **Purchase orders** with two drafts (one per supplier). Open **Reorder** again: it now says *Nothing needs reordering right now*, because a draft already counts as "on order". | *Manage Purchase Orders*, created straight from the recommendation. Nothing is sent to a supplier: "sent" is marked by hand. |
| 5 | Open the **Chicken** order > **Mark as sent** > **Receive stock**: change the quantity to **40**, set an expiry date about a week ahead > **Record receipt**. | *Partially received*, outstanding **40 kg**. | Receiving creates the stock batch and the stock-in record linked to the order. A line can never receive more than is outstanding (try 100 first: the page refuses it next to the line). |
| 6 | Receive the remaining **40 kg**, then open the **Potato** order and receive **60**. | Both orders *Received*. | The reorder formula already counted "on order" and stock, so it needed no change: the recommendation, the order and the stock all agree. |
| 7 | **Record stock** > **Wastage**: Chicken, **5**, reason *Expired*. | The expired batch is written off. | *Inventory Wastage Recording* (already existed). We do it now so the next step is clean. |
| 8 | **Adjustment** tab: pick Chicken. The page shows *System on hand: N kg*. Enter **N minus 2**, reason "Stock take: 2 kg spillage" > **Save**. | The live line shows *difference -2*; history shows an *adjustment* of -2. | *Stock Adjustment*: you enter the counted quantity, the system posts the difference, and a reason is mandatory. Enter the same number again and it says there is nothing to adjust. |
| 9 | **Stock** > **Data check** > **Run data check**. | Green "No problems found", checked 20 ingredients, no expired stock listed. | *Validate Inventory Data*: the recorded movements add up exactly to the stock in the batches. (Also available as `flask smartrest check-stock`.) |
| 10 | **Suppliers** > **Add supplier** "Island Spice Traders", lead time 2 > **Save**, then **Deactivate** it. Open **Purchase orders** > **New purchase order**. | The supplier list does **not** include Island Spice Traders. | *Manage Suppliers*. A deactivated supplier keeps its history but cannot be chosen for new orders. |

---

## Scene 3: The Administrator watches (about 4 minutes) — log in as `admin`

| # | Do | You should see | Say |
|---|---|---|---|
| 1 | **Dashboard** > **Run alert check**. | The Chicken projected stock-out and the Potato critical-stock alerts are gone; the *shortage of Potato* report has closed by itself (the ingredient was restocked). | Alerts clear when the cause is fixed. |
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

## If something looks different

- **Different numbers:** the forecast run changes them slightly. The logic still holds (for example, the recommendation with a confirmed pre-order is the larger of the two rounded up to the batch size).
- **A screen says "No forecast yet":** a forecast has not been run for today. As Admin, open **Models** and press **Run forecast now**.
- **An alert did not clear straight away:** alerts refresh at most once a minute; press **Run alert check** on the Admin dashboard.
- **You want to repeat the demo:** restore `backups/before_demo.sql` (see above), or ask for a reset to the seeded demo state.

## After the demo

Restore the dump, or delete what you created: cancel or leave the draft orders, and set the restaurant name back. The purchase orders, requests, pre-order and adjustment are real records in the demo database.
