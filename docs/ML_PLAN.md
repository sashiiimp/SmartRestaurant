# SmartRestaurant: ML and decision-rules plan

Read `REQUIREMENTS.md` (S1-S6, A16), `ARCHITECTURE.md` section 6, and `DATABASE.md` first.

**Part A** is the forecasting model (`app/ml`, called only through `ForecastingService`). **Part B** is the deterministic decision logic that turns forecasts into preparation quantities, ingredient requirements, reorder suggestions and alerts (`RecommendationService`, `AlertService`). Part B is not ML, but it is where the demo's value is visible, so it is specified exactly and tested by hand calculation.

---

# Part A: Demand forecasting

## 1. Scope and decisions

| # | Decision |
|---|---|
| M-1 | Target: quantity sold per menu item per day (A4, A5), horizon 7 days starting **today** (history ends yesterday). |
| M-2 | **One global model for all items**, with the item as a one-hot feature. About 10 items x 24 months is roughly 7.5k rows. That is too little for a model per item, and a global model shares what is learned about weekdays and holidays. |
| M-3 | Candidates: two baselines (`naive_lag7`, `seasonal_mean4`), Random Forest and XGBoost, exactly the proposal's stack. No deep learning, no ARIMA. |
| M-4 | **No recursive forecasting.** Every history feature is lagged by **7 days or more**, so all 7 days are predicted directly from actuals with no predicted value fed back. This also makes leakage impossible by construction. |
| M-5 | Selection is by **hold-out MAE**, judged against `naive_lag7` (S1). If nothing beats it, the baseline becomes the active model and the UI and report say so. |
| M-6 | Weather at forecast time is a **seasonal average** unless the admin has entered weather for that date (I5 in REQ). No weather API in the MVP; it is a postponed extension. |
| M-7 | Everything is reproducible: generator seed 42, `random_state=42`, library versions pinned in `requirements.txt` and stored inside each artifact. |
| M-8 | **Environment check on day 0:** this machine has Python 3.14, and binary wheels for scikit-learn, XGBoost and pandas may not exist for it. If `pip install` has to compile them, use Python 3.12 for the project venv instead. Decide before writing any code. |

## 2. Synthetic data generator (`app/seed/generate.py`)

There is no real restaurant data (A3). The generator produces a labelled, documented dataset with **known, deliberately simple effects**, so the model has real structure to find and the evaluation is meaningful. It does not prove accuracy on a real restaurant, and every screen and report that shows results says "synthetic".

Period: 2024-09-01 to yesterday (about 750 days) x 10 items.

```
expected(item, day) = base_item * dow[day] * month[day] * holiday_effect * promo_effect * rain_effect * trend(day)
sold(item, day)     = Poisson( expected * LogNormal(0, 0.10) )
```

| Effect | Rule (all values are assumptions of the generator, not measurements) |
|---|---|
| Base | 25 to 140 portions per day per item (fries and burgers highest, drinks about 50) |
| Day of week | Mon 0.85, Tue 0.85, Wed 0.90, Thu 0.95, Fri 1.20, Sat 1.30, Sun 1.15 |
| Month | April and December x1.15 (festive seasons), other months x1.0 |
| Public holiday (not Poya) | x1.15 all items |
| **Poya day** | meat items (chicken burger, beef burger, fried chicken, chicken kottu, chicken wrap) x0.65; veg items x1.10. Assumed effect; it gives the model a strong item-by-holiday interaction to learn. |
| School holiday | x1.10 for burgers, fries, drinks |
| Promotion | covered items x(1 + 0.02 x discount_pct), for example 15% off gives x1.30; about 24 promotions of 5 to 10 days, one or two items each, plus two all-item promotions |
| Rain | x(1 - 0.004 x min(rain_mm, 40)); drinks use twice the coefficient |
| Trend | +10% linear over the whole period |

Weather (Colombo pattern, assumed): monthly wet-day probability (Jan 0.20, Feb 0.15, Mar 0.25, Apr 0.45, May 0.65, Jun 0.55, Jul 0.45, Aug 0.45, Sep 0.50, Oct 0.65, Nov 0.60, Dec 0.40), rain on a wet day is Gamma with mean 12 mm, temperature 26 to 31 C with a mild annual cycle. Source `synthetic`.

Holidays come from `data/holidays_lk.csv` (public, Poya, school-term holidays, 2024-09 to 2026-12). **The builder curates this file from the official published Sri Lanka calendar** (I cannot verify dates offline). The generator reads the same file, so the demo stays self-consistent even if a date is wrong; verify it before the report is submitted. *(Done 4 Oct 2026: Poya days and movable holidays replaced by the declared dates; see `ML_EVALUATION.md` section 7. School vacations remain approximate.)*

