from app.extensions import db
from app.models import Outlet


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
