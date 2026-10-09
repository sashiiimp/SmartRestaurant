"""Read-only check of a real restaurant sales export before it is imported anywhere (docs/data/REAL_DATA_PROTOCOL.md).

Usage:  .venv/bin/python scripts/validate_sales_csv.py SALES.csv [--mapping MAP.csv] [--closed CLOSED.csv] [--out REPORT.md]

It reads files only: no database, no network, no app. The rules mirror the application so a file that passes here
will also pass the import's dry run:
- columns `date, item, quantity` and optional `unit_price` (same aliases as the import), ISO dates, whole quantities >= 0;
- one row per item and date;
- a day more than 10 x the item's typical (median) day is reported as a likely typo (the import's outlier rule);
- at least 146 days from first to last date (56-day hold-out + 90 days), the minimum the training needs.
It also lists dates with no rows at all (closed days must be confirmed by the outlet, never filled with zeros), each
month's total portions for the outlet manager to reconcile and sign off, and the file's SHA-256 for provenance.
Exit code 0 when no error was found, 1 otherwise.
"""
import argparse
import csv
import hashlib
import io
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

ALIASES = {"date": "date", "day": "date", "sale_date": "date", "item": "item", "menu_item": "item",
           "item_name": "item", "quantity": "quantity", "quantity_sold": "quantity", "qty": "quantity",
           "sold": "quantity", "unit_price": "unit_price", "price": "unit_price"}
MAX_PORTIONS = 10_000          # app/services/validation.py
OUTLIER_FACTOR = 10            # app/services/data_management_service.py
OUTLIER_MIN_ROWS = 7
MIN_SPAN_DAYS = 56 + 90        # app/ml/train.py: hold-out + 90 days
MAX_LISTED = 25


