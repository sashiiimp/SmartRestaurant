"""E2E-1: the whole decision chain on controlled data, through the real API and all three roles (14 Oct 2026 release
check). Historical sales -> forecast -> confirmed pre-orders -> prep plan -> BOM requirements -> stock request ->
issue (FEFO) -> inventory wastage -> prepared / served / waste -> reports -> reorder -> purchase order -> receipt.
Every expected number is worked out by hand in the comments, never copied from the code's output (TESTING.md 4).
Today is fixed at Fri 25 Sep 2026 (conftest)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Forecast, ForecastRun, Supplier
from tests.conftest import login
from tests.factories import add_batch, add_recipe, make_ingredient, make_item

TODAY = date(2026, 9, 25)
YESTERDAY = TODAY - timedelta(days=1)
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731


def approx(x, y, places=2):
    return round(float(x), places) == round(float(y), places)


@pytest.fixture()
def world(app, users):
    sup = Supplier(outlet_id=1, name="Ceylon Poultry", lead_time_days=2)
    db.session.add(sup)
    db.session.commit()
    burger = make_item(name="Chicken Burger", price=650, batch_size=6)
    fried = make_item(name="Fried Chicken 2 pc", price=990, batch_size=8)
    milo = make_item(name="Iced Milo", price=350, batch_size=10)          # no recipe on purpose
    chicken = make_ingredient(name="Chicken", unit="kg", min_stock=5, reorder_level=10, pack_size=5, supplier_id=sup.id)
    bun = make_ingredient(name="Burger bun", unit="pcs", min_stock=20, reorder_level=40, pack_size=50, supplier_id=sup.id)
    add_recipe(burger, [(chicken, "0.12"), (bun, 1)])
    add_recipe(fried, [(chicken, "0.30")])
    add_batch(chicken, 12, received=date(2026, 9, 20), expiry=date(2026, 9, 30), batch_no="CHK-A")
    add_batch(chicken, 5, received=date(2026, 9, 15), expiry=YESTERDAY, batch_no="CHK-OLD")   # expired: not usable
    add_batch(bun, 60, received=date(2026, 9, 20), batch_no="BUN-1")
    # One forecast run made today for 6 days (25-30 Sep): 1 Oct is deliberately missing.
    run = ForecastRun(outlet_id=1, as_of_date=TODAY, horizon_days=7, trigger_type="cli", status="ok")
    db.session.add(run)
    db.session.flush()
    for n in range(6):
        for item, qty in ((burger, "47.3"), (fried, "25"), (milo, "20")):
            db.session.add(Forecast(outlet_id=1, run_id=run.id, menu_item_id=item.id, target_date=TODAY + timedelta(days=n),
                                    predicted_qty=Decimal(qty), method="model", input_snapshot={}, is_latest=True))
    # An older run's forecast for 23 Sep, to compare with the sales actually recorded that day.
    old = ForecastRun(outlet_id=1, as_of_date=date(2026, 9, 23), horizon_days=1, trigger_type="cli", status="ok")
    db.session.add(old)
    db.session.flush()
    for item, qty in ((burger, "45"), (fried, "28")):
        db.session.add(Forecast(outlet_id=1, run_id=old.id, menu_item_id=item.id, target_date=date(2026, 9, 23),
                                predicted_qty=Decimal(qty), method="model", input_snapshot={}, is_latest=True))
    db.session.commit()
    clients = {}
    for role in ("admin", "kitchen", "inventory"):
        c = app.test_client()
        assert login(c, users[role].username).status_code == 302
        clients[role] = c
    return dict(burger=burger, fried=fried, milo=milo, chicken=chicken, bun=bun, sup=sup, **clients)


def data(resp, status=None):
    """The response body's data; a write may answer 200 or 201 (the status codes are covered by the API tests)."""
    assert resp.status_code in ((status,) if status else (200, 201)), (resp.status_code, resp.get_json())
    return resp.get_json()["data"]


