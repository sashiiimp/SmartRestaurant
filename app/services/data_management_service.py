"""Menu, recipes, sales import, contextual data (Data Management service, ARCH section 3)."""
import csv
import io
from datetime import timedelta

import pandas as pd

from app.extensions import db
from app.models import Holiday, Ingredient, MenuItem, Promotion, PromotionItem, RecipeLine, SalesRecord, WeatherDaily
from app.models.context import HOLIDAY_TYPES
from app.services import audit
from app.services.errors import NotFoundError, ValidationError
from app.services.validation import Fields
from app.utils.dates import today


# ---- menu (A4) -------------------------------------------------------------------------------
def list_menu_items(outlet_id: int, active_only: bool = False) -> list[MenuItem]:
    q = MenuItem.query.filter_by(outlet_id=outlet_id)
    if active_only:
        q = q.filter_by(is_active=True)
    return q.order_by(MenuItem.id).all()


def get_menu_item(outlet_id: int, item_id: int) -> MenuItem:
    item = MenuItem.query.filter_by(id=item_id, outlet_id=outlet_id).first()
    if not item:
        raise NotFoundError("Menu item not found.")
    return item


def _menu_fields(data: dict, partial: bool = False) -> dict:
    f = Fields(data)
    f.text("name", required=not partial, max_len=120)
    f.text("category", required=False, max_len=60)
    f.decimal("price", required=not partial, min=0)
    f.text("portion_unit", required=False, max_len=30, default="portion")
    f.integer("shelf_life_hours", required=False, min=0)
    f.integer("batch_size", required=False, min=1, default=1)
    return f.check()


def create_menu_item(outlet_id: int, data: dict, actor_id: int | None = None) -> MenuItem:
    v = _menu_fields(data)
    if MenuItem.query.filter_by(outlet_id=outlet_id, name=v["name"]).first():
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    item = MenuItem(outlet_id=outlet_id, **v)
    db.session.add(item)
    db.session.flush()
    audit.record(outlet_id, actor_id, "menu.create", "menu_item", item.id)
    db.session.commit()
    return item


def update_menu_item(outlet_id: int, item_id: int, data: dict, actor_id: int | None = None) -> MenuItem:
    item = get_menu_item(outlet_id, item_id)
    merged = {"name": item.name, "category": item.category, "price": item.price,
              "portion_unit": item.portion_unit, "shelf_life_hours": item.shelf_life_hours,
              "batch_size": item.batch_size, **{k: v for k, v in data.items() if k in
              ("name", "category", "price", "portion_unit", "shelf_life_hours", "batch_size")}}
    v = _menu_fields(merged)
    clash = MenuItem.query.filter(MenuItem.outlet_id == outlet_id, MenuItem.name == v["name"],
                                  MenuItem.id != item.id).first()
    if clash:
        raise ValidationError("Please fix the highlighted fields.", {"name": "already exists"})
    for k, val in v.items():
        setattr(item, k, val)
    if "is_active" in data:
        item.is_active = bool(data["is_active"])
    audit.record(outlet_id, actor_id, "menu.update", "menu_item", item.id)
    db.session.commit()
    return item


def set_availability(outlet_id: int, item_id: int, is_available: bool, actor_id: int | None = None) -> MenuItem:
    """K13: the manager marks an item available or unavailable. One persistent flag; it does not change the forecast."""
    item = get_menu_item(outlet_id, item_id)
    if not item.is_active:
        raise ValidationError("That menu item is not active.", {"menu_item_id": "is not active"})
    item.is_available = bool(is_available)
    audit.record(outlet_id, actor_id, "menu.availability", "menu_item", item.id, {"is_available": item.is_available})
    db.session.commit()
    return item


# ---- recipes (A5) ----------------------------------------------------------------------------
def get_recipe(outlet_id: int, item_id: int) -> list[RecipeLine]:
    item = get_menu_item(outlet_id, item_id)
    return sorted(item.recipe_lines, key=lambda r: r.id)


