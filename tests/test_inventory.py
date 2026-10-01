import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import Ingredient, StockTransaction
from app.services.auth_service import create_user
from app.services import inventory_service


class InventoryTests(unittest.TestCase):
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

    def _create_ingredient(self, name="Hạt cà phê", **kwargs):
        return inventory_service.create_ingredient(
            name=name,
            unit=kwargs.pop("unit", "g"),
            **kwargs,
        )

    def test_inventory_routes_require_authentication(self):
        routes = (
            ("GET", "/inventory"),
            ("POST", "/inventory/ingredients/add"),
            ("POST", "/inventory/ingredients/1/edit"),
            ("POST", "/inventory/ingredients/1/delete"),
            ("POST", "/inventory/ingredients/1/import"),
            ("POST", "/inventory/ingredients/1/export"),
            ("GET", "/inventory/ingredients/1/history"),
        )
        for method, path in routes:
            with self.subTest(method=method, path=path):
                response = self.client.open(path, method=method)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.startswith("/login?next="))

    def test_logged_in_user_can_open_inventory(self):
        self._login()
        response = self.client.get("/inventory")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Kho nguyên liệu".encode(), response.data)

    def test_create_ingredient_succeeds_with_zero_initial_stock(self):
        with self.app.app_context():
            ingredient = self._create_ingredient(
                min_quantity=Decimal("3.250"), description="Nguồn Arabica"
            )
            self.assertEqual(ingredient.name, "Hạt cà phê")
            self.assertEqual(ingredient.unit, "g")
            self.assertEqual(ingredient.quantity, Decimal("0.000"))
            self.assertEqual(ingredient.min_quantity, Decimal("3.250"))
            self.assertTrue(ingredient.is_active)

    def test_empty_name_is_rejected(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                self._create_ingredient(name="  ")
            self.assertEqual(Ingredient.query.count(), 0)

    def test_empty_unit_is_rejected(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                self._create_ingredient(unit="  ")
            self.assertEqual(Ingredient.query.count(), 0)

    def test_duplicate_name_is_rejected_after_trimming(self):
        with self.app.app_context():
            self._create_ingredient(name="Hạt cà phê")
            with self.assertRaises(ValueError):
                self._create_ingredient(name=" Hạt cà phê ")
            self.assertEqual(Ingredient.query.count(), 1)

    def test_negative_quantity_and_minimum_are_rejected(self):
        with self.app.app_context():
            for field, value in (("min_quantity", "-0.001"),):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self._create_ingredient(**{field: value})
            ingredient = self._create_ingredient()
            with self.assertRaises(ValueError):
                inventory_service.update_ingredient(
                    ingredient.id, ingredient.name, ingredient.unit, "-1"
                )

    def test_invalid_decimal_and_infinity_are_rejected(self):
        with self.app.app_context():
            for value in ("abc", "Infinity", "-Infinity", "NaN", "1.0001"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self._create_ingredient(min_quantity=value)
            self.assertEqual(Ingredient.query.count(), 0)

    def test_update_ingredient(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            updated = inventory_service.update_ingredient(
                ingredient.id,
                "Bột cà phê",
                "kg",
                "1.250",
                description="Bột rang xay",
                is_active=False,
            )
            self.assertEqual(updated.name, "Bột cà phê")
            self.assertEqual(updated.unit, "kg")
            self.assertEqual(updated.min_quantity, Decimal("1.250"))
            self.assertEqual(updated.description, "Bột rang xay")
            self.assertFalse(updated.is_active)
            self.assertEqual(updated.quantity, Decimal("0.000"))

    def test_unit_cannot_change_after_stock_transaction(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            inventory_service.import_stock(ingredient.id, "5")
            with self.assertRaises(ValueError):
                inventory_service.update_ingredient(
                    ingredient.id, ingredient.name, "kg", "0"
                )
            self.assertEqual(
                db.session.get(Ingredient, ingredient.id).unit,
                "g",
            )

    def test_delete_ingredient_without_history(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            inventory_service.delete_ingredient(ingredient.id)
            self.assertIsNone(db.session.get(Ingredient, ingredient.id))

    def test_ingredient_with_history_cannot_be_deleted(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            inventory_service.import_stock(ingredient.id, "2")
            with self.assertRaises(ValueError):
                inventory_service.delete_ingredient(ingredient.id)
            self.assertIsNotNone(db.session.get(Ingredient, ingredient.id))

    def test_import_increases_stock_and_creates_history(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            transaction = inventory_service.import_stock(
                ingredient.id, "10.125", "Nhập đầu kỳ"
            )
            self.assertEqual(transaction.type, "import")
            self.assertEqual(transaction.quantity, Decimal("10.125"))
            self.assertEqual(transaction.note, "Nhập đầu kỳ")
            self.assertEqual(
                db.session.get(Ingredient, ingredient.id).quantity,
                Decimal("10.125"),
            )
            self.assertEqual(StockTransaction.query.count(), 1)

    def test_export_decreases_stock_and_creates_history(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            inventory_service.import_stock(ingredient.id, "8.500")
            transaction = inventory_service.export_stock(
                ingredient.id, "3.250", "Pha chế"
            )
            self.assertEqual(transaction.type, "export")
            self.assertEqual(transaction.quantity, Decimal("3.250"))
            self.assertEqual(transaction.note, "Pha chế")
            self.assertEqual(
                db.session.get(Ingredient, ingredient.id).quantity,
                Decimal("5.250"),
            )
            self.assertEqual(StockTransaction.query.count(), 2)

    def test_export_more_than_stock_is_rejected_without_history(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            inventory_service.import_stock(ingredient.id, "2")
            with self.assertRaises(ValueError):
                inventory_service.export_stock(ingredient.id, "2.001")
            self.assertEqual(
                db.session.get(Ingredient, ingredient.id).quantity,
                Decimal("2.000"),
            )
            self.assertEqual(StockTransaction.query.count(), 1)

    def test_zero_and_negative_movements_are_rejected(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            for movement in (inventory_service.import_stock, inventory_service.export_stock):
                for quantity in ("0", "-0.001"):
                    with self.subTest(movement=movement.__name__, quantity=quantity):
                        with self.assertRaises(ValueError):
                            movement(ingredient.id, quantity)
            self.assertEqual(StockTransaction.query.count(), 0)

    def test_unknown_ingredient_is_rejected(self):
        with self.app.app_context():
            for operation in (
                lambda: inventory_service.import_stock(999, "1"),
                lambda: inventory_service.export_stock(999, "1"),
                lambda: inventory_service.get_ingredient_history(999),
            ):
                with self.assertRaises(ValueError):
                    operation()

    def test_inactive_ingredient_cannot_be_imported_or_exported(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            inventory_service.import_stock(ingredient.id, "3")
            inventory_service.update_ingredient(
                ingredient.id, ingredient.name, ingredient.unit, "0", is_active=False
            )
            with self.assertRaises(ValueError):
                inventory_service.import_stock(ingredient.id, "1")
            with self.assertRaises(ValueError):
                inventory_service.export_stock(ingredient.id, "1")
            self.assertEqual(
                db.session.get(Ingredient, ingredient.id).quantity,
                Decimal("3.000"),
            )

    def test_import_rolls_back_balance_if_commit_fails(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            session = db.session()
            with patch.object(session, "commit", side_effect=RuntimeError("commit")):
                with self.assertRaises(RuntimeError):
                    inventory_service.import_stock(ingredient.id, "4")
            self.assertEqual(
                db.session.get(Ingredient, ingredient.id).quantity,
                Decimal("0.000"),
            )
            self.assertEqual(StockTransaction.query.count(), 0)

    def test_export_rolls_back_balance_if_commit_fails(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            inventory_service.import_stock(ingredient.id, "6")
            session = db.session()
            with patch.object(session, "commit", side_effect=RuntimeError("commit")):
                with self.assertRaises(RuntimeError):
                    inventory_service.export_stock(ingredient.id, "2")
            self.assertEqual(
                db.session.get(Ingredient, ingredient.id).quantity,
                Decimal("6.000"),
            )
            self.assertEqual(StockTransaction.query.count(), 1)

    def test_low_stock_includes_equal_and_below_minimum(self):
        with self.app.app_context():
            equal = self._create_ingredient("Equal", min_quantity="5")
            below = self._create_ingredient("Below", min_quantity="5")
            above = self._create_ingredient("Above", min_quantity="5")
            inventory_service.import_stock(equal.id, "5")
            inventory_service.import_stock(below.id, "4")
            inventory_service.import_stock(above.id, "6")
            results = inventory_service.get_ingredients(low_stock=True)
            self.assertEqual({item.id for item in results}, {equal.id, below.id})

    def test_search_ingredients_by_name(self):
        with self.app.app_context():
            self._create_ingredient("Hạt cà phê")
            self._create_ingredient("Sữa tươi")
            results = inventory_service.get_ingredients(search="sữa")
            self.assertEqual([item.name for item in results], ["Sữa tươi"])

    def test_filter_by_active_status(self):
        with self.app.app_context():
            active = self._create_ingredient("Đang dùng")
            inactive = self._create_ingredient("Ngừng dùng")
            inventory_service.update_ingredient(
                inactive.id, inactive.name, inactive.unit, "0", is_active=False
            )
            self.assertEqual(
                [item.id for item in inventory_service.get_ingredients(is_active="active")],
                [active.id],
            )
            self.assertEqual(
                [item.id for item in inventory_service.get_ingredients(is_active="inactive")],
                [inactive.id],
            )

    def test_history_is_sorted_newest_first(self):
        with self.app.app_context():
            ingredient = self._create_ingredient()
            first = inventory_service.import_stock(ingredient.id, "2", "Lần một")
            second = inventory_service.import_stock(ingredient.id, "3", "Lần hai")
            history = inventory_service.get_ingredient_history(ingredient.id)
            self.assertEqual([transaction.id for transaction in history], [second.id, first.id])

    def test_inventory_routes_create_and_move_stock_when_logged_in(self):
        self._login()
        response = self.client.post(
            "/inventory/ingredients/add",
            data={"name": "Sữa", "unit": "ml", "min_quantity": "10"},
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            ingredient = Ingredient.query.filter_by(name="Sữa").one()
            ingredient_id = ingredient.id
        response = self.client.post(
            f"/inventory/ingredients/{ingredient_id}/import",
            data={"quantity": "25", "note": "Nhập thử", "new_quantity": "999"},
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            ingredient = db.session.get(Ingredient, ingredient_id)
            self.assertEqual(ingredient.quantity, Decimal("25.000"))
            self.assertEqual(StockTransaction.query.count(), 1)

    def test_init_db_creates_inventory_tables(self):
        with self.app.app_context():
            db.session.remove()
            StockTransaction.__table__.drop(db.engine)
            Ingredient.__table__.drop(db.engine)
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            self.assertTrue(inspect(db.engine).has_table("ingredients"))
            self.assertTrue(inspect(db.engine).has_table("stock_transactions"))


if __name__ == "__main__":
    unittest.main()