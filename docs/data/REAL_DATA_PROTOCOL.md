# Real Sri Lankan restaurant data: collection and validation protocol

*Written 9 October 2026 after the proposal-versus-implementation audit. **No real Sri Lankan restaurant data exists in
this project yet.** The system and its demonstration run on synthetic data; the forecasting method was evaluated
offline on external public datasets (Yaz, Germany; Sandwich Analytics Part II, US; UCI Online Retail II, UK), which are
not Sri Lankan. This protocol describes how real data may be obtained and checked; it must never be replaced by
invented or adjusted figures.*

## 1. Purpose

The proposal aims to establish whether machine learning can produce reliable forecasts **for Sri Lankan fast-food
restaurants**. That question can only be answered with the sales history of a real outlet. The application needs no
change to use it: the existing CSV import (`POST /api/v1/sales/import`, Data page) and `flask smartrest evaluate`
already accept and evaluate real sales.

## 2. Partner and permissions [TEAM]

1. Approach one fast-food outlet (Colombo or elsewhere in Sri Lanka) through a team member's contact. Use the request
   letter in `DATA_REQUEST_TEMPLATE.md`.
2. Obtain **written permission** from the owner or an authorised manager, stating what is shared, for what purpose,
   how it is stored and when it is deleted.
3. Check with the module leader whether **ethics approval** or a university consent form is required, and use it.
4. Agree how the outlet is named in the report: by name only with written consent; otherwise "a fast-food outlet in
   Colombo".

## 3. What to ask for

| File | Content | Required |
|---|---|---|
| `sales.csv` | `date,item,quantity[,unit_price]`: **one row per menu item per day**, daily totals of portions sold, dates as `YYYY-MM-DD`, UTF-8 | Yes |
| History | at least **146 days** (the training needs a 56-day hold-out plus 90 days); **12 to 24 months recommended** so Avurudu, Poya days, school holidays and December are included | Yes |
| `closed.csv` | `date`: days the outlet was closed (they stay unrecorded, never zero) | Yes, if any |
| `mapping.csv` | `outlet_item,menu_item`: the outlet's item names and the SmartRestaurant menu item each corresponds to | Yes |
| Promotions | item, start date, end date, discount % (entered on the Promotions page) | If any |
| Recipes, daily waste | only for ingredient and waste evaluation | Optional |

**Never ask for or accept** customer names, phone numbers, card or payment data, staff names, or individual receipts.
A point-of-sale "item sales by day" report exported to CSV is enough.

Weather comes from a public historical source (for example the Department of Meteorology or a historical weather
service), with the source and access date recorded. Holidays use the existing declared calendar (`data/holidays_lk.csv`).

## 4. Provenance record

For each file received, record in a private provenance note (not in the repository):
who exported it, from which system, on which date, the period covered, and the SHA-256 printed by the checker below.

## 5. Validation (before any import)

1. Run the read-only checker (it reads the files only; no database, no network):

   ```
   .venv/bin/python scripts/validate_sales_csv.py sales.csv --mapping mapping.csv --closed closed.csv --out check.md
   ```

   It checks the columns, ISO dates, whole quantities from 0 to 10,000, one row per item and day, item names against
   the mapping, the 146-day minimum, days more than 10 x an item's typical day (the import's outlier rule), and lists
   dates with no rows that are not marked closed. It prints the file's SHA-256 and a table of **monthly totals**.
2. Ask the outlet manager to compare the monthly totals with their own records and **sign the table** (paper or
   e-mail). Investigate any month that differs.
3. Spot-check about ten days against the outlet's own daily reports or receipts.
4. Correct problems **only at the source** (a new export from the outlet), never by editing numbers by hand. Every
   change is recorded in the provenance note.

## 6. Where the data goes

- **Never into the live demonstration system** (`/srv/smartrest`) or its database.
- Into a separate, isolated instance (as was done for the Yaz evaluation): its own system user, its own SQLite file,
  no public port. Import with a **dry run first**, then commit; then run `flask smartrest train` and
  `flask smartrest evaluate --json results.json` there.
- Raw files stay in a root-only folder, are not committed to Git, and are deleted when the project ends (or as agreed
  with the outlet).

## 7. Reporting

- Report the outlet's data separately from the synthetic results and from the external datasets.
- State the period, the number of items and days, the closed days, the reconciliation result and every limitation.
- Report the comparison with **both** simple rules (same day last week and the 4-week average) with significance
  tests, as in the external evaluations.

## 8. Timeline and fallback

The final report is due on 18 October 2026. If no partner data has passed validation by about **15 October 2026**,
do not use partial or unverified data. Keep the current, accurate wording (synthetic system data plus external
real-data validation) and list Sri Lankan validation as the first future recommendation.
