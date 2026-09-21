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
        click.echo("Password for the new users is the SEED_PASSWORD value from .env"
                   if __import__("os").environ.get("SEED_PASSWORD") else
                   f"Generated password (shown once): {next(iter(result['passwords'].values()))}")
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
