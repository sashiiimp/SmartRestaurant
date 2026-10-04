"""Build data/holidays_lk.csv: officially declared Poya days and public holidays, plus approximate school vacations.

Poya days and movable public holidays are the dates declared in the government calendars, checked on 4 Oct 2026
against: the Government Printing Department desk calendars and gazettes (documents.gov.lk), the Central Bank of
Sri Lanka bank-holiday lists (cbsl.gov.lk) and the published 2025 and 2026 holiday calendars (adaderana.lk,
news ids 104417 and 116465). An earlier version computed Poya days from the astronomical full moon; that put 19 of
them one day late, because the Poya Committee often declares the day before the full moon in Colombo time.

2026 Vesak: the calendar declares Vesak Poya on 1 May (with 2 May as the day after) and Adhi Poson Poya on 30 May;
an amendment later made 31 May a public holiday for the State Vesak celebration (EFC circular 17 of 2026).
School vacations are still approximate (the Ministry of Education term dates were not checked).
"""
import csv
import pathlib
from datetime import date, timedelta

OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "holidays_lk.csv"
START, END = date(2024, 8, 1), date(2026, 12, 31)

POYA = [  # (date, name), as declared
    (date(2024, 8, 19), "Nikini Poya"), (date(2024, 9, 17), "Binara Poya"), (date(2024, 10, 17), "Vap Poya"),
    (date(2024, 11, 15), "Il Poya"), (date(2024, 12, 14), "Unduvap Poya"),
    (date(2025, 1, 13), "Duruthu Poya"), (date(2025, 2, 12), "Navam Poya"), (date(2025, 3, 13), "Medin Poya"),
    (date(2025, 4, 12), "Bak Poya"), (date(2025, 5, 12), "Vesak Poya"), (date(2025, 6, 10), "Poson Poya"),
    (date(2025, 7, 10), "Esala Poya"), (date(2025, 8, 8), "Nikini Poya"), (date(2025, 9, 7), "Binara Poya"),
    (date(2025, 10, 6), "Vap Poya"), (date(2025, 11, 5), "Il Poya"), (date(2025, 12, 4), "Unduvap Poya"),
    (date(2026, 1, 3), "Duruthu Poya"), (date(2026, 2, 1), "Navam Poya"), (date(2026, 3, 2), "Medin Poya"),
    (date(2026, 4, 1), "Bak Poya"), (date(2026, 5, 1), "Vesak Poya"), (date(2026, 5, 30), "Adhi Poson Poya"),
    (date(2026, 6, 29), "Poson Poya"), (date(2026, 7, 29), "Esala Poya"), (date(2026, 8, 27), "Nikini Poya"),
    (date(2026, 9, 26), "Binara Poya"), (date(2026, 10, 25), "Vap Poya"), (date(2026, 11, 24), "Il Poya"),
    (date(2026, 12, 23), "Unduvap Poya"),
]

MOVABLE = [  # public holidays whose date changes every year, as declared
    (date(2024, 9, 16), "Milad-un-Nabi"), (date(2024, 10, 31), "Deepavali"),
    (date(2025, 1, 14), "Tamil Thai Pongal Day"), (date(2025, 2, 26), "Maha Shivaratri"),
    (date(2025, 3, 31), "Eid al-Fitr"), (date(2025, 5, 13), "Day after Vesak Poya"), (date(2025, 6, 7), "Eid al-Adha"),
    (date(2025, 9, 5), "Milad-un-Nabi"), (date(2025, 10, 20), "Deepavali"),
    (date(2026, 1, 15), "Tamil Thai Pongal Day"), (date(2026, 2, 15), "Maha Shivaratri"),
    (date(2026, 3, 21), "Eid al-Fitr"), (date(2026, 5, 2), "Day after Vesak Poya"), (date(2026, 5, 28), "Eid al-Adha"),
    (date(2026, 5, 31), "State Vesak holiday (amendment)"), (date(2026, 8, 26), "Milad-un-Nabi"),
    (date(2026, 11, 8), "Deepavali"),
]


def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def poya_days():
    return [(d, name, "poya") for d, name in POYA]


def public_days():
    rows = []
    for y in (2024, 2025, 2026):
        fixed = [(2, 4, "Independence Day"), (4, 13, "Day before Sinhala and Tamil New Year"),
                 (4, 14, "Sinhala and Tamil New Year"), (5, 1, "May Day"), (12, 25, "Christmas Day")]
        for m, d, name in fixed:
            rows.append((date(y, m, d), name, "public"))
        rows.append((easter(y) - timedelta(days=2), "Good Friday", "public"))
    rows += [(d, n, "public") for d, n in MOVABLE]
    return rows


def school_days():
    ranges = [(date(2024, 8, 1), date(2024, 8, 31)), (date(2024, 12, 15), date(2025, 1, 5)),
              (date(2025, 4, 8), date(2025, 4, 21)), (date(2025, 8, 4), date(2025, 8, 31)),
              (date(2025, 12, 14), date(2026, 1, 4)), (date(2026, 4, 3), date(2026, 4, 19)),
              (date(2026, 8, 3), date(2026, 8, 30)), (date(2026, 12, 13), date(2026, 12, 31))]
    rows = []
    for a, b in ranges:
        d = a
        while d <= b:
            rows.append((d, "School vacation (approx.)", "school"))
            d += timedelta(days=1)
    return rows


if __name__ == "__main__":
    rows = sorted(set(poya_days() + public_days() + school_days()))
    rows = [r for r in rows if START <= r[0] <= END]
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "name", "type"])
        for d, name, kind in rows:
            w.writerow([d.isoformat(), name, kind])
    poya = [r for r in rows if r[2] == "poya"]
    print(len(rows), "rows;", len(poya), "poya days;", len(rows) - len(poya) - sum(r[2] == "school" for r in rows),
          "public holidays")