Also generated (for waste and S6): `prepared = max(round(sold * (1 + e)), sold)` with `e ~ Normal(0.15, 0.10)` clipped to [-0.05, 0.60], and `waste = prepared - sold` when positive (reason 80% overproduction, 10% quality, 10% expired).

Known simplifications, stated in the report: sales are not censored by stock-outs (real sales understate demand when an item sells out), no price elasticity beyond promotions, no trend breaks.

The generator also writes `data/synthetic/oracle_expected.csv` (the noise-free `expected` values, **never loaded into the app**). The MAE of the oracle is the best any model could do, which lets the report say how close each model gets.

## 3. Features (`ml/features.py`, `build_features`)

One function builds features for training and for inference (NFR6, no train/serve skew). Input: sales history DataFrame, context DataFrames, list of target dates. Output: one row per (item, date).

| Group | Feature | Definition |
|---|---|---|
| Calendar | `dow`, `is_weekend`, `month` | from the target date |
| Context | `is_public_holiday`, `is_poya`, `is_school_holiday` | from `holidays`; known in advance |
| Context | `promo_discount_pct` | 0 if no active promotion covers the item that day; known in advance if the admin has entered it |
| Context | `rain_mm`, `temp_c` | weather row if present, else seasonal average (section 4) |
| History | `lag_7`, `lag_14`, `lag_21`, `lag_28` | sold on target date minus k days (k >= 7) |
| History | `roll_mean_7` | mean sold over target-13 .. target-7 |
| History | `roll_mean_28` | mean sold over target-34 .. target-7 |
| Item | `item_<id>` | one-hot |

Missing-vs-zero follows `DATABASE.md` section 2.3 (an item absent on a recorded day is 0; a day with no rows is missing).

Training rows need all lags present, so each item's first 28 recorded days are dropped from training. At inference a missing lag is filled from the next weekly lag (`lag_k` from `lag_{k+7}`), else from `roll_mean_28`, and the run records `lags_imputed = true` in the forecast's `input_snapshot`.

**Unit test (`tests/unit/test_features.py`): perturbing any sales value on or after target-6 must not change that target's features.**

## 4. Missing data and weather (S5, NFR3)

| Situation | Behaviour |
|---|---|
| No weather row for the target date | Use the **seasonal average**: mean `rain_mm` and `temp_c` for that month over the weather history (overall mean if under 12 months). Snapshot has `weather_estimated = true`; the UI shows a small "weather estimated" tag. |
| Admin entered forecast weather for a future date | Used, with `weather_estimated = false`. |
| No holiday or promo data for the date | Treated as "no event". Not an error. |
| Item history under `min_history_days` (35) but at least 7 days | `method = baseline` (`naive_lag7` fallback), labelled in the UI. |
| Item history under 7 days, or item not in the active model | No forecast row; UI says "Not enough history"; run status `partial`. |
| No active model | Run status `skipped`, reason "no active model", no forecasts, a `forecast_failed` warning alert. |
| Any exception during a run | Run status `failed`, reason stored, alert raised, readable message in the UI, full trace in the log only. |

**Honest evaluation.** In the hold-out set, weather features are replaced by the seasonal estimate computed from the training period, because that is what the model actually sees when it forecasts tomorrow. A model trained on actual rain but served an average would otherwise look better than it is.

## 5. Training and selection (`ml/train.py`)

1. Load the full history with `build_features`.
2. **Time-based split:** the last **56 days** (8 whole weeks) are the hold-out; everything earlier is training. No shuffling, no cross-validation, no tuning grid in the MVP. *(Added 4 Oct 2026, outside the MVP: a rolling-origin cross-validation over six 28-day windows, `flask smartrest evaluate`; results in `ML_EVALUATION.md` section 4.)*
3. Fit and predict on the hold-out for each candidate:

