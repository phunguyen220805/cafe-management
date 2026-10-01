import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import Category, MenuItem
from app.services import menu_service
from app.services.auth_service import create_user


class MenuTests(unittest.TestCase):
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
            category = menu_service.create_category("Cà phê")
            self.category_id = category.id

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

    def test_create_category_succeeds(self):
        with self.app.app_context():
            category = menu_service.create_category("Trà", "Trà pha tại quán")
            self.assertEqual(category.name, "Trà")
            self.assertEqual(Category.query.count(), 2)

    def test_category_name_cannot_be_empty(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                menu_service.create_category("   ")
            self.assertEqual(Category.query.count(), 1)

    def test_duplicate_category_name_is_rejected(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                menu_service.create_category("Cà phê")
            self.assertEqual(Category.query.count(), 1)

    def test_create_menu_item_succeeds_and_links_category(self):
        with self.app.app_context():
            item = menu_service.create_menu_item(
                "Bạc xỉu", self.category_id, "35000"
            )
            self.assertEqual(item.category_id, self.category_id)
            self.assertEqual(item.category.name, "Cà phê")
            self.assertEqual(MenuItem.query.count(), 1)

    def test_menu_item_name_cannot_be_empty(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                menu_service.create_menu_item(" ", self.category_id, "35000")
            self.assertEqual(MenuItem.query.count(), 0)

    def test_price_must_be_positive(self):
        with self.app.app_context():
            for price in ("0", "-1"):
                with self.subTest(price=price), self.assertRaises(ValueError):
                    menu_service.create_menu_item("Bạc xỉu", self.category_id, price)
            self.assertEqual(MenuItem.query.count(), 0)

    def test_category_must_exist(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                menu_service.create_menu_item("Bạc xỉu", 999, "35000")
            self.assertEqual(MenuItem.query.count(), 0)

    def test_update_menu_item(self):
        with self.app.app_context():
            item = menu_service.create_menu_item("Bạc xỉu", self.category_id, "35000")
            tea = menu_service.create_category("Trà")
            updated = menu_service.update_menu_item(
                item.id,
                "Trà đào",
                tea.id,
                "42000",
                description="Trà đào cam sả",
                is_available=False,
            )
            self.assertEqual(updated.name, "Trà đào")
            self.assertEqual(updated.category_id, tea.id)
            self.assertEqual(str(updated.price), "42000.00")
            self.assertFalse(updated.is_available)

    def test_delete_menu_item(self):
        with self.app.app_context():
            item = menu_service.create_menu_item("Bạc xỉu", self.category_id, "35000")
            menu_service.delete_menu_item(item.id)
            self.assertEqual(MenuItem.query.count(), 0)

    def test_category_with_menu_items_cannot_be_deleted(self):
        with self.app.app_context():
            menu_service.create_menu_item("Bạc xỉu", self.category_id, "35000")
            with self.assertRaises(ValueError):
                menu_service.delete_category(self.category_id)
            self.assertIsNotNone(db.session.get(Category, self.category_id))

    def test_empty_category_can_be_deleted(self):
        with self.app.app_context():
            menu_service.delete_category(self.category_id)
            self.assertIsNone(db.session.get(Category, self.category_id))

    def test_menu_requires_authentication(self):
        response = self.client.get("/menu")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("/login?next="))

    def test_authenticated_user_can_open_menu(self):
        self._login()
        response = self.client.get("/menu")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Thực đơn".encode(), response.data)

    def test_init_db_cli_succeeds(self):
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Database tables are ready.", result.output)

    def test_search_menu_items(self):
        with self.app.app_context():
            menu_service.create_menu_item("Bạc xỉu", self.category_id, "35000")
            menu_service.create_menu_item("Trà đào", self.category_id, "42000")
            results = menu_service.get_menu_items(search="bạc")
            self.assertEqual([item.name for item in results], ["Bạc xỉu"])

    def test_filter_menu_items_by_category(self):
        with self.app.app_context():
            tea = menu_service.create_category("Trà")
            menu_service.create_menu_item("Bạc xỉu", self.category_id, "35000")
            menu_service.create_menu_item("Trà đào", tea.id, "42000")
            results = menu_service.get_menu_items(category_id=tea.id)
            self.assertEqual([item.name for item in results], ["Trà đào"])


if __name__ == "__main__":
    unittest.main()