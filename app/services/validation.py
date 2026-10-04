"""Small field validator used by every service (C4, NFR8). Collects all errors, then raises once."""
from datetime import date
from decimal import Decimal, InvalidOperation

from app.services.errors import ValidationError
from app.utils.dates import today

# Upper limits (NFR8). Each is far above any real figure for one outlet and below its column's range, so a typo or a
# pasted number is refused with a message instead of distorting the forecast and the recommendations built on it, or
# overflowing a column (a 500 on MariaDB in strict mode).
MAX_INT = 2_147_483_647           # INT columns (ids, counts)
MAX_PORTIONS = 10_000             # portions of one item in one entry (prepared, served, waste, pre-orders, orders)
MAX_STOCK_QTY = 1_000_000         # base units (kg, l, pcs) in one entry; stock columns are DECIMAL(12,3)
MAX_MONEY = 10_000_000            # LKR; price and cost columns are DECIMAL(12,2)
STOCK_PLACES, MONEY_PLACES = 3, 2  # more decimals would be rounded away silently by the column


class Fields:
    def __init__(self, data: dict | None):
        self.data = data or {}
        self.errors: dict[str, str] = {}
        self.values: dict = {}

    def _raw(self, name):
        v = self.data.get(name)
        if isinstance(v, str):
            v = v.strip()
        return None if v == "" else v

    def _missing(self, name, required):
        if required:
            self.errors[name] = "is required"
        return None

    def text(self, name, required=True, max_len=255, default=None):
        v = self._raw(name)
        if v is None:
            if default is not None:
                self.values[name] = default
                return default
            self.values[name] = None
            return self._missing(name, required)
        if isinstance(v, (bool, dict, list)):
            self.errors[name] = "must be text"
            return None
        v = str(v)
        if len(v) > max_len:
            self.errors[name] = f"must be at most {max_len} characters"
            return None
        self.values[name] = v
        return v

    def decimal(self, name, required=True, min=None, gt=None, max=None, default=None, places=None):
        v = self._raw(name)
        if v is None:
            if default is not None:
                self.values[name] = Decimal(str(default))
                return self.values[name]
            self.values[name] = None
            return self._missing(name, required)
        if isinstance(v, bool):
            self.errors[name] = "must be a number"
            return None
        try:
            d = Decimal(str(v))
            if not d.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            self.errors[name] = "must be a number"
            return None
        if gt is not None and not d > Decimal(str(gt)):
            self.errors[name] = f"must be greater than {gt}"
            return None
        if min is not None and d < Decimal(str(min)):
            self.errors[name] = f"must be at least {min}"
            return None
        if max is not None and d > Decimal(str(max)):
            self.errors[name] = f"must be at most {max:,}"
            return None
        if places is not None and d.as_tuple().exponent < -places:
            self.errors[name] = f"must have at most {places} decimal places"
            return None
        self.values[name] = d
        return d

    def integer(self, name, required=True, min=None, gt=None, max=MAX_INT, default=None):
        r = self.decimal(name, required=required, min=min, gt=gt, max=max, default=default)
        if r is None:
            return None
        if r != r.to_integral_value():
            self.errors[name] = "must be a whole number"
            self.values[name] = None
            return None
        self.values[name] = int(r)
        return int(r)

    def portions(self, name, required=True, min=None, gt=None, default=None):
        """A count of portions of one item in one entry."""
        return self.integer(name, required=required, min=min, gt=gt, max=MAX_PORTIONS, default=default)

    def stock_qty(self, name, required=True, min=None, gt=None, default=None):
        """An ingredient quantity in its base unit."""
        return self.decimal(name, required=required, min=min, gt=gt, max=MAX_STOCK_QTY, default=default,
                            places=STOCK_PLACES)

    def money(self, name, required=True, default=None):
        """A price or unit cost in LKR."""
        return self.decimal(name, required=required, min=0, max=MAX_MONEY, default=default, places=MONEY_PLACES)

    def date(self, name, required=True, not_future=False, default=None):
        v = self._raw(name)
        if v is None:
            if default is not None:
                self.values[name] = default
                return default
            self.values[name] = None
            return self._missing(name, required)
        try:
            d = v if isinstance(v, date) else date.fromisoformat(str(v))
        except ValueError:
            self.errors[name] = "must be a date (YYYY-MM-DD)"
            return None
        if not_future and d > today():
            self.errors[name] = "cannot be in the future"
            return None
        self.values[name] = d
        return d

    def choice(self, name, options, required=True, default=None):
        v = self._raw(name)
        if v is None:
            if default is not None:
                self.values[name] = default
                return default
            self.values[name] = None
            return self._missing(name, required)
        if v not in options:
            self.errors[name] = "must be one of: " + ", ".join(options)
            return None
        self.values[name] = v
        return v

    def boolean(self, name, default=None):
        v = self.data.get(name, default)
        if v is None:
            return None
        if not isinstance(v, bool):
            self.errors[name] = "must be true or false"
            return None
        self.values[name] = v
        return v

    def error(self, name, message):
        self.errors[name] = message

    def check(self):
        if self.errors:
            raise ValidationError("Please fix the highlighted fields.", dict(self.errors))
        return self.values
