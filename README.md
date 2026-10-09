# SmartRestaurant

An ML-based demand forecasting and inventory decision support system for Sri Lankan fast-food restaurants
(CSE5015 project, Team ForeSight). Python 3.14, Flask, MariaDB/MySQL, Pandas, scikit-learn, XGBoost; Vue 3 and
Bootstrap 5 (vendored, no CDN, no build step) inside Jinja2 pages.

**All data in the demo is synthetic** and labelled as such in the UI. No real restaurant data was available; see
`docs/ML_PLAN.md` section 2 and `docs/ML_EVALUATION.md` for what that does and does not prove.

## What it does

Item-level 7-day demand forecast, then a preparation recommendation (with the numbers behind it), ingredient
requirements and shortage detection, reorder suggestions, stock-out / expiry / waste-risk alerts, recording of
actual prepared, served and wasted quantities and stock movements, dashboards for three roles (System
Administrator, Food Production Manager, Inventory & Procurement Manager), and sales / forecast-accuracy / waste
reports with CSV export.

| Doc | Purpose |
|---|---|
| `docs/REQUIREMENTS.md`, `ARCHITECTURE.md`, `DATABASE.md`, `API.md`, `ML_PLAN.md`, `UI_PLAN.md`, `TESTING.md`, `PLAN.md` | The approved planning set |
| `docs/ML_EVALUATION.md` | Actual model results (not planned numbers) |
| `docs/TEST_LOG.md` | Test evidence and UAT results |
| `docs/screenshots/` | Screens captured by `tests/ui/smoke.py` |
| `docs/diagrams/` | UML diagrams (use case, class, sequence, activity), Mermaid sources and images |
| `docs/report/` | Final report draft (`REPORT.md`, `SmartRestaurant_Final_Report_DRAFT.docx`) and its figures |

## Setup

```bash
uv venv --python 3.14 .venv            # or: python3 -m venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt   # or: pip install -r requirements-dev.txt
cp .env.example .env                   # then edit: SECRET_KEY, DATABASE_URL, TEST_DATABASE_URL, SEED_PASSWORD
# database: MySQL 8.4 (production target, see docs/RUNBOOK_MYSQL.md) or the older private MariaDB (scripts/db.sh)
export FLASK_APP=wsgi.py
flask db upgrade                       # create the tables
flask smartrest demo-reset             # seed + synthetic history + train + activate + backfill + forecast + alerts
flask run                              # http://127.0.0.1:5000
```

Log in as `admin`, `kitchen1` or `inventory1` with the `SEED_PASSWORD` from `.env`; an account with its own
`SEED_PASSWORD_<USERNAME>` (e.g. `SEED_PASSWORD_ADMIN`) uses that instead (or the generated password printed by
`flask smartrest seed`). Passwords are never stored in the repository.

`demo-reset` takes about 20 seconds and rebuilds everything from scratch (it refuses to run with `APP_ENV=prod`).
Use `SMARTREST_TODAY=YYYY-MM-DD` to pin "today" for a repeatable demo.

### Commands

```
flask smartrest seed [--reset]          outlet, users, settings, catalog, recipes, suppliers, opening stock
flask smartrest generate-data           synthetic history through the import services
flask smartrest train [--activate]      compare baselines, Random Forest, XGBoost; print the metrics
flask smartrest evaluate [--json F]     cross-validation, feature ablation, segment errors (read-only)
flask smartrest activate <label>        make a trained version active (previous one stays for rollback)
flask smartrest forecast [--as-of D]    7-day forecast;  --from D --to D  = single-day backfill
flask smartrest alerts                  (alerts also refresh lazily when read)
flask smartrest create-user | set-setting <key> <value> | demo-reset
```

## Tests

```bash
pytest -q -m "not mysql"                # fast: unit + service + API tests on SQLite
pytest -q                               # everything, incl. MariaDB constraint and concurrency tests
pytest -q -m perf -s tests/perf         # timing against the seeded database
pytest --cov=app/services --cov=app/ml  # coverage
scripts/devserver.sh start && python tests/ui/smoke.py all --shots docs/screenshots   # browser test (Playwright)
```

## Demo script (about 8 minutes, after `flask smartrest demo-reset`)

1. **Admin** > Models: synthetic-data banner, hold-out comparison of the four candidates, Monitoring > Forecast accuracy.
2. **Kitchen** > Prep plan: forecast, buffer, batch, recommendation. Accept one item, override one with a reason, add a prepared quantity.
3. **Kitchen** > Ingredients: chicken and potato are short today (matches the hand calculation in `docs/TESTING.md`).
4. **Inventory** > Dashboard: the projected stock-out alerts and the reorder suggestion (Reorder page shows every term).
5. **Inventory** > Record stock: stock-in of chicken; the alert clears; the kitchen shortage disappears.
6. **Kitchen** > Served & waste: end-of-day entries (try a negative number for the error handling).
7. As kitchen, open `/admin`: 403.

## Project layout

`app/models` (tables), `app/services` (all business logic), `app/ml` (pure ML, called only by `ForecastingService`),
`app/controllers` (thin Flask blueprints and the JSON API), `app/templates` + `app/static` (views), `app/seed`
(catalog and synthetic data generator), `tests/`, `docs/`. Import rules are enforced by `tests/test_architecture.py`.
