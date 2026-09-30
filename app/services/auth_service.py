from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User


def create_user(username, password):
    username = username.strip() if isinstance(username, str) else ""
    if not username:
        raise ValueError("Username is required.")
    if User.query.filter_by(username=username).first() is not None:
        raise ValueError("Username already exists.")

    user = User(username=username)
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
    if user is not None and user.check_password(password):
        return user
    return None