def set_recipe(outlet_id: int, item_id: int, lines: list[dict], actor_id: int | None = None) -> list[RecipeLine]:
    """Replace all recipe lines atomically. Quantities are in each ingredient's base unit."""
    item = get_menu_item(outlet_id, item_id)
    if not isinstance(lines, list):
        raise ValidationError("Please fix the highlighted fields.", {"lines": "must be a list"})
    errors, seen, clean = {}, set(), []
    for i, raw in enumerate(lines):
        f = Fields(raw if isinstance(raw, dict) else {})
        ing_id = f.integer("ingredient_id")
        qty = f.decimal("quantity_per_portion", gt=0)
        if f.errors:
            errors[f"lines[{i}]"] = "; ".join(f"{k} {m}" for k, m in f.errors.items())
            continue
        if ing_id in seen:
            errors[f"lines[{i}]"] = "ingredient appears twice"
            continue
        seen.add(ing_id)
        if not Ingredient.query.filter_by(id=ing_id, outlet_id=outlet_id).first():
            errors[f"lines[{i}]"] = "unknown ingredient"
            continue
        clean.append((ing_id, qty))
    if errors:
        raise ValidationError("Please fix the highlighted fields.", errors)
    RecipeLine.query.filter_by(menu_item_id=item.id).delete()
    db.session.flush()
    db.session.expire(item)
    for ing_id, qty in clean:
        db.session.add(RecipeLine(menu_item_id=item.id, ingredient_id=ing_id, quantity_per_portion=qty))
    audit.record(outlet_id, actor_id, "recipe.update", "menu_item", item.id, {"lines": len(clean)})
    db.session.commit()
    return get_recipe(outlet_id, item_id)


def items_without_recipe(outlet_id: int) -> list[MenuItem]:
    return [m for m in list_menu_items(outlet_id, active_only=True) if not m.recipe_lines]

# ---- CSV import (A14, A15) -------------------------------------------------------------------
MAX_IMPORT_ROWS = 60000
MAX_ERRORS_SHOWN = 200
ALIASES = {
    "date": "date", "day": "date", "sale_date": "date",
    "item": "item", "menu_item": "item", "item_name": "item",
    "quantity": "quantity", "quantity_sold": "quantity", "qty": "quantity", "sold": "quantity",
    "unit_price": "unit_price", "price": "unit_price",
    "type": "type", "holiday_type": "type",
    "rain_mm": "rain_mm", "rain": "rain_mm", "temp_c": "temp_c", "temperature": "temp_c", "temp": "temp_c",
}


def _read_csv(content, required: list[str]) -> list[tuple[int, dict]]:
    """Decode and parse; raise a readable ValidationError for empty files, bad encoding or missing columns."""
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValidationError("The file is not UTF-8 text. Save it as CSV (UTF-8) and try again.",
                                  code="bad_file")
    if not content.strip():
        raise ValidationError("The file is empty.", code="bad_file")
    try:
        reader = csv.DictReader(io.StringIO(content))
        headers = [ALIASES.get((h or "").strip().lower().replace(" ", "_"), (h or "").strip().lower())
                   for h in (reader.fieldnames or [])]
    except csv.Error:
        raise ValidationError("The file could not be read as CSV.", code="bad_file")
    missing = [c for c in required if c not in headers]
    if missing:
        raise ValidationError(f"Missing column(s): {', '.join(missing)}. Expected: {', '.join(required)}.",
                              code="bad_file")
    rows = []
    try:
        for i, raw in enumerate(reader, start=2):  # row 1 is the header
            if len(rows) >= MAX_IMPORT_ROWS:
                raise ValidationError(f"Too many rows (limit {MAX_IMPORT_ROWS}). Split the file.", code="bad_file")
            row = {headers[j]: (v or "").strip() for j, (k, v) in enumerate(raw.items()) if j < len(headers)}
            if any(row.values()):
                rows.append((i, row))
    except csv.Error:
        raise ValidationError("The file could not be read as CSV.", code="bad_file")
    return rows


class _Report:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.accepted = 0
        self.rejected = 0
        self.skipped_unchanged = 0
        self.errors: list[dict] = []

    def reject(self, row, field, message):
        self.rejected += 1
        if len(self.errors) < MAX_ERRORS_SHOWN:
            self.errors.append({"row": row, "field": field, "message": message})

    def as_dict(self):
        return {"dry_run": self.dry_run, "accepted": self.accepted, "rejected": self.rejected,
                "skipped_unchanged": self.skipped_unchanged, "errors": self.errors,
                "errors_truncated": self.rejected > len(self.errors)}


