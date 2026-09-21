# SmartRestaurant: Milestone 1 pseudocode

Written from the implementation as of 21 Sep 2026. Each section names the function it mirrors. Values in [brackets] are default settings (editable by the administrator). Stock and money use exact decimals; portions are whole numbers.

## 1. Demand forecasting

`app/ml/features.py`, `app/ml/train.py`, `forecasting_service.run_forecast`

**1a. Features.** One row per (menu item, date). Every history value looks back 7 days or more, so a forecast never uses recent or forecast values.

```
BuildFeatures(item, date):
  calendar  : day_of_week, is_weekend (Sat/Sun), month
  context   : is_public_holiday, is_poya, is_school_holiday   (holiday calendar)
              promo_discount_pct = largest promotion for item and date, else 0
              rain_mm, temp_c    = entered value, else average for that month
                                   (overall average if under ~1 year of weather data)
  history   : lag_7, lag_14, lag_21, lag_28  = portions sold on date-7, -14, -21, -28
              roll_mean_7  = mean of the 7 days ending date-7   (needs 4 days)
              roll_mean_28 = mean of the 28 days ending date-7  (needs 14 days)
  item      : one-hot flag per menu item
  when forecasting only: a missing history value is filled from the next weekly lag,
      then the rolling means, then the item's own average, and the row is marked "lags imputed"
```

**1b. Training and model choice** (run by the administrator or CLI).

```
TrainModel(sales history):
  holdStart = last sales date - 55 days                     // 56-day hold-out
  IF holdStart <= first sales date + 60 days: STOP "need more history"
  rows  = BuildFeatures for every item and date, target y = portions sold
  DROP rows with missing y, lag or rolling values
  train = rows before holdStart ;  hold = rows from holdStart
  hold.rain, hold.temp = monthly averages of the training period only
  FOR each candidate IN [naive_lag7, seasonal_mean4, random_forest, xgboost]:
      naive_lag7     : prediction = lag_7
      seasonal_mean4 : prediction = mean(lag_7, lag_14, lag_21, lag_28)
      random_forest, xgboost : fit on train, predict hold
      predictions below 0 become 0 ;  error = MAE(hold.y, prediction)
  winner = candidate with the lowest MAE  (a tie goes to the earlier one in the list)
  beats_baseline = MAE(winner) < MAE(naive_lag7)
  IF winner is a trained model: refit it on all usable rows
  save as a new model version (status "trained")
Activate(version): status = "active"; the previous active version becomes "retired"
```

**1c. Forecast run** (CLI or administrator; never trains).

```
RunForecast(asOf = today, horizon = [7] days):
  IF asOf is after today: REJECT
  create a run (status "running")
  IF there is no active model: run = "skipped", "No active model"; STOP
  dates = asOf ... asOf + horizon - 1
  features = BuildFeatures(all active items, dates), using sales before asOf only
  FOR each item:  days = number of dates with recorded sales for the item
      IF the active model is a baseline:       route = baseline  IF days >= 7 ELSE none
      ELSE IF item is in the model AND days >= [35]: route = model
      ELSE IF days >= 7:                        route = naive_lag7
      ELSE:                                     route = none  (no forecast)
  quantity = prediction of the route, negatives set to 0, rounded to 2 decimals
  method = "model" IF route is model ELSE "baseline"    // baseline rows show "*" (simple estimate)
  store the rows; older rows for the same item and date get is_latest = false (never overwritten)
  status = "skipped" IF no rows ; "partial" IF some items have none ; ELSE "ok"
  IF an unexpected error occurs: roll back, status = "failed" with a readable reason
```

## 2. Forecast period selection

`kitchen_forecast.js`, `GET /forecasts`, `forecasting_service.get_forecasts`

```
Kitchen forecast page:
  start = today (Asia/Colombo)  // user can step -1 / +1 day, pick a date, or press Today
  request forecasts from = start to = start + 6             // always a 7-day window

GetForecasts(start, end):                                   // dates must be valid, else validation error
  rows       = latest forecasts (is_latest) with target date in [start, end],
               only from runs whose asOf date is not after today
  missing    = dates in [start, end] that have no forecast    // shown as "-" plus a notice
  lastRun    = most recent run with asOf <= min(start, today) // never later than the selected date or today
  lastDate   = latest target date available (runs not after today)
  RETURN rows, missing, lastRun, lastDate, active model

Other windows:
  Prep plan            : one date (default today)
  Ingredient forecast  : fixed today ... today + 6
  Stock-out look-ahead : [7] days, never more than 7
```

