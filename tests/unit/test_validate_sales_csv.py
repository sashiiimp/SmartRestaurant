"""scripts/validate_sales_csv.py: the read-only check for a real sales export (docs/data/REAL_DATA_PROTOCOL.md).
All files here are made up for the test and say so; they are not restaurant data."""
import importlib.util
from datetime import date, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "validate_sales_csv", Path(__file__).resolve().parents[2] / "scripts" / "validate_sales_csv.py")
v = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v)

START = date(2026, 1, 1)


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def days_csv(n_days, qty=10, item="Chicken Burger", skip=(), extra=""):
    lines = ["Date,Item,Qty,Price"]
    for i in range(n_days):
        if i not in skip:
            lines.append(f"{START + timedelta(days=i)},{item},{qty},650")
    return "\n".join(lines) + "\n" + extra


def run(tmp_path, text, *args):
    p = write(tmp_path, "sales.csv", text)
    out = tmp_path / "report.md"
    code = v.main([str(p), "--out", str(out), *args])
    return code, out.read_text()


def test_a_clean_file_of_146_days_passes_and_aliases_are_accepted(tmp_path):
    code, rep = run(tmp_path, days_csv(146))
    assert code == 0 and "**PASS**" in rep and "(146 days)" in rep
    assert "| 2026-01 | 310 |" in rep          # 31 days x 10 portions


def test_145_days_is_too_short(tmp_path):
    code, rep = run(tmp_path, days_csv(145))
    assert code == 1 and "covers 145 days" in rep


def test_bad_values_duplicates_and_outliers_are_errors(tmp_path):
    extra = ("2026-01-05,Chicken Burger,12,650\n"     # duplicate of day 5
             "05/01/2026,Fries,3,450\n"                # not ISO
             "2026-01-06,Fries,2.5,450\n"              # not whole
             "2026-01-07,Fries,-1,450\n"               # negative
             "2026-01-08,Fries,3,abc\n")               # bad price
    text = days_csv(146).replace(f"{START + timedelta(days=20)},Chicken Burger,10,650",
                                 f"{START + timedelta(days=20)},Chicken Burger,101,650")  # 101 > 10 x median 10
    code, rep = run(tmp_path, text + extra)
    assert code == 1
    for fragment in ("already appears on line", "is not YYYY-MM-DD", "'2.5' is not a whole number",
                     "outside 0 to 10000", "unit_price 'abc'", "Chicken Burger on 2026-01-21: 101 (typical day 10)"):
        assert fragment in rep, fragment


def test_missing_days_are_warnings_unless_listed_as_closed(tmp_path):
    text = days_csv(150, skip=(10, 11))
    code, rep = run(tmp_path, text)
    assert code == 0 and "2 date(s) have no rows" in rep and "2026-01-11, 2026-01-12" in rep
    closed = write(tmp_path, "closed.csv", "date\n2026-01-11\n2026-01-12\n")
    code, rep = run(tmp_path, text, "--closed", str(closed))
    assert code == 0 and "have no rows" not in rep


def test_items_missing_from_the_mapping_are_errors(tmp_path):
    mapping = write(tmp_path, "map.csv", "outlet_item,menu_item\nChicken Burger,Chicken Burger\n")
    code, rep = run(tmp_path, days_csv(146) + "2026-01-02,Zinger Box,4,900\n", "--mapping", str(mapping))
    assert code == 1 and "Items without a SmartRestaurant menu item in the mapping file: Zinger Box." in rep


def test_wrong_columns_and_encoding_give_a_readable_error(tmp_path):
    code, rep = run(tmp_path, "when,what\n2026-01-01,x\n")
    assert code == 1 and "Missing column(s): date, item, quantity" in rep
    p = tmp_path / "latin1.csv"
    p.write_bytes("date,item,quantity\n2026-01-01,Caf\xe9,1\n".encode("latin-1"))
    assert v.main([str(p), "--out", str(tmp_path / "r.md")]) == 1
    assert "not UTF-8" in (tmp_path / "r.md").read_text()