def import_sales_csv(outlet_id: int, content, dry_run: bool = True, on_conflict: str = "skip",
                     source: str = "import", actor_id: int | None = None) -> dict:
    """CSV of date, item, quantity[, unit_price]. Validate everything first; save only when dry_run is False."""
    if on_conflict not in ("skip", "overwrite"):
        raise ValidationError("on_conflict must be skip or overwrite.", {"on_conflict": "invalid"})
    rows = _read_csv(content, ["date", "item", "quantity"])
    report = _Report(dry_run)
    items = {m.name.lower(): m for m in list_menu_items(outlet_id)}
    parsed, seen = [], set()
    limit = today()
    for rownum, r in rows:
        f = Fields(r)
        d = f.date("date", not_future=True)
        name = (r.get("item") or "").strip()
        item = items.get(name.lower())
        if not name:
            f.error("item", "is required")
        elif item is None:
            f.error("item", f"Unknown menu item '{name}'")
        q = f.decimal("quantity", min=0)
        if q is not None and q != q.to_integral_value():
            f.error("quantity", "must be a whole number")
        price = f.decimal("unit_price", required=False, min=0)
        if f.errors:
            field, msg = next(iter(f.errors.items()))
            report.reject(rownum, field, msg if field != "item" else msg)
            continue
        key = (item.id, d)
        if key in seen:
            report.reject(rownum, "date", "Duplicate of an earlier row for the same item and date")
            continue
        seen.add(key)
        parsed.append((rownum, item, d, int(q), price if price is not None else item.price))

    if parsed:
        dates = [p[2] for p in parsed]
        existing = {(s.menu_item_id, s.sale_date): s for s in SalesRecord.query.filter(
            SalesRecord.outlet_id == outlet_id, SalesRecord.sale_date >= min(dates), SalesRecord.sale_date <= max(dates))}
    else:
        existing = {}
    inserts, updates = [], []
    for rownum, item, d, q, price in parsed:
        cur = existing.get((item.id, d))
        if cur is None:
            inserts.append({"outlet_id": outlet_id, "menu_item_id": item.id, "sale_date": d, "quantity_sold": q,
                            "unit_price": price, "source": source, "created_by": actor_id})
            report.accepted += 1
        elif cur.quantity_sold == q and cur.unit_price == price:
            report.skipped_unchanged += 1
        elif on_conflict == "overwrite":
            updates.append((cur, q, price))
            report.accepted += 1
        else:
            report.reject(rownum, "quantity", f"A different record already exists for {item.name} on {d} "
                                              f"(quantity {cur.quantity_sold}); use overwrite to replace it")
    if not dry_run and (inserts or updates):
        if inserts:
            db.session.bulk_insert_mappings(SalesRecord, inserts)
        for cur, q, price in updates:
            cur.quantity_sold, cur.unit_price, cur.source = q, price, source
        audit.record(outlet_id, actor_id, "sales.import", "sales_records", None,
                     {"inserted": len(inserts), "updated": len(updates), "source": source})
        db.session.commit()
    return report.as_dict()


def import_holidays_csv(outlet_id: int, content, dry_run: bool = True, source: str = "imported",
                        actor_id: int | None = None) -> dict:
    """CSV of date, name, type (public, poya, school, other)."""
    rows = _read_csv(content, ["date", "name", "type"])
    report = _Report(dry_run)
    existing = {(h.holiday_date, h.name) for h in Holiday.query.filter_by(outlet_id=outlet_id)}
    inserts, seen = [], set()
    for rownum, r in rows:
        f = Fields(r)
        d = f.date("date")
        name = f.text("name", max_len=120)
        kind = f.choice("type", HOLIDAY_TYPES)
        if f.errors:
            field, msg = next(iter(f.errors.items()))
            report.reject(rownum, field, msg)
            continue
        if (d, name) in existing or (d, name) in seen:
            report.skipped_unchanged += 1
            continue
        seen.add((d, name))
        inserts.append({"outlet_id": outlet_id, "holiday_date": d, "name": name, "holiday_type": kind, "source": source})
        report.accepted += 1
    if not dry_run and inserts:
        db.session.bulk_insert_mappings(Holiday, inserts)
        audit.record(outlet_id, actor_id, "holidays.import", "holidays", None, {"inserted": len(inserts)})
        db.session.commit()
    return report.as_dict()


