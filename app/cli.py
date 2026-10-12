import click
from flask.cli import AppGroup

group = AppGroup("smartrest", help="SmartRestaurant admin commands.")


@group.command("seed")
@click.option("--reset", is_flag=True, help="Drop and recreate all tables first (refused in production).")
def seed_cmd(reset):
    """Seed outlet, users, settings, suppliers, ingredients, menu and recipes."""
    from app.seed.seeder import seed_base

    result = seed_base(reset=reset)
    for username, password in result["passwords"].items():
        click.echo(f"created user {username}")
    if result["passwords"]:
        import os
        click.echo("Passwords: SEED_PASSWORD_<USERNAME> from .env where set (e.g. SEED_PASSWORD_ADMIN), otherwise SEED_PASSWORD")
        # only a generated shared password is ever printed, never one taken from the environment
        generated = None if os.environ.get("SEED_PASSWORD") else next(
            (p for u, p in result["passwords"].items() if not os.environ.get(f"SEED_PASSWORD_{u.upper()}")), None)
        if generated:
            click.echo(f"Generated password for the accounts without their own (shown once): {generated}")
    click.echo("seed complete")


@group.command("generate-data")
@click.option("--start", default="2024-09-01", show_default=True)
@click.option("--end", default=None, help="Last day of history (default: yesterday).")
@click.option("--seed", default=42, show_default=True)
def generate_cmd(start, end, seed):
    """Generate the labelled synthetic history and load it through the import services."""
    from datetime import date

    from app.seed.generate import generate

    result = generate(1, date.fromisoformat(start), date.fromisoformat(end) if end else None, seed)
    for k, v in result.items():
        click.echo(f"{k}: {v}")


@group.command("train")
@click.option("--activate", is_flag=True, help="Make the new version active.")
def train_cmd(activate):
    """Train Random Forest, XGBoost and baselines; compare on the hold-out; save the winner."""
    from flask import current_app

    from app.services import forecasting_service as fs

    r = fs.train_model(1, current_app.config["MODEL_DIR"], activate=activate)
    click.echo(f"version {r['version_label']}  winner: {r['algorithm']}  beats baseline: {r['beats_baseline']}")
    click.echo(r["selection_reason"])
    click.echo(f"hold-out {r['holdout']['start']} .. {r['holdout']['end']}")
    click.echo(f"{'model':16} {'MAE':>7} {'RMSE':>7} {'MAPE%':>7} {'WAPE%':>7} {'R2':>7} {'bias':>7}")
    for m in r["comparison"]:
        click.echo(f"{m['model']:16} {m['mae']:7.2f} {m['rmse']:7.2f} {m['mape']:7.2f} {m['wape']:7.2f} "
                   f"{m['r2']:7.3f} {m['bias']:7.2f}")
    if r["oracle_mae"] is not None:
        click.echo(f"oracle MAE (noise floor of the synthetic data): {r['oracle_mae']:.2f}")


@group.command("evaluate")
@click.option("--folds", default=6, show_default=True, help="Number of consecutive test windows.")
@click.option("--fold-days", default=28, show_default=True, help="Length of each test window in days.")
@click.option("--json", "json_path", default=None, help="Also write the full result to this JSON file.")
def evaluate_cmd(folds, fold_days, json_path):
    """Cross-validation, feature ablation and segment errors. Read-only: no model is stored or activated."""
    import json

    from app.services import forecasting_service as fs

    r = fs.run_experiments(1, n_folds=folds, fold_days=fold_days)
    click.echo(f"data to {r['data_end']}; {r['n_folds']} folds of {r['fold_days']} days (synthetic demo data)")
    click.echo("\nfolds")
    for f in r["folds"]:
        floor = f" floor {f['noise_floor_mae']:.2f}" if f.get("noise_floor_mae") is not None else ""
        maes = "  ".join(f"{a} {m['mae']:.2f}" for a, m in f["metrics"].items())
        click.echo(f"  {f['test_start']}..{f['test_end']}  {maes}  winner {f['winner']}{floor}")
    click.echo(f"\n{'cross-validation':16} {'MAE':>7} {'+/-':>6} {'WAPE%':>7} {'+/-':>6} {'beats naive':>12} {'won':>4}")
    for a, s in r["cv"].items():
        click.echo(f"{a:16} {s['mae_mean']:7.2f} {s['mae_std']:6.2f} {s['wape_mean']:7.2f} {s['wape_std']:6.2f} "
                   f"{s['folds_beating_naive']:>7}/{r['n_folds']:<4} {s['folds_won']:>4}")
    click.echo(f"\nablation ({r['algorithm_for_ablation']})      CV MAE    +/-   hold-out MAE  hold-out WAPE%")
    for a in r["ablation"]:
        click.echo(f"  {a['feature_set']:26} {a['cv']['mae_mean']:7.2f} {a['cv']['mae_std']:6.2f} "
                   f"{a['holdout']['mae']:13.2f} {a['holdout']['wape']:14.2f}")
    rows = r["segment_rows"]
    click.echo(f"\nsegment MAE (pooled CV test rows; {rows['total']} rows)")
    click.echo(f"  {'feature set':26} " + "  ".join(f"{s} ({rows[s]}): with / without" for s in rows if s != "total"))
    for a in r["ablation"]:
        seg = a["segments"]
        click.echo(f"  {a['feature_set']:26} " + "  ".join(
            f"{seg[s]['with']['mae']:6.2f} / {seg[s]['without']['mae']:6.2f}".rjust(len(f"{s} ({rows[s]}): with / without"))
            for s in seg))
    if json_path:
        with open(json_path, "w") as fh:
            json.dump(r, fh, indent=1)
        click.echo(f"\nfull result written to {json_path}")


