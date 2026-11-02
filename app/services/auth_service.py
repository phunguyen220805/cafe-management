from functools import wraps
from datetime import date

from flask import abort, has_request_context
from flask_login import current_user, login_required
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User


def migrate_user_table():
    columns = {
        row[1] for row in db.session.execute(text("PRAGMA table_info(user)"))
    }
    statements = []
    if "role" not in columns:
        statements.append(
            "ALTER TABLE user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'employee'"
        )
    if "is_active" not in columns:
        statements.append(
            "ALTER TABLE user ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
        )
    if "full_name" not in columns:
        statements.append("ALTER TABLE user ADD COLUMN full_name VARCHAR(120)")
    if "date_of_birth" not in columns:
        statements.append("ALTER TABLE user ADD COLUMN date_of_birth DATE")
    for statement in statements:
        db.session.execute(text(statement))
    if statements:
        db.session.commit()


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not current_user.is_admin():
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def parse_date_of_birth(value):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        parsed_date = value
    else:
        try:
            parsed_date = date.fromisoformat(str(value).strip())
        except (TypeError, ValueError) as error:
            raise ValueError("Date of birth must use YYYY-MM-DD format.") from error
    if parsed_date > date.today():
        raise ValueError("Date of birth cannot be in the future.")
    return parsed_date


def normalize_full_name(full_name):
    if full_name is None:
        return None
    normalized = full_name.strip() if isinstance(full_name, str) else ""
    return normalized or None


def create_user(
    username,
    password,
    role=User.EMPLOYEE_ROLE,
    full_name=None,
    date_of_birth=None,
):
    username = username.strip() if isinstance(username, str) else ""
    if not username:
        raise ValueError("Username is required.")
    if role not in User.ROLES:
        raise ValueError("Invalid user role.")
    full_name = normalize_full_name(full_name)
    date_of_birth = parse_date_of_birth(date_of_birth)
    if User.query.filter_by(username=username).first() is not None:
        raise ValueError("Username already exists.")

    user = User(
        username=username,
        full_name=full_name,
        date_of_birth=date_of_birth,
        role=role,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("Username already exists.") from error
    return user


def authenticate_user(username, password):
    user = User.query.filter_by(username=username).first()
    if user is not None and user.is_active and user.check_password(password):
        return user
    return None


def count_admins():
    return User.query.filter_by(role=User.ADMIN_ROLE, is_active=True).count()


def update_user_role(user, role):
    if role not in User.ROLES:
        raise ValueError("Invalid user role.")
    if (
        has_request_context()
        and current_user.is_authenticated
        and user.id == current_user.id
        and role != User.ADMIN_ROLE
    ):
        raise ValueError("You cannot remove your own admin role.")
    if user.role == User.ADMIN_ROLE and role != User.ADMIN_ROLE and count_admins() <= 1:
        raise ValueError("Cannot remove the last active admin.")
    user.role = role
    db.session.commit()


def update_user_status(user, is_active):
    if (
        not is_active
        and has_request_context()
        and current_user.is_authenticated
        and user.id == current_user.id
    ):
        raise ValueError("You cannot lock your own account.")
    if not is_active and user.role == User.ADMIN_ROLE and count_admins() <= 1:
        raise ValueError("Cannot lock the last active admin.")
    user.is_active = is_active
    db.session.commit()


def update_user_profile(user, full_name, date_of_birth, role):
    if role not in User.ROLES:
        raise ValueError("Invalid user role.")
    if (
        has_request_context()
        and current_user.is_authenticated
        and user.id == current_user.id
        and role != User.ADMIN_ROLE
    ):
        raise ValueError("You cannot remove your own admin role.")
    if user.role == User.ADMIN_ROLE and role != User.ADMIN_ROLE and count_admins() <= 1:
        raise ValueError("Cannot remove the last active admin.")
    user.full_name = normalize_full_name(full_name)
    user.date_of_birth = parse_date_of_birth(date_of_birth)
    user.role = role
    db.session.commit()