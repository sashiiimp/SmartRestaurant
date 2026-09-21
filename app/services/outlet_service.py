from app.extensions import db
from app.models import Outlet
from app.services import audit
from app.services.errors import NotFoundError
from app.services.validation import Fields


def ensure_outlet(name: str = "SmartRestaurant Demo (Colombo)") -> Outlet:
    outlet = db.session.get(Outlet, 1)
    if outlet is None:
        outlet = Outlet(id=1, name=name, address="Colombo, Sri Lanka", contact="", opening_days="Mon-Sun",
                        opening_hours="10:00-22:00", timezone="Asia/Colombo")
        db.session.add(outlet)
        db.session.commit()
    return outlet


def reset_database() -> None:
    """Drop and recreate every table (demo reset). The CLI refuses this in production."""
    db.drop_all()
    db.create_all()


# ---- restaurant information (A6) --------------------------------------------------------------------------
def restaurant_dict(o: Outlet) -> dict:
    return {"name": o.name, "address": o.address, "contact": o.contact, "opening_days": o.opening_days,
            "opening_hours": o.opening_hours, "timezone": o.timezone}


def get_restaurant(outlet_id: int) -> dict:
    o = db.session.get(Outlet, outlet_id)
    if o is None:
        raise NotFoundError("Restaurant not found.")
    return restaurant_dict(o)


def update_restaurant(outlet_id: int, data: dict, actor_id: int | None = None) -> dict:
    """A6: basic restaurant information. The time zone is fixed (business dates are Asia/Colombo) and cannot be edited."""
    o = db.session.get(Outlet, outlet_id)
    if o is None:
        raise NotFoundError("Restaurant not found.")
    keys = ("name", "address", "contact", "opening_days", "opening_hours")
    merged = {k: data[k] if k in data else getattr(o, k) for k in keys}
    f = Fields(merged)
    f.text("name", max_len=120)
    f.text("address", required=False, max_len=255)
    f.text("contact", required=False, max_len=120)
    f.text("opening_days", required=False, max_len=60)
    f.text("opening_hours", required=False, max_len=60)
    v = f.check()
    for k in keys:
        setattr(o, k, v[k])
    audit.record(outlet_id, actor_id, "restaurant.update", "outlet", o.id, {"changed": sorted(k for k in keys if k in data)})
    db.session.commit()
    return restaurant_dict(o)