def test_whole_decision_chain(world):
    w = world
    admin, kitchen, inv = w["admin"], w["kitchen"], w["inventory"]
    burger, fried, milo, chicken, bun = w["burger"], w["fried"], w["milo"], w["chicken"], w["bun"]

    # 1 Historical sales (admin import): check first, nothing saved; then save.
    csv = "date,item,quantity\n2026-09-22,Chicken Burger,40\n2026-09-22,Fried Chicken 2 pc,20\n" \
          "2026-09-23,Chicken Burger,50\n2026-09-23,Fried Chicken 2 pc,30\n"
    check = data(admin.post("/api/v1/sales/import", data={"file": (__import__("io").BytesIO(csv.encode()), "s.csv"), "dry_run": "true"},
                            content_type="multipart/form-data"))
    assert check["accepted"] == 4 and check["dry_run"] is True
    saved = data(admin.post("/api/v1/sales/import", data={"file": (__import__("io").BytesIO(csv.encode()), "s.csv"), "dry_run": "false"},
                            content_type="multipart/form-data"))
    assert saved["accepted"] == 4
    sales = data(admin.get("/api/v1/reports/sales?from=2026-09-22&to=2026-09-23&group_by=day"))
    # 140 portions; revenue 90 x 650 + 50 x 990 = 58,500 + 49,500 = 108,000
    assert sales["totals"]["quantity"] == 140 and approx(sales["totals"]["revenue"], 108000)

    # 2 Forecast accuracy for 23 Sep: burger 45 vs 50, fried 28 vs 30.
    acc = data(admin.get("/api/v1/forecasts/accuracy?from=2026-09-23&to=2026-09-23"))["overall"]
    assert approx(acc["mae"], 3.5)                  # (5 + 2) / 2
    assert approx(acc["wape"], 8.75)                # 7 / 80 x 100
    assert approx(acc["mape"], 8.33)                # (10 % + 6.67 %) / 2
    assert approx(acc["bias"], -3.5)                # (-5 - 2) / 2: under-forecast

    # 3 Seven-day forecast: 6 days present, 1 Oct named as missing, never filled with a made-up number.
    fc = admin.get(f"/api/v1/forecasts?from={D(0)}&to={D(6)}").get_json()
    assert len(fc["data"]) == 18 and fc["meta"]["missing_dates"] == [D(6)]

    # 4 Pre-orders: a confirmed 58 for burgers today counts; a pending 100 for fried does not.
    po = data(kitchen.post("/api/v1/kitchen/pre-orders", json={"menu_item_id": burger.id, "target_date": D(0), "quantity": 58,
                                                               "customer_name": "Office lunch", "pickup_time": "12:30",
                                                               "status": "confirmed"}))
    data(kitchen.post("/api/v1/kitchen/pre-orders", json={"menu_item_id": fried.id, "target_date": D(0), "quantity": 100,
                                                          "customer_name": "Maybe", "pickup_time": "18:00"}))

    # 5 Prep plan. Burger: max(47.3 x 1.1 = 52.03, 58) = 58 -> batch 6 -> 60 (NOT 47.3 + 58: no double count).
    #    Fried: 25 x 1.1 = 27.5 -> batch 8 -> 32 (the pending pre-order is ignored). Milo: 22 -> batch 10 -> 30.
    plan = {r["name"]: r for r in data(kitchen.get(f"/api/v1/recommendations/prep?date={D(0)}"))["items"]}
    assert (plan["Chicken Burger"]["recommended_qty"], plan["Chicken Burger"]["preorder_qty"]) == (60, 58)
    assert approx(plan["Chicken Burger"]["forecast_qty"], 47.3)              # the forecast itself is unchanged
    assert plan["Fried Chicken 2 pc"]["recommended_qty"] == 32 and plan["Fried Chicken 2 pc"]["preorder_qty"] == 0
    assert plan["Iced Milo"]["recommended_qty"] == 30
    data(kitchen.post("/api/v1/recommendations/prep/decisions", json={"menu_item_id": burger.id, "date": D(0), "action": "accept"}))
    bad = kitchen.post("/api/v1/recommendations/prep/decisions", json={"menu_item_id": fried.id, "date": D(0), "action": "override", "final_qty": 40})
    assert bad.status_code == 422                                              # an override needs a reason
    data(kitchen.post("/api/v1/recommendations/prep/decisions", json={"menu_item_id": fried.id, "date": D(0), "action": "override",
                                                                      "final_qty": 40, "reason": "Cricket match tonight"}))

    # 6 BOM requirements for today: chicken 60 x 0.12 + 40 x 0.30 = 7.2 + 12.0 = 19.2 kg against usable 12
    #   (the expired 5 kg is not usable) -> short by 7.2. Buns 60 x 1 = 60 against 60 -> sufficient. Milo has no recipe.
    req = data(kitchen.get(f"/api/v1/recommendations/requirements?date={D(0)}"))
    r = {x["name"]: x for x in req["ingredients"]}
    assert approx(r["Chicken"]["required"], 19.2) and approx(r["Chicken"]["usable_stock"], 12) and approx(r["Chicken"]["short_by"], 7.2)
    assert r["Chicken"]["status"] == "short" and r["Burger bun"]["status"] != "short" and approx(r["Burger bun"]["required"], 60)
    assert [(c["name"], c["reason"]) for c in req["cannot_compute"]] == [("Iced Milo", "no_recipe")]

    # 7 Stock request: kitchen asks for 7.2 kg; inventory approves and issues it, earliest usable expiry first.
    sr = data(kitchen.post("/api/v1/kitchen/stock-requests", json={"note": "for tonight", "lines": [{"ingredient_id": chicken.id, "quantity": 7.2}]}))
    data(inv.post(f"/api/v1/stock-requests/{sr['id']}/approve", json={}))
    data(inv.post(f"/api/v1/stock-requests/{sr['id']}/issue", json={"lines": [{"line_id": sr["lines"][0]["id"], "quantity": 7.2}]}))
    lv = {x["name"]: x for x in data(inv.get("/api/v1/stock/levels"))}
    # usable 12 - 7.2 = 4.8 (below the 5 kg minimum: critical); on hand still includes the expired 5 kg = 9.8
    assert approx(lv["Chicken"]["usable"], 4.8) and approx(lv["Chicken"]["on_hand"], 9.8)
    assert lv["Chicken"]["status"] == "low" and lv["Chicken"]["is_critical"] is True

    # 8 Inventory wastage of the expired batch: on hand drops to the usable 4.8; the batch list no longer shows it.
    old_batch = next(b for b in data(inv.get("/api/v1/stock/batches")) if b["batch_no"] == "CHK-OLD")
    assert old_batch["expired"] is True
    data(inv.post("/api/v1/stock/wastage", json={"ingredient_id": chicken.id, "quantity": 5, "reason": "expired",
                                                 "batch_id": old_batch["id"], "movement_date": D(0)}))
    lv = {x["name"]: x for x in data(inv.get("/api/v1/stock/levels"))}
    assert approx(lv["Chicken"]["on_hand"], 4.8) and approx(lv["Chicken"]["usable"], 4.8)
    assert not [b for b in data(inv.get("/api/v1/stock/batches")) if b["batch_no"] == "CHK-OLD"]

    # 9 Yesterday's kitchen records: prepared 60 / 40, served 50 / 30, waste 6 / 5, staff meals 2 burgers.
    for item, q in ((burger, 60), (fried, 40)):
        data(kitchen.post("/api/v1/kitchen/prepared", json={"menu_item_id": item.id, "date": YESTERDAY.isoformat(), "quantity": q}))
    data(kitchen.post("/api/v1/sales/served", json={"date": YESTERDAY.isoformat(), "lines": [
        {"menu_item_id": burger.id, "quantity": 50}, {"menu_item_id": fried.id, "quantity": 30}]}))
    for item, q in ((burger, 6), (fried, 5)):
        data(kitchen.post("/api/v1/kitchen/waste", json={"menu_item_id": item.id, "date": YESTERDAY.isoformat(), "quantity": q,
                                                         "reason": "overproduction"}))
    data(kitchen.post("/api/v1/kitchen/food-usage", json={"menu_item_id": burger.id, "date": YESTERDAY.isoformat(),
                                                          "usage_type": "staff_meal", "quantity": 2}))
    day = {x["name"]: x for x in data(kitchen.get(f"/api/v1/kitchen/daily-summary?date={YESTERDAY.isoformat()}"))["items"]}
    b, f = day["Chicken Burger"], day["Fried Chicken 2 pc"]
    assert (b["prepared"], b["served"], b["wasted"]) == (60, 50, 6)
    assert (f["prepared"], f["served"], f["wasted"]) == (40, 30, 5)

    # 10 Waste report for yesterday: 11 portions; value 6 x 650 + 5 x 990 = 3,900 + 4,950 = 8,850 LKR.
    waste = data(admin.get(f"/api/v1/reports/waste?from={YESTERDAY.isoformat()}&to={YESTERDAY.isoformat()}&group_by=day"))
    assert waste["food"]["totals"]["quantity"] == 11 and approx(waste["food"]["totals"]["value"], 8850)

    # 11 Admin dashboard, 7 days ending yesterday (18-24 Sep): sales 140 imported + 80 served = 220 portions;
    #    revenue 108,000 + 50 x 650 + 30 x 990 = 108,000 + 32,500 + 29,700 = 170,200; waste rate 11 / 100 = 11.0 %;
    #    forecast for the next 7 days: 6 days x (47.3 + 25 + 20) = 553.8, with 1 Oct missing (null, not zero).
    dash = data(admin.get("/api/v1/dashboards/admin?range=7"))
    assert dash["sales"]["quantity"] == 220 and approx(dash["sales"]["revenue"], 170200)
    assert approx(dash["waste_rate"]["pct"], 11.0) and dash["waste_rate"]["prepared"] == 100
    assert approx(dash["forecast_next7_total"], 553.8)
    assert [f["qty"] is None for f in dash["forecast_next7"]] == [False] * 6 + [True]

    # 12 Ingredient demand, 7 days: chicken day 1 = 19.2 (decided plan); days 2-6 use the recommendation:
    #    burger 52.03 -> 54 x 0.12 = 6.48, fried 27.5 -> 32 x 0.30 = 9.60, together 16.08 per day; day 7 has no forecast.
    #    Total 19.2 + 5 x 16.08 = 99.6 kg. Buns: 60 + 5 x 54 = 330.
    ing = {x["name"]: x for x in data(inv.get(f"/api/v1/recommendations/ingredient-forecast?from={D(0)}&days=7"))["ingredients"]}
    assert [round(v, 2) for v in ing["Chicken"]["daily"]] == [19.2, 16.08, 16.08, 16.08, 16.08, 16.08, 0]
    assert approx(ing["Chicken"]["total_need"], 99.6) and approx(ing["Burger bun"]["total_need"], 330)

    # 13 Reorder: lead time 2 days -> need 19.2 + 16.08 = 35.28; raw = 35.28 + safety 5 - usable 4.8 - on order 0 = 35.48;
    #    pack 5 -> 40 kg. Buns: need 60 + 54 = 114; raw = 114 + 20 - 60 = 74; pack 50 -> 100.
    sugg = {x["name"]: x for x in data(inv.get("/api/v1/recommendations/reorder"))}
    assert approx(sugg["Chicken"]["need_over_lead_time"], 35.28) and approx(sugg["Chicken"]["raw_qty"], 35.48)
    assert approx(sugg["Chicken"]["suggested_qty"], 40) and approx(sugg["Burger bun"]["suggested_qty"], 100)

    # 14 Purchase order for the suggestion; once sent it is "on order" and the chicken suggestion disappears;
    #    receiving adds a batch: usable 4.8 + 40 = 44.8, status ok.
    order = data(inv.post("/api/v1/purchase-orders", json={"supplier_id": w["sup"].id, "lines": [{"ingredient_id": chicken.id, "qty_ordered": 40}]}))
    data(inv.post(f"/api/v1/purchase-orders/{order['id']}/send", json={}))
    assert "Chicken" not in {x["name"] for x in data(inv.get("/api/v1/recommendations/reorder"))}
    line = data(inv.get(f"/api/v1/purchase-orders/{order['id']}"))["lines"][0]
    data(inv.post(f"/api/v1/purchase-orders/{order['id']}/receive", json={"lines": [{"line_id": line["id"], "quantity": 40, "expiry_date": D(6)}]}))
    lv = {x["name"]: x for x in data(inv.get("/api/v1/stock/levels"))}
    assert approx(lv["Chicken"]["usable"], 44.8) and lv["Chicken"]["status"] == "ok"
    assert data(inv.get("/api/v1/stock/consistency"))["consistent"] is True

    # 15 Movement report shows the whole story for chicken today: issue -7.2, wastage -5, receipt +40.
    mv = data(admin.get(f"/api/v1/reports/movements?from={D(0)}&to={D(0)}&ingredient_id={chicken.id}"))
    assert sorted(round(m["quantity"], 1) for m in mv) == [-7.2, -5.0, 40.0]

    # 16 The pre-order stays linked to planning: completing it changes nothing in the plan and records no sale.
    data(kitchen.patch(f"/api/v1/kitchen/pre-orders/{po['id']}", json={"status": "completed"}))
    plan = {r["name"]: r for r in data(kitchen.get(f"/api/v1/recommendations/prep?date={D(0)}"))["items"]}
    assert plan["Chicken Burger"]["preorder_qty"] == 58 and plan["Chicken Burger"]["final_qty"] == 60
    assert data(admin.get(f"/api/v1/reports/sales?from={D(0)}&to={D(0)}&group_by=day"))["totals"]["quantity"] == 0
