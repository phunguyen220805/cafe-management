import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import Table
from app.services.auth_service import create_user
from app.services import table_service


class TableTests(unittest.TestCase):
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

    def _login(self):
        return self.client.post(
            "/login", data={"username": "barista", "password": "Cafe@123"}
        )

    def test_tables_page_requires_authentication(self):
        response = self.client.get("/tables")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("/login?next="))

    def test_authenticated_user_can_open_tables_page(self):
        self._login()
        response = self.client.get("/tables")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Quản lý bàn".encode(), response.data)

    def test_create_table_succeeds(self):
        with self.app.app_context():
            table = table_service.create_table("Bàn 01", 4)
            self.assertEqual(table.name, "Bàn 01")
            self.assertEqual(table.capacity, 4)
            self.assertEqual(table.status, "available")
            self.assertEqual(Table.query.count(), 1)

    def test_empty_table_name_is_rejected(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                table_service.create_table("  ", 4)
            self.assertEqual(Table.query.count(), 0)

    def test_duplicate_table_name_is_rejected(self):
        with self.app.app_context():
            table_service.create_table("Bàn 01", 4)
            with self.assertRaises(ValueError):
                table_service.create_table("Bàn 01", 2)
            self.assertEqual(Table.query.count(), 1)

    def test_invalid_capacity_is_rejected(self):
        with self.app.app_context():
            for capacity in (0, -1, "abc", "2.5"):
                with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                    table_service.create_table("Bàn 01", capacity)
            self.assertEqual(Table.query.count(), 0)

    def test_invalid_status_is_rejected(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                table_service.create_table("Bàn 01", 4, status="cleaning")
            self.assertEqual(Table.query.count(), 0)

    def test_update_table(self):
        with self.app.app_context():
            table = table_service.create_table("Bàn 01", 4)
            updated = table_service.update_table(
                table.id,
                "Bàn cửa sổ",
                6,
                "reserved",
                description="Gần cửa sổ",
            )
            self.assertEqual(updated.name, "Bàn cửa sổ")
            self.assertEqual(updated.capacity, 6)
            self.assertEqual(updated.status, "reserved")
            self.assertEqual(updated.description, "Gần cửa sổ")

    def test_delete_table(self):
        with self.app.app_context():
            table = table_service.create_table("Bàn 01", 4)
            table_service.delete_table(table.id)
            self.assertEqual(Table.query.count(), 0)

    def test_search_tables_by_name(self):
        with self.app.app_context():
            table_service.create_table("Bàn cửa sổ", 4)
            table_service.create_table("Bàn sân vườn", 6)
            results = table_service.get_tables(search="cửa sổ")
            self.assertEqual([table.name for table in results], ["Bàn cửa sổ"])

    def test_filter_tables_by_status(self):
        with self.app.app_context():
            table_service.create_table("Bàn 01", 4, status="available")
            table_service.create_table("Bàn 02", 2, status="occupied")
            results = table_service.get_tables(status="occupied")
            self.assertEqual([table.name for table in results], ["Bàn 02"])

    def test_init_db_command_creates_table_model_table(self):
        with self.app.app_context():
            db.session.remove()
            Table.__table__.drop(db.engine)

        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            self.assertTrue(inspect(db.engine).has_table("cafe_tables"))


if __name__ == "__main__":
    unittest.main()