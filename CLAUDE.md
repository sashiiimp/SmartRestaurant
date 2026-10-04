# CLAUDE.md: SmartRestaurant

ML-based demand forecasting and inventory decision support for Sri Lankan fast-food restaurants (CSE5015 project, Team ForeSight). Flask + MySQL/MariaDB + Pandas/scikit-learn/XGBoost, with Vue 3 (CDN, no build step) inside Jinja2 pages. **Hard deadline: 28 Sep 2026. One builder. MVP first.**

## Read first, in this order

1. `docs/PLAN.md`: what is in scope now (tiers M1/M2/S/X), the schedule, the trim ladder. **This decides what to build.**
2. `docs/REQUIREMENTS.md`: stories (C, A, K, I, S ids) and acceptance criteria.
3. `docs/ARCHITECTURE.md`: MVC layers, import rules, service graph, request flows.
4. `docs/DATABASE.md`, `docs/API.md`, `docs/ML_PLAN.md`, `docs/UI_PLAN.md`, `docs/TESTING.md`.
5. `docs/proposal.pdf` is the source of truth for FR1-FR12 and NFR1-NFR8.

If asked to build something outside M1/M2 of `PLAN.md`, say so and ask before doing it. If code must differ from a document, change the document in the same commit.

## Status

**M1, M2 and all 15 remaining proposal functions (`docs/PLAN.md` section 3A: suppliers, adjustments, purchase orders, availability, pre-orders, stock requests, shortage reports, data check, admin inventory and forecast monitoring, reports, restaurant information, daily orders, ingredient usage, analytics) are implemented, tested and deployed to the demo database (21 Sep 2026)**; see `docs/PLAN.md` and `docs/TEST_LOG.md`. **4 Oct 2026:** cross-validation and feature ablation added (`flask smartrest evaluate`, `docs/ML_EVALUATION.md` sections 4 to 6) and the holiday calendar corrected to the declared dates (section 7). After the security and QA audit, upper limits, bounded ranges and type checks were added to the validation (`docs/API.md` section 1, `docs/TEST_LOG.md` section 13), and sessions, headers, CSV export, uploads, passwords and the lockout were hardened (section 14; migration `4c1e5e7a9b2d`, not yet applied to the demo database). Remaining work is report/demo preparation. Keep the fast tests green (`pytest -q -m "not mysql"`) and re-run `python tests/ui/smoke.py all` after UI changes (against a copy of the database, never the demo data).

## Commands (available once the slices are built)

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
```

Environment: `SECRET_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, `APP_ENV` (`dev`/`test`/`prod`), `SEED_PASSWORD`, `SMARTREST_TODAY` (optional fixed date for tests and demos). All read through `app/config.py`.

## Architecture rules (enforced by `tests/test_architecture.py`)

- **Controllers** (`app/controllers`): parse the request, check the role, call **one** service method, choose the response, map exceptions to status codes. No queries, no calculations, no ML, **no `db.session.commit()`**. Import only `services`, `utils`, `flask`.
- **Services** (`app/services`): all business logic, validation and transactions. Take `outlet_id` explicitly. Never import `flask.request`, `session` or controllers. Call only services lower in the dependency graph (`ARCHITECTURE.md` section 3). Raise `ValidationError`, `NotFoundError` or `ConflictError` (`services/errors.py`).
- **ML** (`app/ml`): pure Python on DataFrames; no Flask, no DB, no models. Called **only** by `ForecastingService`.
- **Models** (`app/models`): tables only, no logic. **Templates**: display only.
- Every role blueprint uses `before_request` with `roles_required(...)`; every API route has an explicit `@roles_required`. The route x role test (`tests/api/test_rbac.py`) must stay green.

## Conventions

- Python: type hints on service signatures, small functions, no clever abstractions. Match the surrounding code's style and comment density; comments explain *why*.
- **Money and stock quantities are `Decimal`**, never float. Portions are `int`. Forecast values are `Decimal(10,2)`.
- **Dates:** business dates are `date` in Asia/Colombo, obtained through `utils.dates.today()` (honours `SMARTREST_TODAY`); never call `date.today()` directly. Timestamps are UTC.
- **API:** envelope `{"data", "meta"}` / `{"error": {"code","message","fields"}}`; status codes as in `docs/API.md`. Add the endpoint to `API.md` first if it is new.
- **Validation** lives in services; the DB constraints are the backstop, not the only check. Forms and JS hints are convenience only.
- **Stock** is derived from batches and immutable movements; never write a running total. Stock-outs are FEFO over usable (non-expired) batches with row locks.
- **Forecasts** are never overwritten: insert new rows and flip `is_latest`. A forecast never contains a number that was not produced by a model or a labelled baseline (S5).
- **Frontend:** Vue 3 global build with **`delimiters: ['[[', ']]']` on every app** (Jinja uses `{{ }}`). Never use `|safe`; pass data with `{{ data|tojson }}`. Vue, Bootstrap and Chart.js are vendored in `app/static/vendor/`; no CDN links. Page skeleton and components are in `docs/UI_PLAN.md`.
- **Synthetic data** is labelled as such in the UI, reports and docs. Never present its accuracy as real-world accuracy.
- **Security:** no secrets in git, hashed passwords, CSRF on all writes, escaped output, parameterised queries only, generic login errors.
- Dependencies: keep to Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF, PyMySQL, pandas, numpy, scikit-learn, xgboost, joblib, pytest. Ask before adding anything else.

## Workflow

- Work in the slices and order in `PLAN.md`. Per feature: service and its tests, then API, then page. Do not skip the tests for formulas (`TESTING.md` section 4 has hand-calculated expected values; never copy expected values from the code's output).
- One commit per work package with a clear message. `git init` happens at plan approval. Never commit `.env`, `instance/`, `data/synthetic/`, backups or passwords.
- Do not over-engineer: no background workers, no SPA build, no new services, no abstractions for hypothetical needs. If something is not in `PLAN.md` M1 or M2, it does not get built by default.
- After finishing a work package, update the status line in this file and the hours in `PLAN.md`.
- Before saying "done": run the fast tests and, for UI work, open the page at 360 px and 1280 px.

## Definition of done (story)

Service tested, API matches `API.md`, page matches `UI_PLAN.md`, RBAC and architecture tests green, no business logic in controllers, docs updated if behaviour changed.

## Known environment facts

- The project runs on **Python 3.14** (pinned wheels for pandas, scikit-learn, xgboost-cpu install fine; `requirements.txt` has the tested versions).
- The database is a **private MariaDB 11.8 instance** on port 3307 (`scripts/db.sh start`); the machine also runs an unrelated MariaDB/aaPanel server that this project must not touch. Use portable SQLAlchemy types only. Unit tests use SQLite; concurrency and constraint tests use MariaDB.
- `pkill -f` patterns can kill the shell that issues them; use `scripts/devserver.sh start|stop` for the dev server.
