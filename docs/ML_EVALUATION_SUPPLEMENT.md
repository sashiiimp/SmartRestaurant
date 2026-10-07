# SmartRestaurant: supplementary evaluation (7 Oct 2026)

**Status: supplementary, not yet in the report.** These analyses were added after the 7 Oct 2026 review to answer
questions the main evaluation (`ML_EVALUATION.md`) leaves open. They change nothing in the shipped model, the stored
results or the report; the team decides whether and how to use them. Everything was produced by
`scripts/research_supplement.py` (read-only: it queries the demo database and generates the other seeds in throwaway
in-memory databases). Re-run with:

```
cd /srv/smartrest && runuser -u smartrest -- .venv/bin/python scripts/research_supplement.py --json instance/supplement.json
```

**Read this first.** All data is synthetic (as in `ML_EVALUATION.md`). The results show what the pipeline and the
decision rules do on data with known structure, not what they would achieve in a real restaurant.

## 1. Waste and stock-outs: what the forecast changes in the kitchen

The main evaluation measures forecast error only. This section turns forecasts into preparation quantities with the
production formula (`recommendation_service.compute_recommended`: forecast x (1 + buffer), rounded up to the batch
size) and scores them against actual demand over the active model's hold-out, 9 Aug to 3 Oct 2026 (56 days x 10 items
= 560 item-days, model `v20261004-1`). Food is prepared for the day, so anything not sold is waste and any demand
above the quantity prepared is unmet. The model forecasts are the stored 1-day backfill forecasts of the model copy
fitted before the hold-out (out-of-sample, the same figures as the accuracy view).

| Policy | Buffer | Prepared | Waste % of prepared | Waste at menu price (LKR) | Unmet demand % | Item-days short % | Fill rate % |
|---|---|---|---|---|---|---|---|
| Synthetic history (preparation records) | - | 41,029 | 13.53 | 3,598,210 | 0.00 | 0.0 | 100.00 |
| Naive: same weekday last week | 0% | 37,526 | 13.39 | 3,235,520 | 8.39 | 42.1 | 91.61 |
| | 5% | 39,436 | 15.91 | 4,036,720 | 6.54 | 33.4 | 93.46 |
| | 10% | 41,376 | 18.65 | 4,922,710 | 5.12 | 26.8 | 94.88 |
| | 15% | 43,082 | 21.07 | 5,793,270 | 4.16 | 22.9 | 95.84 |
| | 20% | 44,676 | 23.22 | 6,638,710 | 3.32 | 19.3 | 96.68 |
| | 30% | 48,540 | 28.37 | 8,800,980 | 2.00 | 12.0 | 98.00 |
| Mean of last 4 same weekdays | 0% | 37,782 | 11.63 | 2,816,060 | 5.89 | 35.5 | 94.11 |
| | 5% | 39,732 | 14.41 | 3,642,860 | 4.15 | 28.0 | 95.85 |
| | 10% | 41,540 | 17.22 | 4,572,420 | 3.08 | 21.8 | 96.92 |
| | 15% | 43,310 | 19.85 | 5,467,080 | 2.16 | 15.5 | 97.84 |
| | 20% | 45,126 | 22.63 | 6,465,360 | 1.60 | 12.0 | 98.40 |
| | 30% | 48,690 | 27.69 | 8,551,340 | 0.76 | 7.1 | 99.24 |
| **Model (XGBoost)** | 0% | 37,220 | 9.83 | 2,267,890 | 5.41 | 36.2 | 94.59 |
| | 5% | 38,860 | 12.16 | 2,912,790 | 3.79 | 29.8 | 96.21 |
| | **10% (shipped)** | 40,792 | **15.18** | 3,840,580 | **2.48** | 21.2 | **97.52** |
| | 15% | 42,372 | 17.81 | 4,685,100 | 1.84 | 16.1 | 98.16 |
| | 20% | 44,128 | 20.53 | 5,646,490 | 1.16 | 10.7 | 98.84 |
| | 30% | 47,744 | 25.99 | 7,773,240 | 0.41 | 5.4 | 99.59 |

