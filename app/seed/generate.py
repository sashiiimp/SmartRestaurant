"""Synthetic history generator (ML_PLAN section 2). Every effect below is an assumption of the generator, not a
measurement of a real restaurant. Data is loaded through the same import services as the UI (DATABASE.md 5)."""
import csv
import io
import pathlib
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from app.seed import catalog
from app.services import data_management_service as dm
from app.services import kitchen_service
from app.utils.dates import today

DOW = [0.85, 0.85, 0.90, 0.95, 1.20, 1.30, 1.15]  # Mon..Sun
WET_DAY_PROB = {1: .20, 2: .15, 3: .25, 4: .45, 5: .65, 6: .55, 7: .45, 8: .45, 9: .50, 10: .65, 11: .60, 12: .40}
HOLIDAYS_CSV = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "holidays_lk.csv"


def _weather(rng, days) -> pd.DataFrame:
    rows = []
    for d in days:
        wet = rng.random() < WET_DAY_PROB[d.month]
        rain = float(np.round(rng.gamma(shape=1.2, scale=10.0), 1)) if wet else 0.0  # mean 12 mm on a wet day
        temp = 28.5 + 2.0 * np.sin(2 * np.pi * (d.timetuple().tm_yday - 100) / 365) + rng.normal(0, 0.6)
        rows.append((d.isoformat(), rain, float(np.round(temp, 1))))
    return pd.DataFrame(rows, columns=["date", "rain_mm", "temp_c"])


def _promotions(rng, start: date, end: date, items):
    """About one promotion a month, 5-10 days, 1-2 items; two all-item promotions; one planned in the future."""
    out, d = [], start + timedelta(days=12)
    n = 0
    while d < end - timedelta(days=8):
        length = int(rng.integers(5, 11))
        k = int(rng.integers(1, 3))
        chosen = [int(i) for i in rng.choice([m.id for m in items], size=k, replace=False)]
        out.append({"name": f"Promo {n + 1}", "start_date": d, "end_date": d + timedelta(days=length - 1),
                    "discount_pct": int(rng.choice([10, 15, 20])), "item_ids": chosen, "applies_to_all": False})
        n += 1
        d += timedelta(days=int(rng.integers(24, 36)))
    for i, off in enumerate((200, 480)):
        s = start + timedelta(days=off)
        if s + timedelta(days=6) < end:
            out.append({"name": f"Storewide offer {i + 1}", "start_date": s, "end_date": s + timedelta(days=6),
                        "discount_pct": 10, "item_ids": [], "applies_to_all": True})
    fried = next((m for m in items if m.name == "Fried Chicken 2 pc"), items[0])
    out.append({"name": "Weekend combo (planned)", "start_date": end + timedelta(days=3),
                "end_date": end + timedelta(days=9), "discount_pct": 15, "item_ids": [fried.id],
                "applies_to_all": False})
    return out


def generate(outlet_id: int, start: date = date(2024, 9, 1), end: date | None = None, seed: int = 42,
             out_dir: str = "data/synthetic") -> dict:
    end = end or today() - timedelta(days=1)
    if end <= start + timedelta(days=120):
        raise ValueError("The history must be at least 4 months long.")
    rng = np.random.default_rng(seed)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    items = dm.list_menu_items(outlet_id, active_only=True)
    base = {m[0]: m[5] for m in catalog.MENU}

    # contextual data first, through the import services
    hol_res = dm.import_holidays_csv(outlet_id, HOLIDAYS_CSV.read_text(), dry_run=False, source="curated-approx")
    weather = _weather(rng, days)
    weather.to_csv(out / "weather.csv", index=False)
    dm.import_weather_csv(outlet_id, weather.to_csv(index=False), dry_run=False, source="synthetic")
    promos = _promotions(rng, start, end, items)
    for p in promos:
        dm.create_promotion(outlet_id, p)

    hol = pd.read_csv(HOLIDAYS_CSV, parse_dates=["date"])
    day_index = pd.DatetimeIndex(pd.to_datetime(days))
    is_poya = day_index.isin(hol.loc[hol["type"] == "poya", "date"])
    is_public = day_index.isin(hol.loc[hol["type"] == "public", "date"])
    is_school = day_index.isin(hol.loc[hol["type"] == "school", "date"])
    rain = weather["rain_mm"].to_numpy()
    dow = np.array([DOW[d.weekday()] for d in days])
    month = np.array([1.15 if d.month in (4, 12) else 1.0 for d in days])
    trend = 1.0 + 0.10 * np.arange(len(days)) / len(days)

    sales_rows, expected_rows, prep_rows, waste_rows = [], [], [], []
    for m in items:
        promo = np.ones(len(days))
        for p in promos:
            if p["applies_to_all"] or m.id in p["item_ids"]:
                for i, d in enumerate(days):
                    if p["start_date"] <= d <= p["end_date"]:
                        promo[i] = max(promo[i], 1 + 0.02 * p["discount_pct"])
        drink = m.name in catalog.DRINK_ITEMS
        meat = m.name in catalog.MEAT_ITEMS
        holiday = np.ones(len(days))
        holiday = np.where(is_public, holiday * 1.15, holiday)
        holiday = np.where(is_poya, holiday * (0.65 if meat else (1.0 if drink else 1.10)), holiday)
        if m.name in catalog.SCHOOL_ITEMS:
            holiday = np.where(is_school, holiday * 1.10, holiday)
        rain_eff = 1 - (0.008 if drink else 0.004) * np.minimum(rain, 40)
        expected = base[m.name] * dow * month * holiday * promo * rain_eff * trend
        sold = rng.poisson(expected * rng.lognormal(0.0, 0.10, len(days)))
        over = np.clip(rng.normal(0.15, 0.10, len(days)), -0.05, 0.60)
        prepared = np.maximum(np.round(sold * (1 + over)).astype(int), sold)
        waste = prepared - sold
        for i, d in enumerate(days):
            sales_rows.append((d.isoformat(), m.name, int(sold[i]), float(m.price)))
            expected_rows.append((m.id, d.isoformat(), round(float(expected[i]), 3)))
            prep_rows.append({"menu_item_id": m.id, "prep_date": d, "quantity": int(prepared[i]),
                              "prepared_at": datetime(d.year, d.month, d.day, 9, 0)})
            if waste[i] > 0:
                reason = rng.choice(["overproduction", "quality", "expired"], p=[0.8, 0.1, 0.1])
                waste_rows.append({"menu_item_id": m.id, "waste_date": d, "quantity": int(waste[i]),
                                   "reason": str(reason), "unit_price": m.price})

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "item", "quantity", "unit_price"])
    w.writerows(sales_rows)
    (out / "sales.csv").write_text(buf.getvalue())
    pd.DataFrame(expected_rows, columns=["item_id", "date", "expected_qty"]).to_csv(out / "oracle_expected.csv", index=False)
    sales_res = dm.import_sales_csv(outlet_id, buf.getvalue(), dry_run=False, source="synthetic")
    kitchen_service.bulk_load_history(outlet_id, prep_rows, waste_rows)
    return {"start": start.isoformat(), "end": end.isoformat(), "days": len(days), "items": len(items),
            "sales_rows": sales_res["accepted"], "sales_rejected": sales_res["rejected"], "promotions": len(promos),
            "holidays_loaded": hol_res["accepted"], "prepared_rows": len(prep_rows), "waste_rows": len(waste_rows)}
