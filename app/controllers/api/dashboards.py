from datetime import timedelta

from flask_login import current_user

from app.controllers.api import bp
from app.services import dashboard_service as dash
from app.utils.dates import today
from flask import request

from app.utils.responses import csv_response, date_arg, int_arg, ok
from app.utils.security import current_outlet_id, roles_required


@bp.route("/dashboards/kitchen")
@roles_required("kitchen", "admin")
def kitchen_dashboard():
    return ok(dash.kitchen_dashboard(current_outlet_id(), date_arg("date", today()), current_user.role))


@bp.route("/dashboards/inventory")
@roles_required("inventory", "admin")
def inventory_dashboard():
    return ok(dash.inventory_dashboard(current_outlet_id(), current_user.role))


@bp.route("/dashboards/admin")
@roles_required("admin")
def admin_dashboard():
    return ok(dash.admin_dashboard(current_outlet_id(), int_arg("range", 7)))


@bp.route("/reports/sales")
@roles_required("admin")
def report_sales():
    end = date_arg("to", today() - timedelta(days=1))
    out = dash.sales_report(current_outlet_id(), date_arg("from", end - timedelta(days=29)), end,
                            request.args.get("group_by", "day"), int_arg("item_id"))
    if request.args.get("format") == "csv":
        return csv_response(f"sales_{out['from']}_{out['to']}.csv", ["period", "portions_sold", "revenue_lkr"],
                            [[r["period"], r["quantity"], f"{r['revenue']:.2f}"] for r in out["rows"]])
    return ok(out)


@bp.route("/reports/waste")
@roles_required("admin")
def report_waste():
    end = date_arg("to", today() - timedelta(days=1))
    out = dash.waste_report(current_outlet_id(), date_arg("from", end - timedelta(days=29)), end,
                            request.args.get("group_by", "day"))
    if request.args.get("format") == "csv":
        rows = [["food", r["period"], r["quantity"], f"{r['value']:.2f}"] for r in out["food"]["rows"]]
        rows += [["ingredient", r["period"], r["quantity"], f"{r['value']:.2f}"] for r in out["ingredient"]["rows"]]
        return csv_response(f"waste_{out['from']}_{out['to']}.csv", ["type", "period", "quantity", "value_lkr"], rows)
    return ok(out)