@group.command("activate")
@click.argument("version_label")
def activate_cmd(version_label):
    from app.services import forecasting_service as fs

    mv = fs.activate_model(1, version_label)
    click.echo(f"active model: {mv.version_label} ({mv.algorithm})")


@group.command("forecast")
@click.option("--as-of", "as_of", default=None, help="Forecast start date (default: today).")
@click.option("--from", "from_", default=None, help="Backfill start date.")
@click.option("--to", "to_", default=None, help="Backfill end date.")
def forecast_cmd(as_of, from_, to_):
    """Run the 7-day forecast, or with --from/--to a single-day backfill per past date."""
    from datetime import date

    from app.services import forecasting_service as fs

    if from_ or to_:
        if not (from_ and to_):
            raise click.UsageError("--from and --to must be used together")
        click.echo(fs.backfill(1, date.fromisoformat(from_), date.fromisoformat(to_)))
        return
    r = fs.run_forecast(1, date.fromisoformat(as_of) if as_of else None, trigger="cli")
    click.echo(r)


@group.command("forecast-daily")
def forecast_daily_cmd():
    """The scheduled 7-day forecast: runs once per Asia/Colombo day, skips when today's forecast already exists."""
    from app.services import forecasting_service as fs

    r = fs.run_daily_forecast(1)
    click.echo(r)
    if r["action"] in ("not_run", "gave_up") or r.get("status") in ("failed", "skipped"):
        raise SystemExit(1)   # a failed timer run shows up in `systemctl status smartrest-forecast`


@group.command("demo-reset")
@click.pass_context
def demo_reset_cmd(ctx):
    """Reset to the ready-to-demo state: seed, synthetic history, train+activate, backfill, forecast, alerts."""
    from datetime import timedelta

    from flask import current_app

    from app.seed.generate import generate
    from app.seed.seeder import seed_base
    from app.services import forecasting_service as fs
    from app.utils.dates import today

    click.echo("seeding ...")
    result = seed_base(reset=True)
    click.echo("generating synthetic history ...")
    click.echo(generate(1))
    click.echo("training ...")
    r = fs.train_model(1, current_app.config["MODEL_DIR"], activate=True)
    click.echo(f"  {r['version_label']}: {r['algorithm']} (beats baseline: {r['beats_baseline']})")
    click.echo("backfilling the last 56 days ...")
    click.echo(fs.backfill(1, today() - timedelta(days=56), today() - timedelta(days=1)))
    click.echo(fs.run_forecast(1, trigger="cli"))
    try:
        from app.services import alert_service

        click.echo(alert_service.evaluate(1))
    except ImportError:
        pass
    if result["passwords"]:
        click.echo("users created (password = SEED_PASSWORD_<USERNAME> or SEED_PASSWORD from .env, or the generated one)")


@group.command("create-user")
@click.option("--username", prompt=True)
@click.option("--full-name", prompt=True)
@click.option("--role", type=click.Choice(["admin", "kitchen", "inventory"]), prompt=True)
@click.password_option()
def create_user_cmd(username, full_name, role, password):
    from app.services import auth_service

    auth_service.create_user(1, full_name, username, role, password)
    click.echo("user created")


@group.command("set-setting")
@click.argument("key")
@click.argument("value")
def set_setting_cmd(key, value):
    from app.services import settings

    settings.set_value(1, key, value)
    click.echo(f"{key} = {value}")


def register_cli(app):
    app.cli.add_command(group)


@group.command("check-stock")
def check_stock_cmd():
    """Check that stored stock agrees with the movement history (I16). Exit code 1 if it does not."""
    from app.services import inventory_service as inv

    r = inv.consistency_check(1)
    click.echo(f"checked {r['ingredients_checked']} ingredients and {r['batches_checked']} batches on {r['checked_on']}")
    for m in r["mismatches"]:
        click.echo(f"MISMATCH {m['ingredient']}: movements {m['movements']} vs batches {m['batches']} (difference {m['difference']})")
    for b in r["batches_over_received"]:
        click.echo(f"OVER-RECEIVED batch {b['batch_id']} {b['ingredient']}: {b['qty_remaining']} left of {b['qty_received']}")
    for b in r["expired_with_stock"]:
        click.echo(f"expired stock: {b['ingredient']} batch {b['batch_no']} {b['qty_remaining']} {b['unit']} (record it as wastage)")
    click.echo("consistent" if r["consistent"] else "NOT consistent")
    raise SystemExit(0 if r["consistent"] else 1)
