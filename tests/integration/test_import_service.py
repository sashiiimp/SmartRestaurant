"""IMP-1 .. IMP-5, VAL-2, VAL-3: sales, holiday and weather import (A14, A15)."""
from datetime import date

import pytest

from app.models import SalesRecord, WeatherDaily
from app.services import data_management_service as dm
from app.services.errors import ValidationError
from tests.factories import make_item

GOOD = "date,item,quantity,unit_price\n2026-09-01,Burger,40,650\n2026-09-02,Burger,42,650\n"


@pytest.fixture()
def burger(app):
    return make_item(name="Burger", price=650)


def test_dry_run_reports_errors_and_saves_nothing(burger):
    csv = "date,item,quantity\n2026-09-01,Burger,40\n2026-09-02,Chiken,5\n2026-09-03,Burger,abc\n2026-09-04,Burger,-3\n"
    r = dm.import_sales_csv(1, csv, dry_run=True)
    assert (r["accepted"], r["rejected"]) == (1, 3)
    assert [e["row"] for e in r["errors"]] == [3, 4, 5]
    assert "Unknown menu item 'Chiken'" in r["errors"][0]["message"]
    assert SalesRecord.query.count() == 0


def test_commit_saves_valid_rows_and_reimport_creates_no_duplicates(burger):
    csv = "date,item,quantity\n2026-09-01,Burger,40\n2026-09-02,Nope,5\n"
    r = dm.import_sales_csv(1, csv, dry_run=False, source="import")
    assert r["accepted"] == 1 and r["rejected"] == 1
    assert SalesRecord.query.count() == 1
    again = dm.import_sales_csv(1, csv, dry_run=False)
    assert again["accepted"] == 0 and again["skipped_unchanged"] == 1
    assert SalesRecord.query.count() == 1


def test_unknown_items_are_never_created(burger):
    from app.models import MenuItem
    dm.import_sales_csv(1, "date,item,quantity\n2026-09-01,Ghost,5\n", dry_run=False)
    assert MenuItem.query.filter_by(name="Ghost").count() == 0


def test_conflict_skip_vs_overwrite(burger):
    dm.import_sales_csv(1, GOOD, dry_run=False)
    changed = "date,item,quantity\n2026-09-01,Burger,99\n"
    skipped = dm.import_sales_csv(1, changed, dry_run=False, on_conflict="skip")
    assert skipped["rejected"] == 1 and "already exists" in skipped["errors"][0]["message"]
    assert SalesRecord.query.filter_by(sale_date=date(2026, 9, 1)).one().quantity_sold == 40
    over = dm.import_sales_csv(1, changed, dry_run=False, on_conflict="overwrite")
    assert over["accepted"] == 1
    assert SalesRecord.query.filter_by(sale_date=date(2026, 9, 1)).one().quantity_sold == 99


def test_zero_accepted_negative_and_future_rejected(burger):
    csv = "date,item,quantity\n2026-09-01,Burger,0\n2026-09-02,Burger,-1\n2026-09-30,Burger,5\n"  # today is 2026-09-25
    r = dm.import_sales_csv(1, csv, dry_run=True)
    assert r["accepted"] == 1 and r["rejected"] == 2
    assert any("future" in e["message"] for e in r["errors"])


def test_duplicate_rows_within_a_file_are_rejected(burger):
    r = dm.import_sales_csv(1, "date,item,quantity\n2026-09-01,Burger,5\n2026-09-01,Burger,6\n", dry_run=True)
    assert r["accepted"] == 1 and r["rejected"] == 1


def test_price_defaults_to_menu_price(burger):
    dm.import_sales_csv(1, "date,item,quantity\n2026-09-01,Burger,5\n", dry_run=False)
    assert float(SalesRecord.query.one().unit_price) == 650.0


@pytest.mark.parametrize("content,fragment", [
    ("", "empty"),
    ("   \n", "empty"),
    ("foo,bar\n1,2\n", "Missing column"),
    (b"\xff\xfe\x00bad", "UTF-8"),
])
def test_bad_files_give_readable_errors(burger, content, fragment):
    with pytest.raises(ValidationError) as e:
        dm.import_sales_csv(1, content, dry_run=True)
    assert fragment in e.value.message


def test_header_only_file_is_fine(burger):
    r = dm.import_sales_csv(1, "date,item,quantity\n", dry_run=True)
    assert r["accepted"] == 0 and r["rejected"] == 0


def test_holiday_and_weather_imports(burger):
    h = dm.import_holidays_csv(1, "date,name,type\n2026-09-26,Binara Poya,poya\n2026-09-27,X,bogus\n", dry_run=False)
    assert h["accepted"] == 1 and h["rejected"] == 1
    assert dm.import_holidays_csv(1, "date,name,type\n2026-09-26,Binara Poya,poya\n", dry_run=False)["skipped_unchanged"] == 1
    w = dm.import_weather_csv(1, "date,rain_mm,temp_c\n2026-09-01,12.5,28\n2026-09-02,-1,28\n", dry_run=False, source="manual")
    assert w["accepted"] == 1 and w["rejected"] == 1
    assert WeatherDaily.query.one().source == "manual"
