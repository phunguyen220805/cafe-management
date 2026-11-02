import os
import secrets

import click
from flask import Flask

from app.extensions import csrf, db, login_manager


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///cafe.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config is not None:
        app.config.update(test_config)

    secret_key = app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY")
    if not secret_key:
        if os.environ.get("APP_ENV") == "development":
            secret_key = secrets.token_hex(32)
        else:
            raise RuntimeError("Set SECRET_KEY in the environment before starting the app.")
    app.config["SECRET_KEY"] = secret_key

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from app.models import (
        Category,
        Ingredient,
        MenuItem,
        Order,
        OrderItem,
        Payment,
        StockTransaction,
        Table,
        User,
    )

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None
        user = db.session.get(User, user_id)
        return user if user is not None and user.is_active else None

    from app.routes.main_routes import main_bp
    from app.routes.auth_routes import auth_bp
    from app.routes.account_routes import account_bp
    from app.routes.inventory_routes import inventory_bp
    from app.routes.menu_routes import menu_bp
    from app.routes.order_routes import order_bp
    from app.routes.payment_routes import payment_bp
    from app.routes.table_routes import table_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(table_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(payment_bp)

    @app.cli.command("init-db")
    def init_db():
        """Create any database tables that are missing."""
        from app.services.auth_service import migrate_user_table

        db.create_all()
        migrate_user_table()
        click.echo("Database tables are ready.")

    @app.cli.command("migrate-user-roles")
    def migrate_user_roles():
        """Add account role and active status columns without replacing data."""
        from app.services.auth_service import migrate_user_table

        db.create_all()
        migrate_user_table()
        click.echo("User role columns are ready.")

    @app.cli.command("seed-admin")
    @click.option("--username", default="admin", show_default=True)
    def seed_admin(username):
        """Create the initial admin account, prompting for its password."""
        from app.services.auth_service import create_user, migrate_user_table

        db.create_all()
        migrate_user_table()
        password = click.prompt(
            "Admin password", hide_input=True, confirmation_prompt=True
        )
        try:
            create_user(username, password, role="admin")
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        click.echo("Admin account created.")

    @app.cli.command("promote-admin")
    @click.option("--username", prompt=True)
    def promote_admin(username):
        """Promote an existing account after verifying its current password."""
        from app.services.auth_service import migrate_user_table, update_user_role

        db.create_all()
        migrate_user_table()
        user = User.query.filter_by(username=username.strip()).first()
        if user is None:
            raise click.ClickException("Username not found.")
        password = click.prompt("Current account password", hide_input=True)
        if not user.check_password(password):
            raise click.ClickException("Password is incorrect.")
        if not click.confirm(f"Promote '{user.username}' to admin?", default=False):
            click.echo("No changes made.")
            return
        update_user_role(user, User.ADMIN_ROLE)
        click.echo("Admin role granted.")

    return app