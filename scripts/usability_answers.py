"""Print the observer's answer key for the usability tasks (docs/usability/KIT.md) for today's demo data.

Read-only: it only calls service read functions. Run it right after `flask smartrest demo-reset`, before each
session, because the forecast and therefore the expected answers change from day to day.

Usage (from the project root): .venv/bin/python scripts/usability_answers.py
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.services import forecasting_service as fs  # noqa: E402
from app.services import recommendation_service as rec  # noqa: E402
from app.utils.dates import today  # noqa: E402


def num(x):
    return f"{float(x):g}"


def main():
    app = create_app()
    with app.app_context():
        d = today()
        print(f"Answer key for {d.isoformat()} (demo data). Accept any answer that matches the page.\n")

        plan = rec.get_prep_plan(1, d)
        by_name = {r["name"]: r for r in plan["items"]}
        cb = by_name["Chicken Burger"]
        print("KITCHEN")
        print(f"  K1 Chicken Burger: prepare {cb['recommended_qty']} = forecast {num(cb['forecast_qty'])} "
              f"+ {num(cb['buffer_pct'])}% buffer, rounded up to whole batches of {cb['batch_size']}"
              f"{', pre-orders ' + str(cb['preorder_qty']) if cb['preorder_qty'] else ''}.")
        vb = by_name["Veggie Burger"]
        print(f"  K2 Veggie Burger: recommended {vb['recommended_qty']}; the participant overrides to 24 with any reason. "
              f"Status becomes Overridden.")
        print("  K3 Chicken Burger: 'Prepared so far' goes from 0 to 24.")
        req = rec.get_requirements(1, d)
        short = [r for r in req["ingredients"] if float(r.get("short_by") or 0) > 0]
        print("  K4 Short today: " + ("; ".join(f"{r['name']} by {num(r['short_by'])} {r['unit']} "
                                              f"(needs {num(r['required'])}, has {num(r['usable_stock'])})" for r in short)
                                    or "nothing is short today"))
        print("  K5 Waste: Fried Chicken 2 pc, quantity 3, reason overproduction, appears in today's waste list.")
        print("  K6 Chicken Burger: after K3 it shows 'In progress'; Mark done -> badge 'Done' and a Reopen button. If the "
              "participant has not accepted a plan for Chicken Burger, Start and Mark done are not shown: accepting first "
              "is the expected path (note it if the participant is confused). A warning that 24 is below the plan is correct.")
        print(f"  K7 Other food use: Chicken Burger, Staff meal, 2. Unaccounted shows '-' until served is recorded for "
              f"today; once it is, unaccounted = prepared - served - waste - 2.")

        print("\nINVENTORY")
        sugg = rec.get_reorder_suggestions(1)
        print("  I1 Reorder: " + ("; ".join(f"{s['name']} {num(s['suggested_qty'])} {s['unit']} from {s['supplier']}"
                                           for s in sugg) or "nothing to reorder"))
        print("  I2 Purchase orders: one draft per supplier for the suggested items; Reorder then shows nothing to order "
              "(drafts count as on order).")
        print("  I3 Stock-in: Chicken 80 kg with an expiry date about a week ahead appears as a stock-in movement. Either path "
              "is correct: Record stock > Stock in, or Receive stock on the Chicken purchase order created in I2.")
        print("  I4 Wastage: the expired chicken batch (CHK-EXPIRED, 5 kg) is written off with reason Expired.")
        print("  I5 Alerts: the alert that Chicken will run short TODAY is gone (alerts refresh at most once a minute, or "
              "press Run alert check). An alert for a later date may remain: that is correct, not a failure. A waste "
              "alert about Chicken KOTTU is a different item; if the participant takes it for the chicken stock alert, "
              "note it as a problem.")
        print("\nADMINISTRATOR")
        mv = fs.model_version_dict(fs.get_active_model(1))
        comp = {c["model"]: c for c in mv["metrics"]["comparison"]}
        best = comp[mv["algorithm"]]
        naive = comp["naive_lag7"]
        print(f"  A1 Active model {mv['version_label']} ({mv['algorithm']}): MAE {num(round(best['mae'], 2))} "
              f"vs naive {num(round(naive['mae'], 2))}, about {round(100 * (1 - best['mae'] / naive['mae']))}% lower.")
        print("  A2 New user: username kitchen2, role Food Production Manager (kitchen), appears in the users list.")
        end = d - timedelta(days=1)
        acc = fs.accuracy(1, end - timedelta(days=27), end, 1)["overall"]
        print(f"  A3 Forecast accuracy, Chicken Burger, default period {end - timedelta(days=27)} to {end}: "
              f"MAE {num(round(acc['mae'], 2))}, WAPE {num(round(acc['wape'], 1))}%.")
        at12 = rec.compute_recommended(cb["forecast_qty"], 12, cb["preorder_qty"], cb["batch_size"])
        print(f"  A4 Settings: safety buffer changed from 10 to 12 %; the kitchen prep plan then shows +12%. Chicken "
              f"Burger becomes {at12} (was {cb['recommended_qty']}); recommendations are rounded up to whole batches, so "
              f"some stay the same, which is correct.")


if __name__ == "__main__":
    main()
