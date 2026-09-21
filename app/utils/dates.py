"""Business dates are Asia/Colombo dates. Never call date.today() directly (CLAUDE.md)."""
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

COLOMBO = ZoneInfo("Asia/Colombo")


def today() -> date:
    fixed = os.environ.get("SMARTREST_TODAY")
    if fixed:
        return date.fromisoformat(fixed)
    return datetime.now(COLOMBO).date()


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def daterange(start: date, end: date):
    """Inclusive range of dates."""
    for i in range((end - start).days + 1):
        yield start + timedelta(days=i)
