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