def import_weather_csv(outlet_id: int, content, dry_run: bool = True, source: str = "imported",
                       on_conflict: str = "skip", actor_id: int | None = None) -> dict:
    """CSV of date, rain_mm[, temp_c]. `source` is stored on each row (manual, imported, api, synthetic)."""
    rows = _read_csv(content, ["date", "rain_mm"])
    report = _Report(dry_run)
    existing = {w.weather_date: w for w in WeatherDaily.query.filter_by(outlet_id=outlet_id)}
    inserts, updates, seen = [], [], set()
    for rownum, r in rows:
        f = Fields(r)
        d = f.date("date")
        rain = f.decimal("rain_mm", min=0)
        temp = f.decimal("temp_c", required=False, min=-10, max=60)
        if f.errors:
            field, msg = next(iter(f.errors.items()))
            report.reject(rownum, field, msg)
            continue
        if d in seen:
            report.reject(rownum, "date", "Duplicate date in file")
            continue
        seen.add(d)
        cur = existing.get(d)
        if cur is None:
            inserts.append({"outlet_id": outlet_id, "weather_date": d, "rain_mm": rain, "temp_c": temp, "source": source})
            report.accepted += 1
        elif cur.rain_mm == rain and cur.temp_c == temp:
            report.skipped_unchanged += 1
        elif on_conflict == "overwrite":
            updates.append((cur, rain, temp))
            report.accepted += 1
        else:
            report.reject(rownum, "date", f"Weather for {d} already exists with different values; use overwrite")
    if not dry_run and (inserts or updates):
        if inserts:
            db.session.bulk_insert_mappings(WeatherDaily, inserts)
        for cur, rain, temp in updates:
            cur.rain_mm, cur.temp_c, cur.source = rain, temp, source
        audit.record(outlet_id, actor_id, "weather.import", "weather_daily", None,
                     {"inserted": len(inserts), "updated": len(updates)})
        db.session.commit()
    return report.as_dict()


# ---- promotions (A15) ------------------------------------------------------------------------
def list_promotions(outlet_id: int) -> list[Promotion]:
    return Promotion.query.filter_by(outlet_id=outlet_id).order_by(Promotion.start_date.desc()).all()


def create_promotion(outlet_id: int, data: dict, actor_id: int | None = None) -> Promotion:
    f = Fields(data)
    f.text("name", max_len=120)
    f.date("start_date")
    f.date("end_date")
    f.decimal("discount_pct", min=0, max=100)
    f.text("promo_type", required=False, max_len=30, default="percent_off")
    applies_all = bool(data.get("applies_to_all"))
    item_ids = data.get("item_ids") or []
    v = f.check()
    if v["end_date"] < v["start_date"]:
        raise ValidationError("Please fix the highlighted fields.", {"end_date": "must not be before the start date"})
    if not applies_all:
        if not item_ids:
            raise ValidationError("Please fix the highlighted fields.", {"item_ids": "choose at least one item or all items"})
        valid = {m.id for m in list_menu_items(outlet_id)}
        if any(i not in valid for i in item_ids):
            raise ValidationError("Please fix the highlighted fields.", {"item_ids": "unknown menu item"})
    promo = Promotion(outlet_id=outlet_id, applies_to_all=applies_all, **v)
    db.session.add(promo)
    db.session.flush()
    if not applies_all:
        for i in sorted(set(item_ids)):
            db.session.add(PromotionItem(promotion_id=promo.id, menu_item_id=i))
    audit.record(outlet_id, actor_id, "promotion.create", "promotion", promo.id)
    db.session.commit()
    return promo


def set_promotion_active(outlet_id: int, promotion_id: int, is_active: bool) -> Promotion:
    promo = Promotion.query.filter_by(id=promotion_id, outlet_id=outlet_id).first()
    if not promo:
        raise NotFoundError("Promotion not found.")
    promo.is_active = bool(is_active)
    db.session.commit()
    return promo


