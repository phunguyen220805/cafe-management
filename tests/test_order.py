import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import Category, MenuItem, Order, OrderItem, Table
from app.services.auth_service import create_user
from app.services.menu_service import create_category, create_menu_item, update_menu_item
from app.services.table_service import create_table
from app.services import order_service


class OrderTests(unittest.TestCase):
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
            category = create_category("Cà phê")
            menu_item = create_menu_item("Bạc xỉu", category.id, "10000")
            table = create_table("Bàn 01", 4)
            self.menu_item_id = menu_item.id
            self.category_id = category.id
            self.table_id = table.id

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

    def _create_order(self, quantity=1, table_id=None):
        return order_service.create_order(
            items=[{"menu_item_id": self.menu_item_id, "quantity": quantity}],
            table_id=table_id,
        )

    def test_orders_list_requires_authentication(self):
        response = self.client.get("/orders")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("/login?next="))

    def test_order_detail_requires_authentication(self):
        with self.app.app_context():
            order = self._create_order()
            order_id = order.id
        response = self.client.get(f"/orders/{order_id}")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("/login?next="))

    def test_authenticated_user_can_open_orders(self):
        self._login()
        response = self.client.get("/orders")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Đơn hàng".encode(), response.data)

    def test_authenticated_user_can_view_order_detail(self):
        with self.app.app_context():
            order = self._create_order(quantity=2)
            order_id = order.id
            order_code = order.order_code
        self._login()
        response = self.client.get(f"/orders/{order_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(order_code.encode(), response.data)
        self.assertIn("20,000 đ".encode(), response.data)

    def test_create_order_for_table(self):
        with self.app.app_context():
            order = self._create_order(quantity=2, table_id=self.table_id)
            self.assertEqual(order.table_id, self.table_id)
            self.assertEqual(order.status, "pending")
            self.assertEqual(len(order.items), 1)

    def test_create_takeaway_order(self):
        with self.app.app_context():
            order = self._create_order()
            self.assertIsNone(order.table_id)

    def test_order_requires_at_least_one_item(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                order_service.create_order(items=[])
            self.assertEqual(Order.query.count(), 0)

    def test_quantity_must_be_positive(self):
        with self.app.app_context():
            for quantity in (0, -1):
                with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                    self._create_order(quantity=quantity)
            self.assertEqual(Order.query.count(), 0)

    def test_quantity_must_be_integer(self):
        with self.app.app_context():
            for quantity in ("1.5", "two"):
                with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                    self._create_order(quantity=quantity)
            self.assertEqual(Order.query.count(), 0)

    def test_menu_item_must_exist(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                order_service.create_order(
                    items=[{"menu_item_id": 999, "quantity": 1}]
                )
            self.assertEqual(Order.query.count(), 0)

    def test_unavailable_menu_item_is_rejected(self):
        with self.app.app_context():
            menu_item = db.session.get(MenuItem, self.menu_item_id)
            menu_item.is_available = False
            db.session.commit()
            with self.assertRaises(ValueError):
                self._create_order()
            self.assertEqual(Order.query.count(), 0)

    def test_table_must_exist_when_selected(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                self._create_order(table_id=999)
            self.assertEqual(Order.query.count(), 0)

    def test_order_prices_and_total_are_calculated(self):
        with self.app.app_context():
            another_item = create_menu_item("Espresso", self.category_id, "15000")
            order = order_service.create_order(
                items=[
                    {"menu_item_id": self.menu_item_id, "quantity": 2},
                    {"menu_item_id": another_item.id, "quantity": 3},
                ]
            )
            lines = {line.menu_item_id: line for line in order.items}
            self.assertEqual(lines[self.menu_item_id].unit_price, 10000)
            self.assertEqual(lines[self.menu_item_id].subtotal, 20000)
            self.assertEqual(lines[another_item.id].subtotal, 45000)
            self.assertEqual(order.total_amount, 65000)

    def test_duplicate_menu_items_are_aggregated(self):
        with self.app.app_context():
            order = order_service.create_order(
                items=[
                    {"menu_item_id": self.menu_item_id, "quantity": 2},
                    {"menu_item_id": self.menu_item_id, "quantity": 3},
                ]
            )
            self.assertEqual(len(order.items), 1)
            self.assertEqual(order.items[0].quantity, 5)
            self.assertEqual(order.total_amount, 50000)

    def test_price_snapshot_is_not_changed_with_menu_price(self):
        with self.app.app_context():
            order = self._create_order(quantity=2)
            order_id = order.id
            update_menu_item(
                self.menu_item_id,
                "Bạc xỉu",
                self.category_id,
                "18000",
                is_available=True,
            )
            old_order = order_service.get_order(order_id)
            self.assertEqual(old_order.items[0].unit_price, 10000)
            self.assertEqual(old_order.items[0].subtotal, 20000)
            self.assertEqual(old_order.total_amount, 20000)

    def test_update_order_status(self):
        with self.app.app_context():
            order = self._create_order()
            updated = order_service.update_order_status(order.id, "preparing")
            self.assertEqual(updated.status, "preparing")

    def test_invalid_order_status_is_rejected(self):
        with self.app.app_context():
            order = self._create_order()
            with self.assertRaises(ValueError):
                order_service.update_order_status(order.id, "paid")
            self.assertEqual(db.session.get(Order, order.id).status, "pending")

    def test_cancel_order(self):
        with self.app.app_context():
            order = self._create_order()
            cancelled = order_service.cancel_order(order.id)
            self.assertEqual(cancelled.status, "cancelled")
            self.assertEqual(len(cancelled.items), 1)

    def test_search_order_code(self):
        with self.app.app_context():
            order = self._create_order()
            results = order_service.get_orders(search=order.order_code[-6:])
            self.assertEqual([result.id for result in results], [order.id])

    def test_filter_orders_by_status(self):
        with self.app.app_context():
            pending = self._create_order()
            preparing = self._create_order()
            order_service.update_order_status(preparing.id, "preparing")
            results = order_service.get_orders(status="preparing")
            self.assertEqual([result.id for result in results], [preparing.id])
            self.assertNotEqual(pending.id, preparing.id)

    def test_filter_orders_by_table(self):
        with self.app.app_context():
            dine_in = self._create_order(table_id=self.table_id)
            takeaway = self._create_order()
            results = order_service.get_orders(table_id=self.table_id)
            self.assertEqual([result.id for result in results], [dine_in.id])
            self.assertNotIn(takeaway.id, [result.id for result in results])

    def test_orders_are_sorted_newest_first(self):
        with self.app.app_context():
            first = self._create_order()
            second = self._create_order()
            results = order_service.get_orders()
            self.assertEqual([result.id for result in results], [second.id, first.id])

    def test_duplicate_order_code_is_rejected(self):
        with self.app.app_context():
            with patch(
                "app.services.order_service._generate_order_code",
                return_value="ORD-DUPLICATE",
            ):
                self._create_order()
                with self.assertRaises(ValueError):
                    self._create_order()
            self.assertEqual(Order.query.count(), 1)

    def test_create_order_rolls_back_on_commit_failure(self):
        with self.app.app_context():
            session = db.session()
            with patch.object(session, "commit", side_effect=RuntimeError("commit")):
                with self.assertRaises(RuntimeError):
                    self._create_order()
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(OrderItem.query.count(), 0)

    def test_menu_item_in_an_order_cannot_be_deleted(self):
        with self.app.app_context():
            self._create_order()
            from app.services.menu_service import delete_menu_item

            with self.assertRaises(ValueError):
                delete_menu_item(self.menu_item_id)
            self.assertIsNotNone(db.session.get(MenuItem, self.menu_item_id))

    def test_table_referenced_by_an_order_cannot_be_deleted(self):
        with self.app.app_context():
            self._create_order(table_id=self.table_id)
            from app.services.table_service import delete_table

            with self.assertRaises(ValueError):
                delete_table(self.table_id)
            self.assertIsNotNone(db.session.get(Table, self.table_id))

    def test_init_db_creates_order_tables(self):
        with self.app.app_context():
            db.session.remove()
            OrderItem.__table__.drop(db.engine)
            Order.__table__.drop(db.engine)

        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            self.assertTrue(inspect(db.engine).has_table("orders"))
            self.assertTrue(inspect(db.engine).has_table("order_items"))

    def test_create_order_route_accepts_selected_items(self):
        self._login()
        response = self.client.post(
            "/orders/add",
            data={
                "table_id": str(self.table_id),
                "menu_item_id": [str(self.menu_item_id)],
                f"quantity_{self.menu_item_id}": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 1)
            self.assertEqual(Order.query.one().total_amount, 20000)


if __name__ == "__main__":
    unittest.main()