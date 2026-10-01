import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
login_manager = LoginManager()


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(connection, _connection_record):
	if isinstance(connection, sqlite3.Connection):
		cursor = connection.cursor()
		cursor.execute("PRAGMA foreign_keys=ON")
		cursor.close()