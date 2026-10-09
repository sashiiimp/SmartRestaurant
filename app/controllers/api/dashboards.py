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


@bp.route("/reports/food-usage")
@roles_required("admin")
def report_food_usage():
    end = date_arg("to", today() - timedelta(days=1))
    out = dash.food_usage_report(current_outlet_id(), date_arg("from", end - timedelta(days=29)), end)
    if request.args.get("format") == "csv":
        return csv_response(f"food_usage_{out['from']}_{out['to']}.csv",
                            ["item", "staff_meal", "complimentary", "sample", "other", "total"],
                            [[r["item"], r["staff_meal"], r["complimentary"], r["sample"], r["other"], r["total"]]
                             for r in out["by_item"]])
    return ok(out)


@bp.route("/reports/stock-levels")
@roles_required("admin")
def report_stock_levels():
    out = dash.stock_levels_report(current_outlet_id())
    if request.args.get("format") == "csv":
        rows = [[r["name"], r["unit"], r["usable"], r["on_hand"], r["min_stock"], r["reorder_level"], r["status"],
                 r["last_movement_date"] or ""] for r in out["rows"]]
        return csv_response(f"stock_levels_{out['as_of']}.csv",
                            ["ingredient", "unit", "usable", "on_hand", "min_stock", "reorder_level", "status", "last_movement"], rows)
    return ok(out)


@bp.route("/reports/inventory-trend")
@roles_required("admin")
def report_inventory_trend():
    end = date_arg("to", today())
    out = dash.inventory_trend(current_outlet_id(), int_arg("ingredient_id"), date_arg("from", end - timedelta(days=29)), end)
    if request.args.get("format") == "csv":
        rows = [[r["date"], r["stock_in"], r["stock_out"], r["wastage"], r["adjustment"], r["closing"]] for r in out["rows"]]
        return csv_response(f"stock_trend_{out['ingredient'].replace(' ', '_')}_{out['from']}_{out['to']}.csv",
                            ["date", "stock_in", "stock_out", "wastage", "adjustment", "closing_on_hand"], rows)
    return ok(out)


@bp.route("/reports/movements")
@roles_required("admin")
def report_movements():
    end = date_arg("to", today())
    csv = request.args.get("format") == "csv"
    out = dash.movement_report(current_outlet_id(), date_arg("from", end - timedelta(days=29)), end, int_arg("ingredient_id"),
                               request.args.get("type"), limit=None if csv else dash.MOVEMENT_LIMIT_ON_SCREEN)
    if csv:
        rows = [[r["date"], r["ingredient"], r["unit"], r["type"], r["quantity"], r["reason"] or "", r["note"] or "",
                 r["reference"] or ""] for r in out["rows"]]
        return csv_response(f"stock_movements_{out['from']}_{out['to']}.csv",
                            ["date", "ingredient", "unit", "type", "quantity", "reason", "note", "reference"], rows)
    return ok(out["rows"], {"total": out["total"], "shown": out["shown"], "from": out["from"], "to": out["to"]})


@bp.route("/reports/analytics")
@roles_required("admin")
def report_analytics():
    end = date_arg("to", today() - timedelta(days=1))
    return ok(dash.analytics(current_outlet_id(), date_arg("from", end - timedelta(days=89)), end))
