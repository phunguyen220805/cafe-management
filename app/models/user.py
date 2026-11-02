from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    role = db.Column(db.String(20), nullable=False, default="employee", server_default="employee")
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")

    ADMIN_ROLE = "admin"
    EMPLOYEE_ROLE = "employee"
    ROLES = (ADMIN_ROLE, EMPLOYEE_ROLE)

    def is_admin(self):
        return self.role == self.ADMIN_ROLE

    def set_password(self, password):
        if not isinstance(password, str) or "@" not in password:
            raise ValueError("Password must contain the @ character.")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)