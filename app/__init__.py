import os
import secrets

import click
from flask import Flask

from app.extensions import db, login_manager


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
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from app.models import Category, MenuItem, Order, OrderItem, Table, User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None
        return db.session.get(User, user_id)

    from app.routes.main_routes import main_bp
    from app.routes.auth_routes import auth_bp
    from app.routes.menu_routes import menu_bp
    from app.routes.order_routes import order_bp
    from app.routes.table_routes import table_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(table_bp)
    app.register_blueprint(order_bp)

    @app.cli.command("init-db")
    def init_db():
        """Create any database tables that are missing."""
        db.create_all()
        click.echo("Database tables are ready.")

    @app.cli.command("seed-admin")
    @click.option("--username", default="admin", show_default=True)
    def seed_admin(username):
        """Create the initial admin account, prompting for its password."""
        from app.services.auth_service import create_user

        db.create_all()
        password = click.prompt(
            "Admin password", hide_input=True, confirmation_prompt=True
        )
        try:
            create_user(username, password)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        click.echo("Admin account created.")

    return app