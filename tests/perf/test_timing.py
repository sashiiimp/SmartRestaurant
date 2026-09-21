"""PERF-1, PERF-2 (NFR2): timing against the seeded database. Run: pytest -m perf (needs `flask smartrest demo-reset`)."""
import os
import statistics
import time

import pytest
from dotenv import dotenv_values

from app import create_app
from app.extensions import db
from app.models import ForecastRun, ModelVersion

pytestmark = pytest.mark.perf


@pytest.fixture(scope="module")
def live():
    application = create_app("dev")
    application.config["WTF_CSRF_ENABLED"] = False   # the login POST of the test client carries no token

    @application.before_request
    def _forget_cached_user():   # one app context is kept open, and Flask-Login caches the user on `g`
        from flask import g
        g.pop("_login_user", None)

    with application.app_context():
        if ModelVersion.query.filter_by(status="active").first() is None:
            pytest.skip("database is not seeded with an active model (run flask smartrest demo-reset)")
        yield application


def test_forecast_run_under_five_seconds(live):
    from app.services import forecasting_service as fs
    t = time.perf_counter()
    r = fs.run_forecast(1, trigger="cli")
    elapsed = time.perf_counter() - t
    assert r["status"] == "ok", r
    assert elapsed < 5, f"forecast run took {elapsed:.2f}s"
    print(f"\nPERF-1 forecast run: {elapsed * 1000:.0f} ms for {r['items_forecast']} items x 7 days")


def test_pages_and_read_endpoints_are_fast(live):
    pw = dotenv_values(os.path.join(os.path.dirname(__file__), "..", "..", ".env")).get("SEED_PASSWORD")
    urls = {
        "admin": ["/admin", "/admin/monitor", "/admin/models", "/api/v1/dashboards/admin", "/api/v1/forecasts/accuracy",
                  "/api/v1/reports/sales", "/api/v1/reports/waste", "/api/v1/forecasts"],
        "kitchen": ["/kitchen", "/kitchen/prep", "/api/v1/dashboards/kitchen", "/api/v1/recommendations/prep",
                    "/api/v1/recommendations/requirements", "/api/v1/kitchen/daily-summary"],
        "inventory": ["/inventory", "/api/v1/dashboards/inventory", "/api/v1/recommendations/reorder",
                      "/api/v1/recommendations/ingredient-forecast", "/api/v1/stock/levels", "/api/v1/alerts"],
    }
    worst = 0.0
    for role, paths in urls.items():
        client = live.test_client()
        username = {"admin": "admin", "kitchen": "kitchen1", "inventory": "inventory1"}[role]
        assert client.post("/login", data={"username": username, "password": pw}).status_code == 302
        for path in paths:
            times = []
            for _ in range(10):
                t = time.perf_counter()
                resp = client.get(path)
                times.append(time.perf_counter() - t)
                assert resp.status_code == 200, (path, resp.status_code)
            p95 = sorted(times)[int(len(times) * 0.95) - 1]
            worst = max(worst, max(times))
            assert max(times) < 3, f"{path} took {max(times):.2f}s"
            if path.startswith("/api/"):
                assert p95 < 1, f"{path} p95 {p95:.2f}s"
            print(f"\n{role:9} {path:45} median {statistics.median(times) * 1000:6.0f} ms  max {max(times) * 1000:6.0f} ms")
    print(f"\nPERF-2 worst request: {worst * 1000:.0f} ms")
