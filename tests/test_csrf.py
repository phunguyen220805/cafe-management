import re
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import User
from app.services.auth_service import create_user


CSRF_TOKEN_PATTERN = re.compile(rb'name="csrf_token" value="([^"]+)"')


class CsrfTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = (Path(self.temp_dir.name) / "test.db").as_posix()
        self.app = create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": True,
                "SECRET_KEY": "test-secret-key",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            }
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            create_user("admin", "Admin@123", role=User.ADMIN_ROLE)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.temp_dir.cleanup()

    def _token(self, path):
        response = self.client.get(path)
        match = CSRF_TOKEN_PATTERN.search(response.data)
        self.assertIsNotNone(match, f"No CSRF token rendered at {path}")
        return match.group(1).decode()

    def test_missing_and_invalid_tokens_are_rejected(self):
        self.assertEqual(
            self.client.post(
                "/login", data={"username": "admin", "password": "Admin@123"}
            ).status_code,
            400,
        )

        login_token = self._token("/login")
        self.assertEqual(
            self.client.post(
                "/login",
                data={
                    "username": "admin",
                    "password": "Admin@123",
                    "csrf_token": login_token,
                },
            ).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(
                "/accounts/add",
                data={
                    "username": "missing-token",
                    "password": "Missing@123",
                    "role": "employee",
                },
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/logout", data={"csrf_token": "invalid-token"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/login",
                data={
                    "username": "admin",
                    "password": "Admin@123",
                    "csrf_token": "invalid-token",
                },
            ).status_code,
            400,
        )

    def test_valid_login_logout_and_account_post_use_csrf_token(self):
        login_token = self._token("/login")
        login_response = self.client.post(
            "/login",
            data={
                "username": "admin",
                "password": "Admin@123",
                "csrf_token": login_token,
            },
        )
        self.assertEqual(login_response.status_code, 302)

        account_token = self._token("/accounts")
        create_response = self.client.post(
            "/accounts/add",
            data={
                "username": "employee",
                "password": "Employee@123",
                "role": "employee",
                "csrf_token": account_token,
            },
        )
        self.assertEqual(create_response.status_code, 302)
        with self.app.app_context():
            self.assertIsNotNone(User.query.filter_by(username="employee").first())

        logout_token = self._token("/")
        logout_response = self.client.post(
            "/logout", data={"csrf_token": logout_token}, follow_redirects=True
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.request.path, "/login")

    def test_authenticated_get_routes_remain_available(self):
        login_token = self._token("/login")
        self.client.post(
            "/login",
            data={
                "username": "admin",
                "password": "Admin@123",
                "csrf_token": login_token,
            },
        )
        for path in ("/", "/accounts"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)


if __name__ == "__main__":
    unittest.main()