| Candidate | Setup |
|---|---|
| `naive_lag7` | prediction = `lag_7` (S1's baseline: same weekday last week) |
| `seasonal_mean4` | mean of `lag_7, lag_14, lag_21, lag_28` |
| `random_forest` | `RandomForestRegressor(n_estimators=300, min_samples_leaf=3, n_jobs=-1, random_state=42)` |
| `xgboost` | `XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, random_state=42)` |

4. Predictions are clipped at 0. Compute the metrics of section 6 for each candidate.
5. Winner = lowest hold-out MAE; ties go to the simpler model. `beats_baseline` = winner MAE < `naive_lag7` MAE. If the winner is a baseline, say so in `selection_reason`.
6. **Refit the winning algorithm on all available history** and save the artifact. (The reported metrics belong to the train-only fit; the shipped model differs only by having seen 8 more weeks. State this in the report.)
7. Save `instance/models/<version_label>/model.joblib` (dict: model, feature column list, item ids, library versions, trained_at) and insert the `model_versions` row (`status = trained`). Activation is a separate explicit step (A16).

Postponed: hyperparameter search, feature ablation, prediction intervals, per-item models. **Stretch (S), about 1 hour:** an ablation table (calendar+lags, then +holiday, then +promo, then +weather) for the winner, which directly answers the proposal's question about contextual factors. *(Done 4 Oct 2026 with `flask smartrest evaluate`, together with segment errors on holiday, promotion and wet days; `ML_EVALUATION.md` section 5.)*

## 6. Evaluation and metrics

| Metric | Definition |
|---|---|
| MAE | mean of \|pred - actual\| (primary, used for selection) |
| RMSE | square root of mean squared error |
| MAPE | mean of \|error\| / actual over rows with actual > 0; the number of excluded rows is reported |
| WAPE | sum of \|error\| / sum of actual (stable when quantities are small) |
| R2 | 1 - SSE / SST on the hold-out |
| Bias | mean of (pred - actual); positive means over-forecasting, which turns into waste |

`model_versions.metrics` JSON shape:

```json
{"overall":  {"naive_lag7": {"mae": 0, "rmse": 0, "mape": 0, "mape_excluded": 0, "wape": 0, "r2": 0, "bias": 0},
              "seasonal_mean4": {}, "random_forest": {}, "xgboost": {}},
 "per_item": {"1": {"naive_lag7": {}, "<winner>": {}}},
 "holdout_rows": 560,
 "oracle_mae": 0,
 "feature_importance": [{"feature": "lag_7", "importance": 0.0}]}   // one-hot item columns are summed into "menu_item (which item)"
```

**Acceptance criteria**

| # | Criterion | Kind |
|---|---|---|
| 1 | Chosen model's hold-out MAE is below `naive_lag7`'s, or the baseline is used and reported (S1) | pass or honest fail |
| 2 | Overall hold-out WAPE about 15% or lower on the synthetic set | **target, not a promise**; it depends on the generator's noise, so it is reported next to `oracle_mae` |
| 3 | No item with WAPE above 30% without an explanation in the report | check |
| 4 | Forecast run under 5 s for 7 days x 10 items (NFR2); training under 60 s on this 2-core machine | measured (`TESTING.md`) |

Live monitoring (A9) recomputes MAE, WAPE, MAPE and bias from stored forecasts against actuals as kitchen data arrives, using the accuracy rule in `DATABASE.md` 2.6.

## 7. Inference and lifecycle

`ForecastingService.run_forecast(outlet_id, as_of, horizon, trigger, use_estimated_weather=False)`:

1. Create a `forecast_runs` row (`started_at`).
2. Load active model (cached per worker, reloaded when the active id in `model_versions` changes; ARCH section 6).
3. For each active item: choose model or baseline by section 4; build features for `as_of ... as_of+horizon-1`; predict.
4. In one transaction: insert `forecasts` (with `input_snapshot`), flip `is_latest` on the previous rows for those (item, date), set the run's status, reason and counts.
5. Return the run summary. The CLI then calls alert evaluation (ARCH section 6).

**Backfill** (`flask smartrest forecast --from D1 --to D2`): one single-day run per date with `as_of = that date`, `trigger = backfill`, `use_estimated_weather = true`. This fills the past 56 days so the A9 forecast-vs-actual chart is populated on demo day. **Backfill uses `eval_model`, the copy fitted on the training period only** (the shipped model is refit on all history and has seen those days), so forecasts for the hold-out days are genuinely out-of-sample. Run it after `train --activate`. A backfill that starts before the active model's hold-out is refused (those days were in `eval_model`'s training data), and an ordinary run cannot start on a past date, so no in-sample forecast can reach the accuracy views.

Retraining is manual (`flask smartrest train`, or the admin button), recommended weekly once real data flows. Rollback = activate the previous version. There is no scheduler (ARCH D6).

## 8. Time-box and risks

| Risk | Response |
|---|---|
| ML eats the schedule | **Cap: 5 hours in total on day 1.** If after two attempts the model does not beat the baseline, ship the honest result and continue; the decision layer matters more to the demo. |
| Result looks too good on synthetic data | Say so; show `oracle_mae`; never quote the numbers as real-world accuracy. |
| RF or XGBoost handles NaN differently | No NaNs reach the model: imputation happens in `build_features` and is logged. |
| Library or Python version problems | M-8 check on day 0; versions stored in the artifact and checked on load. |
| New item added after training | Not in the model's item list, so it gets a baseline or no forecast until retrained (section 4). |

