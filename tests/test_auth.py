import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User
from app.services.auth_service import create_user


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = (Path(self.temp_dir.name) / "test.db").as_posix()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            }
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            create_user("barista", "Cafe@123")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.temp_dir.cleanup()

    def test_existing_home_route_is_preserved(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("HỆ THỐNG QUẢN LÝ QUÁN CAFE".encode(), response.data)

    def test_login_succeeds(self):
        response = self.client.post(
            "/login",
            data={"username": "barista", "password": "Cafe@123"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, "/")

    def test_login_fails_for_unknown_username(self):
        response = self.client.post(
            "/login",
            data={"username": "unknown", "password": "Cafe@123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Tên đăng nhập hoặc mật khẩu không đúng.".encode(), response.data)

    def test_login_fails_for_wrong_password(self):
        response = self.client.post(
            "/login",
            data={"username": "barista", "password": "Wrong@123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Tên đăng nhập hoặc mật khẩu không đúng.".encode(), response.data)

    def test_user_creation_rejects_password_without_at_sign(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                create_user("invalid", "Cafe123")
            self.assertIsNone(User.query.filter_by(username="invalid").first())

    def test_password_is_stored_as_a_hash(self):
        with self.app.app_context():
            user = User.query.filter_by(username="barista").one()
            self.assertNotEqual(user.password_hash, "Cafe@123")
            self.assertTrue(user.check_password("Cafe@123"))
            self.assertFalse(hasattr(user, "password"))

    def test_login_does_not_recheck_at_sign_policy(self):
        with self.app.app_context():
            legacy_user = User(
                username="legacy",
                password_hash=generate_password_hash("LegacyPassword"),
            )
            db.session.add(legacy_user)
            db.session.commit()

        response = self.client.post(
            "/login",
            data={"username": "legacy", "password": "LegacyPassword"},
            follow_redirects=True,
        )

        self.assertEqual(response.request.path, "/")

    def test_logout_clears_authenticated_session(self):
        self.client.post(
            "/login", data={"username": "barista", "password": "Cafe@123"}
        )
        response = self.client.post("/logout", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, "/login")
        with self.client.session_transaction() as session:
            self.assertNotIn("_user_id", session)

    def test_seed_admin_cli_creates_an_account(self):
        result = self.app.test_cli_runner().invoke(
            args=["seed-admin", "--username", "admin"],
            input="Admin@123\nAdmin@123\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            admin = User.query.filter_by(username="admin").one()
            self.assertTrue(admin.check_password("Admin@123"))


if __name__ == "__main__":
    unittest.main()