## 3. Preparation recommendation

`recommendation_service.get_prep_plan`, `compute_recommended`, `decide`

```
Recommended(forecast, preorders, batch_size):
  IF there is no forecast: RETURN none                   // status "no_forecast"
  base = forecast x (1 + [10] / 100)                     // safety buffer
  need = MAX(base, confirmed pre-orders for the item and date)
  IF need <= 0: RETURN 0
  RETURN CEILING(need / batch_size) x batch_size         // whole batches

GetPrepPlan(date):  FOR each active menu item:
  forecast = latest forecast for the item and date
  recommended = Recommended(forecast, confirmed pre-orders, item batch size)
  status = saved decision's status ELSE "suggested" (or "no_forecast")
  also show prepared so far, served so far

Decide(item, date, action):                               // kitchen only
  REJECT if date is in the past, the item is inactive, or there is no forecast
  IF action = accept:   final = recommended
  IF action = override: final = quantity entered (>= 0) with a reason
                        warn IF final < confirmed pre-orders
  save one decision per item and date (update if it exists), audit it
```

## 4. Purchasing / reorder recommendation

`recommendation_service._daily_needs`, `get_reorder_suggestions`, `inventory_service.usable_map`

```
Usable(ingredient) = sum of remaining quantity in batches with no expiry or expiry >= today
OnOrder(ingredient) = sum(ordered - received) on purchase orders in draft, sent or partially received

DailyNeed(ingredient, day):
  FOR each menu item: qty = decision's final quantity IF one exists ELSE recommended
      skip items with no forecast, or with no recipe, or qty <= 0
      need += qty x recipe quantity per portion

Reorder(start = today):
  needs = DailyNeed for 7 days from start
  FOR each active ingredient:
      lead = default supplier's lead time ELSE [2] days ;  lead = between 1 and 7
      needLead = sum of daily need over the first `lead` days
      raw = needLead + safety stock (min_stock) - Usable - OnOrder
      IF raw <= 0: skip                                   // nothing to order
      suggested = MAX( CEILING(raw / pack_size) x pack_size,
                       CEILING(min_order_qty / pack_size) x pack_size )
  RETURN suggestions sorted by ingredient name
```

## 5. Stock-out risk alert

`alert_service._desired` and `evaluate`, `inventory_service.stock_status`

```
FOR each active ingredient:  usable = Usable(ingredient)
  critical = usable <= min_stock
  low      = usable > 0 AND usable <= reorder_level
  IF critical:  open "critical_stock" (severity critical)
  ELSE IF low:  open "low_stock"      (severity warning)

  cumulative = 0
  FOR each of the next 7 days:  cumulative += DailyNeed(ingredient, day)
      first day where cumulative > usable  = shortfall day, short by = cumulative - usable
  IF a shortfall day exists AND days from today < [7]:
      open "projected_stockout" (critical IF shortfall is today or tomorrow, ELSE warning)
```

Visibility: low and critical stock go to Administrator and Inventory; projected stock-out also goes to Food Production.

## 6. Food-waste risk alert

`alert_service._desired` and `evaluate`

```
window = the 7 days before today (today excluded)
FOR each active menu item:
  prepared = sum of prepared portions in the window
  wasted   = sum of wasted portions in the window
  IF prepared >= 20 AND wasted x 100 > prepared x [15]:   // waste rate above the limit
      open "waste_risk" (severity warning): "X% of prepared portions were wasted ... Consider preparing less"
```

Visibility: Administrator and Food Production.

**Alert life cycle (sections 5 and 6).**

```
Evaluate():                                          // when the last run is over 60 s old, or on refresh
  desired = all conditions above that are true now, for alert types that are enabled
  FOR each desired condition (identified by a key such as type + entity):
      no open alert with that key  -> create it
      open alert whose severity, message or date changed -> update it
  FOR each open alert whose key is no longer desired (type still enabled, not manual) -> close as "cleared"
```