---

# Part B: Decision rules (deterministic)

All money and quantities use `Decimal`; rounding rules are exact. Each rule has a hand-calculated test in `TESTING.md` section 4.

## B1. Preparation quantity (S2, K3)

```
base        = forecast_qty * (1 + safety_buffer_pct / 100)
need        = max(base, confirmed_preorders)
recommended = ceil(need / batch_size) * batch_size      (0 if need = 0)
```

This satisfies all three parts of K3: buffer applied, rounded up to a batch, never below confirmed pre-orders (rounding is applied after the floor, so the result is a batch multiple and never below the floor). No forecast gives `status = no_forecast` and no number.

**Decision.** *Accept* stores `final_qty = recommended_qty`. *Override* requires an integer `final_qty >= 0` and a reason; an override below confirmed pre-orders is allowed but returns a warning. The stored row keeps the system's number and the manager's (FR11).

## B2. Ingredient requirements and shortage (S3, K9)

For a date, take each active item's quantity `q`: the stored `final_qty` if a decision exists, otherwise `recommended_qty`. Then:

```
required(j)   = sum over items i of  q_i * recipe_qty(i, j)
usable(j)     = remaining quantity in non-expired batches
short_by(j)   = max(0, required(j) - usable(j))        status = short if short_by > 0
```

Items with `q > 0` and no recipe go to `cannot_compute` (reason `no_recipe`); items with no forecast go there with reason `no_forecast`. They are listed, never silently ignored.

## B3. Ingredient forecast, days of cover, reorder (I7, I9)

Window: today to today + 6. `need(j, d)` is B2 evaluated for date `d` (recommended or accepted quantities).

```
avg_daily_need(j) = sum over d of need(j, d) / 7
days_of_cover(j)  = usable(j) / avg_daily_need(j)        (shown as ">99" when need is 0)
first_shortfall   = first d where sum over d' <= d of need(j, d') > usable(j)
```

Reorder suggestion for ingredient `j`, with `L = supplier lead time` (default setting `default_lead_time_days`, minimum 1, capped at 7):

```
need_L   = sum of need(j, d) for d = today .. today + L - 1
raw      = need_L + min_stock(j) - usable(j) - on_order(j)
if raw <= 0:  no suggestion
else:         suggested = max( ceil(raw / pack) * pack ,  ceil(min_order_qty / pack) * pack )
```

`min_stock` acts as the safety stock. `on_order` is 0 until purchase orders exist (S). Each row returns every term so the manager can see why (I9).

## B4. Alert rules (S4)

`AlertService.evaluate(outlet_id)` recomputes the set of currently true conditions, **opens** any that are missing (one open alert per `dedupe_key`), and **closes** open alerts whose condition is no longer true (`closed_reason = cleared`). It is idempotent. Alert types can be disabled with `alert.<type>.enabled = 0`: nothing new is opened, and existing open alerts are left alone.

| Type | Condition | Severity | `dedupe_key` |
|---|---|---|---|
| `critical_stock` | `usable <= min_stock` (includes out of stock) | critical | `critical_stock:ingredient:<id>` |
| `low_stock` | `min_stock < usable <= reorder_level` | warning | `low_stock:ingredient:<id>` |
| `projected_stockout` | `first_shortfall` exists within `stockout_lookahead_days` | critical if first shortfall is today or tomorrow, else warning | `projected_stockout:ingredient:<id>` |
| `expiry_warning` | batch with `qty_remaining > 0` and `expiry_date <= today + expiry_warning_days` (already expired counts, message asks for a wastage record) | warning; critical if already expired | `expiry_warning:batch:<id>` |
| `waste_risk` | over the last 7 recorded days, `sum(waste) / sum(prepared)` for the item exceeds `waste_risk_threshold_pct` and `sum(prepared) >= 20` | warning | `waste_risk:menu_item:<id>` |
| `forecast_failed` | latest forecast run has status `failed` or `skipped` | critical / warning | `forecast_failed:system` |
| `manual_shortage` (S) | created by the kitchen form; closed by the inventory manager | critical | `manual_shortage:ingredient:<id>` |

A stock change that moves an ingredient from low to critical closes the `low_stock` alert and opens the `critical_stock` one on the next evaluation. **Trigger points:** CLI `alerts`, admin "Run now", and lazily when alerts or dashboards are read and the last evaluation is over 60 seconds old (API.md 3.5). Services below cannot call `AlertService` (ARCH dependency graph), so no service triggers it directly.
