# SmartRestaurant

An ML-based demand forecasting and inventory decision support system for Sri Lankan fast-food restaurants
(CSE5015 project, Team ForeSight). Python 3.14, Flask, MySQL 8.4, Pandas, scikit-learn, XGBoost; Vue 3 and
Bootstrap 5 (vendored, no CDN, no build step) inside Jinja2 pages.

**All data in the demo is synthetic** and labelled as such in the UI. No real restaurant data was available; see
`docs/ML_PLAN.md` section 2 and `docs/ML_EVALUATION.md` for what that does and does not prove.

## What it does

Three roles, each with its own dashboard and pages:

| Role | Main functions |
|---|---|
| **Admin** (System Administrator) | Restaurant overview, sales / forecast-accuracy / waste / inventory reports with CSV export, historical data import, ML model training, comparison and activation, forecast generation, menu items and recipes (BOM), ingredients, users and settings |
| **Kitchen** (Food Production Manager) | 7-day item forecast, preparation plan with the recommendation and its calculation, recording prepared portions, served and wasted quantities, ingredient requirements and shortages, stock requests, customer pre-orders |
| **Inventory** (Inventory & Procurement Manager) | Stock levels and expiry (FEFO batches), stock in / issue / wastage, kitchen requests (approve, issue), reorder suggestions, purchase orders and receiving, suppliers |

Alerts (stock-out, projected shortfall, expiry, waste risk) are shown to the roles that act on them.

## Repository layout

| Path | Contents |
|---|---|
| `app/models` | SQLAlchemy models (the MySQL tables) |
| `app/services` | All business logic: forecasting, recommendations, kitchen, inventory, alerts, reports |
| `app/ml` | Feature building, training, evaluation (called only by the forecasting service) |
| `app/controllers` | Thin Flask blueprints: HTML pages and the JSON API (`/api/v1`) |
| `app/templates`, `app/static` | Jinja2 pages, CSS, Vue page scripts; `static/vendor` holds the pinned third-party libraries |
| `app/seed` | Demo catalogue and the synthetic history generator |
| `migrations/` | Alembic (Flask-Migrate) schema migrations for MySQL 8.4 |
| `tests/` | Unit, service, API, integration and browser smoke tests |
| `docs/` | Requirements, architecture, database, API, ML plan and evaluation, testing, UML diagrams |
| `deploy/` | Example MySQL, systemd and nginx configuration |
| `scripts/` | Dev server, front-end library download, holiday data builder, function inventory used by the tests |
| `data/holidays_lk.csv` | Sri Lankan public holidays used as a forecasting feature (built by `scripts/make_holidays.py`) |

Import rules between the layers are enforced by `tests/test_architecture.py`.

## Documentation

| File | Purpose |
|---|---|
| `docs/REQUIREMENTS.md` | Functional and non-functional requirements, user stories |
| `docs/ARCHITECTURE.md` | Layers, services, security, design decisions |
| `docs/DATABASE.md` | Tables, constraints and the ER diagram |
| `docs/API.md` | The JSON API used by the pages |
| `docs/ML_PLAN.md` | Forecasting design: data, features, models, recommendation formulas |
| `docs/ML_EVALUATION.md` | Actual model results on the hold-out period |
| `docs/TESTING.md` | Test strategy and the hand-calculated test cases |
| `docs/diagrams/` | UML diagrams (use case, class, sequence, activity), Mermaid sources and images |

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env        # then set SECRET_KEY, DATABASE_URL, TEST_DATABASE_URL, SEED_PASSWORD
export FLASK_APP=wsgi.py
flask smartrest db-info     # read-only: which database this configuration uses (MySQL 8.4 is required)
flask db upgrade            # create the tables
flask smartrest demo-reset  # seed, synthetic history, train and activate a model, backfill, forecast, alerts
flask run                   # http://127.0.0.1:5000
```

Log in as `admin`, `kitchen1` or `inventory1` with the `SEED_PASSWORD` from `.env` (or `SEED_PASSWORD_<USERNAME>`
for one account). No password is stored in the repository. `demo-reset` rebuilds everything from scratch and refuses
to run with `APP_ENV=prod`. `SMARTREST_TODAY=YYYY-MM-DD` pins "today" for a repeatable demo.

Other commands (`flask smartrest ...`): `seed`, `generate-data`, `train [--activate]`, `evaluate`, `activate <label>`,
`forecast [--as-of D]`, `forecast-daily`, `check-stock`, `create-user`, `set-setting <key> <value>`.

## Tests

```bash
pytest -q -m "not mysql"                 # unit, service and API tests on SQLite in memory
TEST_ALL_ON_DATABASE=1 pytest -q         # the whole suite against MySQL 8.4 (TEST_DATABASE_URL)
scripts/devserver.sh start && python tests/ui/smoke.py all   # browser smoke test (Playwright, port 5055)
```

## Third-party components

Bootstrap 5.3.3, Vue 3.5.13 and Chart.js 4.4.7 (MIT licence) are vendored in `app/static/vendor`
(`VERSIONS.txt`); the Inter font is under the SIL Open Font License 1.1 (`app/static/vendor/fonts/INTER-LICENSE.txt`).
Python dependencies are listed in `requirements.txt`.