def read_rows(path: Path) -> tuple[list[dict], list[str]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["The file is not UTF-8 text. Export it again as CSV UTF-8."]
    reader = csv.DictReader(io.StringIO(text))
    headers = [ALIASES.get((h or "").strip().lower().replace(" ", "_"), (h or "").strip().lower())
               for h in (reader.fieldnames or [])]
    missing = [c for c in ("date", "item", "quantity") if c not in headers]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Found: {', '.join(reader.fieldnames or []) or 'none'}."]
    reader.fieldnames = headers
    return [dict(r, _line=i) for i, r in enumerate(reader, start=2)], []


def check(rows: list[dict], mapping: dict | None, closed: set) -> dict:
    errors, warnings = [], []
    seen, per_item, per_month, days_with_rows = {}, defaultdict(list), defaultdict(int), set()
    for r in rows:
        line, item = r["_line"], (r.get("item") or "").strip()
        try:
            d = date.fromisoformat((r.get("date") or "").strip())
        except ValueError:
            errors.append(f"Line {line}: date '{r.get('date')}' is not YYYY-MM-DD.")
            continue
        q_raw = (r.get("quantity") or "").strip()
        if not q_raw.lstrip("-").isdigit():
            errors.append(f"Line {line}: quantity '{q_raw}' is not a whole number.")
            continue
        q = int(q_raw)
        if q < 0 or q > MAX_PORTIONS:
            errors.append(f"Line {line}: quantity {q} is outside 0 to {MAX_PORTIONS}.")
            continue
        if not item:
            errors.append(f"Line {line}: the item name is empty.")
            continue
        price = (r.get("unit_price") or "").strip()
        if price:
            try:
                if Decimal(price) < 0:
                    raise InvalidOperation
            except InvalidOperation:
                errors.append(f"Line {line}: unit_price '{price}' is not a number of 0 or more.")
        key = (d, item)
        if key in seen:
            errors.append(f"Line {line}: {item} on {d} already appears on line {seen[key]} (one row per item and day).")
            continue
        seen[key] = line
        if d in closed:
            warnings.append(f"Line {line}: {item} has sales on {d}, which is listed as a closed day.")
        per_item[item].append((d, q))
        per_month[d.strftime("%Y-%m")] += q
        days_with_rows.add(d)

    if mapping is not None:
        unmapped = sorted(i for i in per_item if i not in mapping)
        if unmapped:
            errors.append("Items without a SmartRestaurant menu item in the mapping file: " + ", ".join(unmapped) + ".")

    outliers = []
    for item, vals in per_item.items():
        if len(vals) < OUTLIER_MIN_ROWS:
            continue
        ref = statistics.median(q for _, q in vals)
        outliers += [f"{item} on {d}: {q} (typical day {ref:g})" for d, q in vals if ref > 0 and q > OUTLIER_FACTOR * ref]
    if outliers:
        errors.append(f"{len(outliers)} day(s) above {OUTLIER_FACTOR} x the item's typical day (likely typos): "
                      + "; ".join(outliers[:MAX_LISTED]) + (" ..." if len(outliers) > MAX_LISTED else ""))

    first, last = (min(days_with_rows), max(days_with_rows)) if days_with_rows else (None, None)
    span = (last - first).days + 1 if first else 0
    if first and span < MIN_SPAN_DAYS:
        errors.append(f"The data covers {span} days ({first} to {last}); training and evaluation need at least "
                      f"{MIN_SPAN_DAYS}. Ask for a longer export (12 to 24 months recommended).")
    gaps = []
    if first:
        d = first
        while d <= last:
            if d not in days_with_rows and d not in closed:
                gaps.append(d)
            d += timedelta(days=1)
    if gaps:
        warnings.append(f"{len(gaps)} date(s) have no rows and are not listed as closed: "
                        + ", ".join(str(g) for g in gaps[:MAX_LISTED]) + (" ..." if len(gaps) > MAX_LISTED else "")
                        + ". Ask the outlet whether it was closed; never fill these with zeros.")
    return {"errors": errors, "warnings": warnings, "first": first, "last": last, "span": span,
            "rows": sum(len(v) for v in per_item.values()), "items": {i: len(v) for i, v in sorted(per_item.items())},
            "per_month": dict(sorted(per_month.items()))}


def read_simple(path: Path | None, cols: tuple) -> list[dict] | None:
    if path is None:
        return None
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [{c: (r.get(c) or "").strip() for c in cols} for r in csv.DictReader(fh)]


def report(path: Path, res: dict, sha: str) -> str:
    out = [f"# Sales file check: {path.name}", "", f"SHA-256 `{sha}`", "",
           f"**{'PASS' if not res['errors'] else 'FAIL'}**: {len(res['errors'])} error(s), {len(res['warnings'])} warning(s)", ""]
    if res["first"]:
        out += [f"Rows {res['rows']}, items {len(res['items'])}, dates {res['first']} to {res['last']} ({res['span']} days)", ""]
    for title, key in (("Errors", "errors"), ("Warnings", "warnings")):
        if res[key]:
            out += [f"## {title}", ""] + [f"- {m}" for m in res[key]] + [""]
    if res["items"]:
        out += ["## Days recorded per item", "", "| Item | Days |", "|---|---|"]
        out += [f"| {i} | {n} |" for i, n in res["items"].items()] + [""]
    if res["per_month"]:
        out += ["## Monthly totals (for the outlet manager to reconcile and sign)", "", "| Month | Portions | Matches outlet records? |",
                "|---|---|---|"] + [f"| {m} | {q} | |" for m, q in res["per_month"].items()] + [""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sales", type=Path)
    ap.add_argument("--mapping", type=Path, help="CSV: outlet_item,menu_item")
    ap.add_argument("--closed", type=Path, help="CSV: date (days the outlet was closed)")
    ap.add_argument("--out", type=Path, help="write the report here instead of printing it")
    a = ap.parse_args(argv)
    sha = hashlib.sha256(a.sales.read_bytes()).hexdigest()
    rows, problems = read_rows(a.sales)
    m = read_simple(a.mapping, ("outlet_item", "menu_item"))
    mapping = None if m is None else {r["outlet_item"]: r["menu_item"] for r in m}
    closed_rows = read_simple(a.closed, ("date",)) or []
    closed = set()
    for r in closed_rows:
        try:
            closed.add(date.fromisoformat(r["date"]))
        except ValueError:
            problems.append(f"Closed-days file: '{r['date']}' is not YYYY-MM-DD.")
    res = check(rows, mapping, closed)
    res["errors"] = problems + res["errors"]
    text = report(a.sales, res, sha)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
        print(f"{'PASS' if not res['errors'] else 'FAIL'}: report written to {a.out}")
    else:
        print(text)
    return 0 if not res["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