def list_holidays(outlet_id: int, start=None, end=None) -> list[Holiday]:
    q = Holiday.query.filter_by(outlet_id=outlet_id)
    if start:
        q = q.filter(Holiday.holiday_date >= start)
    if end:
        q = q.filter(Holiday.holiday_date <= end)
    return q.order_by(Holiday.holiday_date).all()


def list_weather(outlet_id: int, start=None, end=None) -> list[WeatherDaily]:
    q = WeatherDaily.query.filter_by(outlet_id=outlet_id)
    if start:
        q = q.filter(WeatherDaily.weather_date >= start)
    if end:
        q = q.filter(WeatherDaily.weather_date <= end)
    return q.order_by(WeatherDaily.weather_date).all()


# ---- frames for the forecasting service ------------------------------------------------------
def load_sales_frame(outlet_id: int, before=None) -> pd.DataFrame:
    q = db.session.query(SalesRecord.menu_item_id, SalesRecord.sale_date, SalesRecord.quantity_sold).filter(
        SalesRecord.outlet_id == outlet_id)
    if before is not None:
        q = q.filter(SalesRecord.sale_date < before)
    df = pd.DataFrame(q.all(), columns=["item_id", "date", "qty"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_holidays_frame(outlet_id: int) -> pd.DataFrame:
    rows = db.session.query(Holiday.holiday_date, Holiday.holiday_type).filter_by(outlet_id=outlet_id).all()
    df = pd.DataFrame(rows, columns=["date", "holiday_type"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_weather_frame(outlet_id: int) -> pd.DataFrame:
    rows = db.session.query(WeatherDaily.weather_date, WeatherDaily.rain_mm, WeatherDaily.temp_c).filter_by(
        outlet_id=outlet_id).all()
    df = pd.DataFrame([(d, float(r), None if t is None else float(t)) for d, r, t in rows],
                      columns=["date", "rain_mm", "temp_c"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_promotions_frame(outlet_id: int) -> pd.DataFrame:
    """Active promotions expanded to one row per (item, day)."""
    all_items = [m.id for m in list_menu_items(outlet_id)]
    rows = []
    for p in Promotion.query.filter_by(outlet_id=outlet_id, is_active=True):
        ids = all_items if p.applies_to_all else [pi.menu_item_id for pi in p.items]
        d = p.start_date
        while d <= p.end_date:
            for i in ids:
                rows.append((i, d, float(p.discount_pct)))
            d += timedelta(days=1)
    df = pd.DataFrame(rows, columns=["item_id", "date", "discount_pct"])
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---- serializers for the API layer -----------------------------------------------------------
def menu_item_dict(m: MenuItem) -> dict:
    return {"id": m.id, "name": m.name, "category": m.category, "price": float(m.price), "portion_unit": m.portion_unit,
            "shelf_life_hours": m.shelf_life_hours, "batch_size": m.batch_size, "is_active": m.is_active,
            "is_available": m.is_available, "has_recipe": bool(m.recipe_lines)}


def recipe_dict(lines) -> list[dict]:
    return [{"ingredient_id": r.ingredient_id, "ingredient": r.ingredient.name, "unit": r.ingredient.unit,
             "quantity_per_portion": float(r.quantity_per_portion)} for r in lines]


def promotion_dict(p: Promotion) -> dict:
    return {"id": p.id, "name": p.name, "start_date": p.start_date.isoformat(), "end_date": p.end_date.isoformat(),
            "discount_pct": float(p.discount_pct), "applies_to_all": p.applies_to_all, "promo_type": p.promo_type,
            "is_active": p.is_active, "item_ids": [i.menu_item_id for i in p.items]}


def holiday_dict(h: Holiday) -> dict:
    return {"id": h.id, "date": h.holiday_date.isoformat(), "name": h.name, "type": h.holiday_type}


def weather_dict(w: WeatherDaily) -> dict:
    return {"date": w.weather_date.isoformat(), "rain_mm": float(w.rain_mm),
            "temp_c": None if w.temp_c is None else float(w.temp_c), "source": w.source}
