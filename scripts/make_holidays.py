"""Build data/holidays_lk.csv: Poya days (computed full moons, Colombo date), fixed public holidays,
movable public holidays typed in from memory, and approximate school-vacation ranges.

NOT an official calendar. Poya dates come from an astronomical full-moon calculation (Meeus, ch. 49) shifted to
Colombo time; movable holidays and school vacations are approximations. Verify against the official published
calendar before quoting them in the report (ML_PLAN.md section 2).
"""
import csv
import math
import pathlib
from datetime import date, datetime, timedelta, timezone

OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "holidays_lk.csv"
START, END = date(2024, 8, 1), date(2026, 12, 31)


def rad(x):
    return math.radians(x % 360)


def full_moon_jde(k):
    T = k / 1236.85
    jde = 2451550.09766 + 29.530588861 * k + 0.00015437 * T ** 2 - 0.00000015 * T ** 3 + 0.00000000073 * T ** 4
    E = 1 - 0.002516 * T - 0.0000074 * T ** 2
    M = 2.5534 + 29.10535670 * k - 0.0000014 * T ** 2
    Mp = 201.5643 + 385.81693528 * k + 0.0107582 * T ** 2
    F = 160.7108 + 390.67050284 * k - 0.0016118 * T ** 2
    Om = 124.7746 - 1.56375588 * k + 0.0020672 * T ** 2
    corr = (-0.40614 * math.sin(rad(Mp)) + 0.17302 * E * math.sin(rad(M)) + 0.01614 * math.sin(rad(2 * Mp))
            + 0.01043 * math.sin(rad(2 * F)) + 0.00734 * E * math.sin(rad(Mp - M))
            - 0.00515 * E * math.sin(rad(Mp + M)) + 0.00209 * E * E * math.sin(rad(2 * M))
            - 0.00111 * math.sin(rad(Mp - 2 * F)) - 0.00057 * math.sin(rad(Mp + 2 * F))
            + 0.00056 * E * math.sin(rad(2 * Mp + M)) - 0.00042 * math.sin(rad(3 * Mp))
            + 0.00042 * E * math.sin(rad(M + 2 * F)) + 0.00038 * E * math.sin(rad(M - 2 * F))
            - 0.00024 * E * math.sin(rad(2 * Mp - M)) - 0.00017 * math.sin(rad(Om)))
    return jde + corr


def jd_to_datetime_utc(jde):
    jd = jde - 69.0 / 86400  # TD to UT, delta-T about 69 s
    unix = (jd - 2440587.5) * 86400
    return datetime.fromtimestamp(unix, tz=timezone.utc)


MONTH_NAMES = ["", "Duruthu", "Navam", "Medin", "Bak", "Vesak", "Poson", "Esala", "Nikini", "Binara", "Vap", "Il", "Unduvap"]


def poya_days():
    rows = []
    k0 = math.floor((START.year + (START.timetuple().tm_yday / 365.25) - 2000) * 12.3685) - 2
    for k in range(k0, k0 + 45):
        dt = jd_to_datetime_utc(full_moon_jde(k + 0.5)) + timedelta(hours=5, minutes=30)
        d = dt.date()
        if START <= d <= END:
            rows.append((d, f"{MONTH_NAMES[d.month]} Poya", "poya"))
    return rows


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


def public_days():
    rows = []
    for y in (2024, 2025, 2026):
        fixed = [(1, 14, "Tamil Thai Pongal Day"), (2, 4, "Independence Day"), (4, 13, "Day before Sinhala and Tamil New Year"),
                 (4, 14, "Sinhala and Tamil New Year"), (5, 1, "May Day"), (12, 25, "Christmas Day")]
        for m, d, name in fixed:
            rows.append((date(y, m, d), name, "public"))
        rows.append((easter(y) - timedelta(days=2), "Good Friday", "public"))
    movable = [  # approximate, entered from memory
        (date(2024, 10, 31), "Deepavali"), (date(2025, 2, 26), "Maha Shivaratri"),
        (date(2025, 3, 31), "Eid al-Fitr"), (date(2025, 6, 7), "Eid al-Adha"), (date(2025, 9, 5), "Milad-un-Nabi"),
        (date(2025, 10, 20), "Deepavali"), (date(2026, 2, 15), "Maha Shivaratri"), (date(2026, 3, 21), "Eid al-Fitr"),
        (date(2026, 5, 28), "Eid al-Adha"), (date(2026, 8, 26), "Milad-un-Nabi"), (date(2026, 11, 8), "Deepavali"),
    ]
    rows += [(d, n, "public") for d, n in movable]
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
    print(len(rows), "rows;", len(poya), "poya days; e.g.", [r[0].isoformat() for r in poya[:4]], "...", [r[0].isoformat() for r in poya if r[0].year == 2026][:12])
