"""Copy the verified MariaDB copy into the empty MySQL schema and prove they are identical.

Usage (cwd = clone of the production code): python maria_to_mysql.py SOURCE_URL TARGET_URL [--copy]
- compare: column names/types/nullability, foreign keys, CHECK names, unique keys, indexes per table
- --copy: insert every row in foreign-key order, keeping primary keys, with FOREIGN_KEY_CHECKS on
- verify: row counts, a content checksum of every table (values normalised: JSON parsed, decimals as text),
  orphan count for every foreign key, AUTO_INCREMENT above the highest id.
The source is only read. Nothing is printed that contains a password.
"""
import hashlib
import json
import sys
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text

src_url, dst_url = sys.argv[1], sys.argv[2]
DO_COPY = "--copy" in sys.argv
sys.path.insert(0, ".")
from app.extensions import db  # noqa: E402
import app.models  # noqa: E402,F401  (registers every table on db.metadata)

src, dst = create_engine(src_url), create_engine(dst_url)
tables = [t for t in db.metadata.sorted_tables]
assert len(tables) == 30, len(tables)
problems = []


def norm_type(t):
    s = str(t).upper()
    if s in ("LONGTEXT", "JSON"):
        return "JSON"           # MariaDB stores JSON as LONGTEXT + JSON_VALID; MySQL has a native type
    if s.startswith("TINYINT"):
        return "TINYINT"
    if s.startswith("INTEGER") or s.startswith("INT"):
        return "INT"
    return s.replace(" COLLATE \"UTF8MB4_UNICODE_CI\"", "")


# ---- 1. schema comparison ------------------------------------------------------------------------------
si, di = inspect(src), inspect(dst)
for t in tables:
    n = t.name
    sc = {c["name"]: (norm_type(c["type"]), c["nullable"]) for c in si.get_columns(n)}
    dc = {c["name"]: (norm_type(c["type"]), c["nullable"]) for c in di.get_columns(n)}
    if sc != dc:
        problems.append(f"{n}: columns differ: {sorted(set(sc.items()) ^ set(dc.items()))}")
    sf = sorted((f["name"], tuple(f["constrained_columns"]), f["referred_table"]) for f in si.get_foreign_keys(n))
    df = sorted((f["name"], tuple(f["constrained_columns"]), f["referred_table"]) for f in di.get_foreign_keys(n))
    if sf != df:
        problems.append(f"{n}: foreign keys differ")
    sk = sorted(c["name"] for c in si.get_check_constraints(n) if not c["name"].startswith(tuple(f"{x}" for x in ("details", "detail", "input_snapshot", "feature_set", "params", "metrics"))))
    dk = sorted(c["name"] for c in di.get_check_constraints(n))
    if sk != dk:
        problems.append(f"{n}: CHECK constraints differ: {sorted(set(sk) ^ set(dk))}")
    su = sorted((u["name"], tuple(u["column_names"])) for u in si.get_unique_constraints(n))
    du = sorted((u["name"], tuple(u["column_names"])) for u in di.get_unique_constraints(n))
    if su != du:
        problems.append(f"{n}: unique keys differ: {sorted(set(su) ^ set(du))}")
    sx = sorted((x["name"], tuple(x["column_names"])) for x in si.get_indexes(n) if not x.get("unique"))
    dx = sorted((x["name"], tuple(x["column_names"])) for x in di.get_indexes(n) if not x.get("unique"))
    if sx != dx:
        problems.append(f"{n}: indexes differ: {sorted(set(sx) ^ set(dx))}")
print(f"schema compared for {len(tables)} tables: {'identical' if not problems else str(len(problems)) + ' difference(s)'}")
for p in problems:
    print("  ", p)

JSON_COLS = {(c.table.name, c.name) for t in tables for c in t.columns if c.type.__class__.__name__ == "JSON"}


def rows_of(engine, t):
    pk = ", ".join(f"`{c.name}`" for c in t.primary_key.columns)
    with engine.connect() as con:
        return [dict(r._mapping) for r in con.execute(text(f"SELECT * FROM `{t.name}` ORDER BY {pk}"))]


def normal(t, row):
    out = []
    for k in sorted(row):
        v = row[k]
        if (t.name, k) in JSON_COLS and v is not None:
            v = json.dumps(json.loads(v) if isinstance(v, (str, bytes)) else v, sort_keys=True)
        elif isinstance(v, Decimal):
            v = format(v.normalize(), "f")
        elif isinstance(v, (datetime, date)):
            v = v.isoformat()
        elif isinstance(v, bytes):
            v = v.decode()
        out.append((k, v))
    return out


def checksum(engine, t):
    rows = rows_of(engine, t)
    return len(rows), hashlib.sha256(repr([normal(t, r) for r in rows]).encode()).hexdigest()


# ---- 2. copy ---------------------------------------------------------------------------------------------
if DO_COPY:
    if problems:
        sys.exit("schema differs: not copying")
    with dst.begin() as con:
        for t in tables:
            n = con.execute(text(f"SELECT COUNT(*) FROM `{t.name}`")).scalar()
            if n:
                sys.exit(f"target table {t.name} is not empty ({n} rows): not copying")
    total = 0
    with dst.begin() as con:
        for t in tables:
            rows = rows_of(src, t)
            if rows:
                for r in rows:          # JSON arrives as text from MariaDB; give MySQL the parsed value
                    for c in r:
                        if (t.name, c) in JSON_COLS and isinstance(r[c], (str, bytes)):
                            r[c] = json.loads(r[c])
                con.execute(t.insert(), rows)
            total += len(rows)
    print(f"copied {total} rows into {len(tables)} tables (foreign key checks on)")

# ---- 3. verification -------------------------------------------------------------------------------------
bad = 0
for t in tables:
    s, d = checksum(src, t), checksum(dst, t)
    if s != d:
        bad += 1
        print(f"  MISMATCH {t.name}: source {s[0]} rows, target {d[0]} rows")
print(f"row counts and content checksums: {30 - bad} of 30 tables identical")
orph = 0
with dst.connect() as con:
    fks = con.execute(text("""SELECT table_name, column_name, referenced_table_name, referenced_column_name
        FROM information_schema.key_column_usage WHERE table_schema = DATABASE() AND referenced_table_name IS NOT NULL""")).all()
    for tn, cn, rt, rc in fks:
        n = con.execute(text(f"SELECT COUNT(*) FROM `{tn}` c LEFT JOIN `{rt}` p ON p.`{rc}` = c.`{cn}` "
                             f"WHERE c.`{cn}` IS NOT NULL AND p.`{rc}` IS NULL")).scalar()
        orph += n
    print(f"foreign keys checked: {len(fks)}, orphan rows: {orph}")
    low = []
    for t in tables:
        pkc = list(t.primary_key.columns)
        if len(pkc) == 1 and pkc[0].autoincrement in (True, "auto"):
            mx = con.execute(text(f"SELECT COALESCE(MAX(`{pkc[0].name}`), 0) FROM `{t.name}`")).scalar()
            ai = con.execute(text("SELECT AUTO_INCREMENT FROM information_schema.tables WHERE table_schema = DATABASE() "
                                  "AND table_name = :n"), {"n": t.name}).scalar()
            if ai is not None and ai <= mx:
                low.append(t.name)
    print(f"AUTO_INCREMENT above the highest id: {'all tables' if not low else 'NOT for ' + ', '.join(low)}")
sys.exit(1 if (problems or bad or orph or low) else 0)
