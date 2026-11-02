import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User
from app.services.auth_service import create_user


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.database_path.as_posix()}",
            }
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            create_user("admin", "Admin@123", role=User.ADMIN_ROLE)
            create_user("employee", "Employee@123")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.temp_dir.cleanup()

    def login(self, username, password):
        return self.client.post(
            "/login", data={"username": username, "password": password}
        )

    def test_only_admin_can_access_account_management(self):
        self.assertEqual(self.client.get("/accounts").status_code, 302)

        self.login("employee", "Employee@123")
        self.assertEqual(self.client.get("/accounts").status_code, 403)

        self.client.post("/logout")
        self.login("admin", "Admin@123")
        response = self.client.get("/accounts")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Quản lý tài khoản".encode(), response.data)

    def test_admin_can_create_employee_with_profile_without_changing_hash_policy(self):
        self.login("admin", "Admin@123")
        response = self.client.post(
            "/accounts/add",
            data={
                "username": "cashier",
                "password": "Cashier@123",
                "role": "employee",
                "full_name": "Nguyen Van Thu",
                "date_of_birth": "1995-04-12",
            },
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            user = User.query.filter_by(username="cashier").one()
            self.assertEqual(user.role, User.EMPLOYEE_ROLE)
            self.assertTrue(user.is_active)
            self.assertEqual(user.full_name, "Nguyen Van Thu")
            self.assertEqual(user.date_of_birth, date(1995, 4, 12))
            self.assertTrue(user.check_password("Cashier@123"))
            self.assertNotEqual(user.password_hash, "Cashier@123")

    def test_create_rejects_invalid_or_future_date_of_birth(self):
        self.login("admin", "Admin@123")
        for username, birth_date in (
            ("bad-date", "12/04/1995"),
            ("future-date", (date.today() + timedelta(days=1)).isoformat()),
        ):
            response = self.client.post(
                "/accounts/add",
                data={
                    "username": username,
                    "password": "Valid@123",
                    "role": "employee",
                    "date_of_birth": birth_date,
                },
            )
            self.assertEqual(response.status_code, 302)
            with self.app.app_context():
                self.assertIsNone(User.query.filter_by(username=username).first())

    def test_admin_can_edit_profile_and_role_without_changing_password(self):
        self.login("admin", "Admin@123")
        employee_id = self._user_id("employee")
        with self.app.app_context():
            password_hash = db.session.get(User, employee_id).password_hash

        response = self.client.post(
            f"/accounts/{employee_id}/edit",
            data={
                "full_name": "Tran Thi Mai",
                "date_of_birth": "1998-09-20",
                "role": "admin",
            },
        )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            employee = db.session.get(User, employee_id)
            self.assertEqual(employee.full_name, "Tran Thi Mai")
            self.assertEqual(employee.date_of_birth, date(1998, 9, 20))
            self.assertEqual(employee.role, User.ADMIN_ROLE)
            self.assertEqual(employee.password_hash, password_hash)
            self.assertTrue(employee.check_password("Employee@123"))

    def test_employee_cannot_use_management_post_routes(self):
        self.login("employee", "Employee@123")
        employee_id = self._user_id("employee")
        routes = (
            ("/accounts/add", {"username": "blocked", "password": "Blocked@123"}),
            (f"/accounts/{employee_id}/edit", {"role": "employee"}),
            (f"/accounts/{employee_id}/status", {"is_active": "0"}),
        )
        for route, data in routes:
            self.assertEqual(self.client.post(route, data=data).status_code, 403)

    def test_account_list_filters_and_empty_state(self):
        self.login("admin", "Admin@123")
        response = self.client.get("/accounts?q=does-not-exist")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Không tìm thấy tài khoản".encode(), response.data)

        response = self.client.get("/accounts?role=employee&status=active")
        self.assertEqual(response.status_code, 200)
        self.assertIn("employee".encode(), response.data)
        self.assertNotIn(b"accounts-badge-admin", response.data)

    def test_locking_account_blocks_login_and_can_be_reversed(self):
        self.login("admin", "Admin@123")
        employee_id = self._user_id("employee")
        response = self.client.post(
            f"/accounts/{employee_id}/status", data={"is_active": "0"}
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            employee = db.session.get(User, employee_id)
            self.assertFalse(employee.is_active)
            password_hash = employee.password_hash
            self.assertFalse(employee.check_password("Wrong@123"))
            self.assertEqual(employee.password_hash, password_hash)

        self.client.post("/logout")
        locked_response = self.login("employee", "Employee@123")
        self.assertEqual(locked_response.status_code, 200)
        self.assertIn("Tên đăng nhập hoặc mật khẩu không đúng.".encode(), locked_response.data)

        self.login("admin", "Admin@123")
        self.client.post(f"/accounts/{employee_id}/status", data={"is_active": "1"})
        self.client.post("/logout")
        response = self.login("employee", "Employee@123")
        self.assertEqual(response.status_code, 302)

    def test_cannot_lock_or_demote_last_admin_or_self(self):
        self.login("admin", "Admin@123")
        admin_id = self._user_id("admin")

        lock_response = self.client.post(
            f"/accounts/{admin_id}/status", data={"is_active": "0"}
        )
        role_response = self.client.post(
            f"/accounts/{admin_id}/role", data={"role": "employee"}
        )

        self.assertEqual(lock_response.status_code, 302)
        self.assertEqual(role_response.status_code, 302)
        with self.app.app_context():
            admin = db.session.get(User, admin_id)
            self.assertTrue(admin.is_active)
            self.assertEqual(admin.role, User.ADMIN_ROLE)

        with self.app.app_context():
            second_admin = User(username="second-admin", role=User.ADMIN_ROLE)
            second_admin.set_password("Second@123")
            db.session.add(second_admin)
            db.session.commit()
        self.assertEqual(
            self.client.post(
                f"/accounts/{admin_id}/role", data={"role": "employee"}
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertEqual(db.session.get(User, admin_id).role, User.ADMIN_ROLE)

    def test_role_and_status_changes_preserve_password_hash(self):
        self.login("admin", "Admin@123")
        employee_id = self._user_id("employee")
        with self.app.app_context():
            password_hash = db.session.get(User, employee_id).password_hash

        self.client.post(
            f"/accounts/{employee_id}/role", data={"role": "admin"}
        )
        self.client.post(
            f"/accounts/{employee_id}/status", data={"is_active": "0"}
        )

        with self.app.app_context():
            employee = db.session.get(User, employee_id)
            self.assertEqual(employee.password_hash, password_hash)
            self.assertTrue(employee.check_password("Employee@123"))

    def test_promote_admin_cli_verifies_password_and_confirmation(self):
        result = self.app.test_cli_runner().invoke(
            args=["promote-admin", "--username", "employee"],
            input="Employee@123\ny\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            employee = User.query.filter_by(username="employee").one()
            self.assertEqual(employee.role, User.ADMIN_ROLE)
            self.assertTrue(employee.check_password("Employee@123"))

    def _user_id(self, username):
        with self.app.app_context():
            return User.query.filter_by(username=username).one().id


class UserMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "legacy.db"
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE, password_hash VARCHAR(256) NOT NULL)"
            )
            connection.execute(
                "INSERT INTO user (username, password_hash) VALUES (?, ?)",
                ("legacy", generate_password_hash("Legacy@123")),
            )
            connection.commit()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.database_path.as_posix()}",
            }
        )

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp_dir.cleanup()

    def test_migration_adds_columns_idempotently_and_preserves_data(self):
        runner = self.app.test_cli_runner()
        first = runner.invoke(args=["migrate-user-roles"])
        second = runner.invoke(args=["migrate-user-roles"])

        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        with self.app.app_context():
            user = User.query.filter_by(username="legacy").one()
            self.assertEqual(user.role, User.EMPLOYEE_ROLE)
            self.assertTrue(user.is_active)
            self.assertTrue(user.check_password("Legacy@123"))
            self.assertEqual(user.id, 1)
            columns = {
                row[1]
                for row in db.session.execute(text("PRAGMA table_info(user)"))
            }
            self.assertTrue({"role", "is_active", "full_name", "date_of_birth"} <= columns)
            self.assertEqual(
                db.session.execute(text("SELECT COUNT(*) FROM user")).scalar_one(),
                1,
            )


if __name__ == "__main__":
    unittest.main()