What this shows, on synthetic data:

1. **At every buffer the model wastes less and leaves less demand unmet than both baselines**: a better forecast
   moves the whole waste/stock-out trade-off, not just one point on it.
2. **At a comparable service level the model needs a smaller buffer.** The naive rule needs +20% to fill 96.7% of
   demand and then wastes 23.2% of what is prepared (LKR 6.64 million at menu price); the model with the shipped
   +10% fills 97.5% and wastes 15.2% (LKR 3.84 million), about 42% less waste value with fewer shortages.
3. **The synthetic history is not a fair comparison.** The generator prepares at least what was sold on every day
   (`app/seed/generate.py`), so the history has no stock-outs by construction; in a real kitchen it would. The model at
   +5% wastes less than the history (12.2% against 13.5%) but leaves 3.8% of demand unmet. Whether that is better
   depends on the cost of a lost sale against the cost of waste, which the data cannot tell.
4. **The buffer is the lever between waste and stock-outs.** A buffer derived from the forecast error (a quantile of
   the hold-out residuals, the newsvendor rule) would choose this point from the costs instead of a fixed 10%; this
   remains future work (`ML_EVALUATION.md` section 6, limitation 4).

Limitations: demand is uncensored (synthetic sales equal demand); no pre-orders in the history; waste is valued at
menu price, not food cost; one outlet, one seed (section 4 checks the forecast across seeds, not the policies).

## 2. Error by forecast horizon

Forecasts made at each day of the hold-out with only the sales before it (as in production, with the seasonal weather
estimate), 1 to 14 days ahead, model copy fitted before the hold-out; 43 origins x 10 items per horizon.

| Days ahead | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MAE | 9.42 | 9.39 | 9.29 | 9.32 | 9.31 | 9.37 | 9.25 | 9.43 | 9.34 | 9.35 | 9.29 | 9.46 | 9.40 | 9.31 |
| Rows with imputed lags | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |

Up to 7 days ahead every lag is a known sale (the features start at lag 7 by design, `ML_PLAN.md` section 3), so the
error does not depend on the horizon. From day 8 the most recent lags are imputed from the older weekly lags; on this
data that costs nothing measurable, because the synthetic demand has a stable weekly pattern. Real demand with level
shifts would likely degrade from day 8, which supports the default 7-day horizon.

## 3. Are the differences significant? (Diebold-Mariano)

Loss = absolute error, averaged over the items per day; the test is on the daily differences (A minus B, negative =
A better), with a Newey-West variance and the Harvey-Leybourne-Newbold small-sample correction; two-sided p-values.

| Comparison | Days | Mean daily difference (portions) | DM | p |
|---|---|---|---|---|
| Model vs naive, hold-out (backfill forecasts) | 56 | -4.69 | -9.12 | 1.4e-12 |
| Model vs mean of 4 weeks, hold-out | 56 | -1.65 | -4.43 | 4.6e-5 |

The pooled cross-validation days (6 windows x 28 days = 168 days) for each seed are in section 4: learned models
against the naive rule have p below 1e-20 in every seed.

## 4. Robustness across synthetic-data seeds

The demo history (1 Sep 2024 to 3 Oct 2026) was generated again with four other seeds, each in its own in-memory
database, and run through the same training, 6 x 28-day cross-validation and ablation as `flask smartrest evaluate`.
Seed 42 reproduces the published figures exactly (hold-out MAE 9.20, CV MAE 9.45), which also checks that the run is
deterministic.

