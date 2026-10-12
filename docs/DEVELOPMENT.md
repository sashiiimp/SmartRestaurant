# SmartRestaurant: developer guide

ML-based demand forecasting and inventory decision support for Sri Lankan fast-food restaurants (CSE5015 project, Team ForeSight). Flask + MySQL 8.4 + pandas/scikit-learn/XGBoost, with Vue 3 (vendored, no build step) inside Jinja2 pages.

## Read first, in this order

1. `docs/PLAN.md`: scope (tiers M1/M2/S/X), the schedule and the trim ladder.
2. `docs/REQUIREMENTS.md`: stories (C, A, K, I, S ids) and acceptance criteria.
3. `docs/ARCHITECTURE.md`: MVC layers, import rules, service graph, request flows.
4. `docs/DATABASE.md`, `docs/API.md`, `docs/ML_PLAN.md`, `docs/UI_PLAN.md`, `docs/TESTING.md`.
5. `docs/proposal.pdf` is the source of truth for FR1-FR12 and NFR1-NFR8.

Scope is decided by `PLAN.md`. If code must differ from a document, change the document in the same commit. The history of what was built, tested and deployed, with dates, is in `docs/TEST_LOG.md`.

## Commands

```
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env                 # then fill values; never commit .env
flask db upgrade
flask smartrest seed [--reset]       # outlet, users, settings, catalog, suppliers, opening stock
flask smartrest generate-data        # synthetic history, loaded through the import services
flask smartrest train --activate     # trains baselines, RF, XGBoost; prints the comparison
flask smartrest evaluate [--json F]  # cross-validation + feature ablation (read-only)
flask smartrest forecast [--as-of D] [--from D --to D]   # --from/--to = backfill
flask smartrest check-stock          # data check: stock vs movement history (exit 1 if inconsistent)
flask smartrest create-user | set-setting <key> <value> | demo-reset
flask run                            # dev server
pytest -q -m "not mysql"             # fast tests
pytest -q                            # all tests (needs the smartrest_test database)
pytest -q -m perf                    # timing tests (skipped unless -m perf; they write to the dev database)
python tests/ui/smoke.py all --base URL   # browser walkthrough; run against a copy of the database, never the demo data
```

Environment: `SECRET_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, `APP_ENV` (`dev`/`test`/`prod`), `SEED_PASSWORD` (and optional `SEED_PASSWORD_<USERNAME>`, e.g. `SEED_PASSWORD_ADMIN`), `SMARTREST_TODAY` (optional fixed date for tests and demos). All read through `app/config.py`.

## Architecture rules (enforced by `tests/test_architecture.py`)

- **Controllers** (`app/controllers`): parse the request, check the role, call **one** service method, choose the response, map exceptions to status codes. No queries, no calculations, no ML, **no `db.session.commit()`**. Import only `services`, `utils`, `flask`.
- **Services** (`app/services`): all business logic, validation and transactions. Take `outlet_id` explicitly. Never import `flask.request`, `session` or controllers. Call only services lower in the dependency graph (`ARCHITECTURE.md` section 3). Raise `ValidationError`, `NotFoundError` or `ConflictError` (`services/errors.py`).
- **ML** (`app/ml`): pure Python on DataFrames; no Flask, no DB, no models. Called **only** by `ForecastingService`.
- **Models** (`app/models`): tables only, no logic. **Templates**: display only.
- Every role blueprint uses `before_request` with `roles_required(...)`; every API route has an explicit `@roles_required`. The route x role test (`tests/api/test_rbac.py`) must stay green.

## Conventions

- Python: type hints on service signatures, small functions, no clever abstractions. Comments explain *why*.
- **Money and stock quantities are `Decimal`**, never float. Portions are `int`. Forecast values are `Decimal(10,2)`.
- **Dates:** business dates are `date` in Asia/Colombo, obtained through `utils.dates.today()` (honours `SMARTREST_TODAY`); never call `date.today()` directly. Timestamps are UTC.
- **API:** envelope `{"data", "meta"}` / `{"error": {"code","message","fields"}}`; status codes as in `docs/API.md`. Add the endpoint to `API.md` first if it is new.
- **Validation** lives in services; the DB constraints are the backstop, not the only check. Forms and JS hints are convenience only.
- **Stock** is derived from batches and immutable movements; never write a running total. Stock-outs are FEFO over usable (non-expired) batches with row locks.
- **Forecasts** are never overwritten: insert new rows and flip `is_latest`. A forecast never contains a number that was not produced by a model or a labelled baseline (S5).
- **Frontend:** Vue 3 global build with **`delimiters: ['[[', ']]']` on every app** (Jinja uses `{{ }}`). Never use `|safe`; pass data with `{{ data|tojson }}`. Vue, Bootstrap and Chart.js are vendored in `app/static/vendor/`; no CDN links. Page skeleton and components are in `docs/UI_PLAN.md`.
- **Synthetic data** is labelled as such in the UI, reports and docs. Never present its accuracy as real-world accuracy.
- **Security:** no secrets in git, hashed passwords, CSRF on all writes, escaped output, parameterised queries only, generic login errors.
- Dependencies: Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF, PyMySQL, pandas, numpy, scikit-learn, xgboost, joblib, pytest. New dependencies need team agreement.

## Workflow

- Per feature: service and its tests, then API, then page. Formula tests use the hand-calculated expected values in `TESTING.md` section 4; never copy expected values from the code's output.
- One commit per work package with a clear message. Never commit `.env`, `instance/`, `data/synthetic/`, backups or passwords.
- Keep it simple: no background workers, no SPA build, no abstractions for hypothetical needs.
- Before calling a change done: run the fast tests and, for UI work, open the page at 360 px and 1280 px.

## Definition of done (story)

Service tested, API matches `API.md`, page matches `UI_PLAN.md`, RBAC and architecture tests green, no business logic in controllers, docs updated if behaviour changed.

## Environment notes

- The project runs on **Python 3.14**; `requirements.txt` has the tested versions.
- **Database:** MySQL 8.4 in production (`docs/RUNBOOK_MYSQL.md`); unit tests use SQLite, and concurrency and constraint tests run on MySQL (`pytest -m mysql` with `TEST_DATABASE_URL`). Use portable SQLAlchemy types only.
- **Deployment:** the demo is served at `https://smartrest.developerstudio.space` by nginx (`deploy/nginx/`) in front of gunicorn, which runs as an unprivileged user under systemd (`deploy/systemd/`) with `APP_ENV=prod`. Run `flask` commands on the server as that user.