| Seed | Hold-out winner | Hold-out MAE: naive / mean-4 / RF / XGB | CV MAE: naive / mean-4 / RF / XGB | CV windows won by XGB | Noise floor (CV) |
|---|---|---|---|---|---|
| 42 | XGBoost | 13.88 / 10.85 / 9.66 / 9.20 | 13.86 / 11.04 / 9.63 / 9.45 | 3 of 6 | 8.32 |
| 7 | XGBoost | 13.24 / 10.94 / 9.45 / 9.25 | 13.11 / 10.89 / 9.30 / 8.84 | 5 of 6 | 7.82 |
| 123 | Random Forest | 13.54 / 10.93 / 9.00 / 9.15 | 12.90 / 10.44 / 8.95 / 8.84 | 4 of 6 | 7.92 |
| 2024 | XGBoost | 12.67 / 9.74 / 8.55 / 8.49 | 12.38 / 9.72 / 8.67 / 8.51 | 5 of 6 | 7.48 |
| 31337 | XGBoost | 12.82 / 10.35 / 8.84 / 8.66 | 12.97 / 10.65 / 9.01 / 8.74 | 6 of 6 | 8.06 |
| **Mean ± sd** | | 13.23 / 10.56 / 9.10 / 8.95 (± 0.50 / 0.52 / 0.45 / 0.35) | 13.05 / 10.55 / 9.11 / 8.88 (± 0.53 / 0.52 / 0.36 / 0.35) | 23 of 30 | |

Feature ablation (XGBoost, CV windows improved by adding the group, and the change in CV MAE):

| Seed | + holidays | + promotions | + weather |
|---|---|---|---|
| 42 | 4 of 6, -0.25 | 6 of 6, -0.63 | 3 of 6, +0.09 |
| 7 | 5 of 6, -0.51 | 5 of 6, -0.26 | 4 of 6, -0.07 |
| 123 | 6 of 6, -0.38 | 5 of 6, -0.16 | 3 of 6, -0.01 |
| 2024 | 5 of 6, -0.35 | 5 of 6, -0.16 | 1 of 6, +0.11 |
| 31337 | 6 of 6, -0.34 | 6 of 6, -0.45 | 3 of 6, +0.01 |

Diebold-Mariano on the 168 pooled CV days:

| Seed | XGB vs RF: difference, p | XGB vs naive: difference, p | RF vs naive: difference, p |
|---|---|---|---|
| 42 | -0.18, 0.085 | -4.41, 2.2e-24 | -4.24, 1.9e-23 |
| 7 | -0.46, 0.0046 | -4.27, 6e-31 | -3.81, 2e-21 |
| 123 | -0.11, 0.24 | -4.05, 3.3e-27 | -3.94, 3.3e-31 |
| 2024 | -0.16, 0.077 | -3.87, 1.6e-36 | -3.71, 5.6e-34 |
| 31337 | -0.27, 0.0032 | -4.23, 2.7e-31 | -3.97, 3.3e-28 |

What holds across seeds:

1. **Learned models beat both baselines in all 30 windows of all five seeds**, cutting the naive error by 31 to 33%
   (CV), with p below 1e-20 every time. This main result does not depend on the seed.
2. **XGBoost is ahead of Random Forest on average** (CV MAE 8.88 against 9.11, 23 of 30 windows), **but the gap is small
   and significant at 5% in only two of five seeds**; on one seed Random Forest wins the hold-out. "XGBoost and
   Random Forest perform similarly, XGBoost slightly better on average" is supported; "XGBoost is clearly better" is not.
3. **Holidays help in every seed** (4 to 6 of 6 windows) and **promotions in every seed** (5 or 6 of 6). The size of
   the promotion gain varies with how many promotions fall in the test windows.
4. **Weather does not help reliably** (1 to 4 of 6 windows, mean change +0.03), consistent with `ML_EVALUATION.md`
   section 5: at forecast time only the seasonal average is known.
5. XGBoost stays 0.7 to 1.1 portions above the noise floor (CV); the floor itself differs by seed (7.5 to 8.3).

## 5. What this does not change

The shipped model, its stored metrics, `ML_EVALUATION.md` and the report are unchanged. Open points for the team:
whether to cite sections 1 to 4 in the report (they strengthen the evaluation of objective O3 and the decision layer),
and whether to replace the fixed 10% buffer by a buffer derived from the forecast error (section 1, point 4).
