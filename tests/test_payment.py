import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import Category, MenuItem, Order, Payment
from app.services.auth_service import create_user
from app.services.menu_service import create_category, create_menu_item
from app.services.order_service import create_order
from app.services import payment_service


class PaymentTests(unittest.TestCase):
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
            menu_item = create_menu_item("Bạc xỉu", category.id, "12500.50")
            order = create_order(
                [{"menu_item_id": menu_item.id, "quantity": 2}]
            )
            self.menu_item_id = menu_item.id
            self.order_id = order.id
            self.order_code = order.order_code
            self.order_amount = Decimal("25001.00")

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

    def _create_payment(self, method="cash", transaction_code=None, order_id=None):
        return payment_service.create_payment(
            order_id=order_id if order_id is not None else self.order_id,
            method=method,
            transaction_code=transaction_code,
        )

    def test_all_payment_routes_require_authentication(self):
        cases = (
            ("GET", "/payments"),
            ("GET", "/payments/1"),
            ("POST", "/payments/add"),
            ("POST", "/payments/1/confirm"),
            ("POST", "/payments/1/cancel"),
        )
        for method, path in cases:
            with self.subTest(method=method, path=path):
                response = self.client.open(path, method=method)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.startswith("/login?next="))

    def test_authenticated_user_can_view_payment_list(self):
        self._login()
        response = self.client.get("/payments")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Thanh toán".encode(), response.data)

    def test_authenticated_user_can_view_payment_detail(self):
        with self.app.app_context():
            payment = self._create_payment()
            payment_id = payment.id
        self._login()
        response = self.client.get(f"/payments/{payment_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.order_code.encode(), response.data)
        self.assertIn("25,001.00 đ".encode(), response.data)

    def test_create_cash_payment(self):
        with self.app.app_context():
            payment = self._create_payment()
            self.assertEqual(payment.method, "cash")
            self.assertEqual(payment.status, "pending")
            self.assertIsNone(payment.transaction_code)

    def test_create_transfer_payment(self):
        with self.app.app_context():
            payment = self._create_payment(
                method="transfer", transaction_code="TX-001"
            )
            self.assertEqual(payment.method, "transfer")
            self.assertEqual(payment.transaction_code, "TX-001")

    def test_amount_is_copied_from_order_total(self):
        with self.app.app_context():
            payment = self._create_payment()
            self.assertEqual(payment.amount, self.order_amount)
            self.assertIsInstance(payment.amount, Decimal)

    def test_client_cannot_override_payment_amount(self):
        self._login()
        response = self.client.post(
            "/payments/add",
            data={
                "order_id": str(self.order_id),
                "method": "cash",
                "amount": "0.01",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            payment = Payment.query.one()
            self.assertEqual(payment.amount, self.order_amount)

    def test_order_must_exist(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                self._create_payment(order_id=999)
            self.assertEqual(Payment.query.count(), 0)

    def test_cancelled_order_cannot_be_paid(self):
        with self.app.app_context():
            order = db.session.get(Order, self.order_id)
            order.status = "cancelled"
            db.session.commit()
            with self.assertRaises(ValueError):
                self._create_payment()
            self.assertEqual(Payment.query.count(), 0)

    def test_invalid_method_is_rejected(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                self._create_payment(method="card")
            self.assertEqual(Payment.query.count(), 0)

    def test_transfer_transaction_code_is_trimmed_and_stored(self):
        with self.app.app_context():
            payment = self._create_payment(
                method="transfer", transaction_code="  TX-ABC  "
            )
            self.assertEqual(payment.transaction_code, "TX-ABC")

    def test_cash_rejects_transaction_code(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                self._create_payment(method="cash", transaction_code="TX-ABC")
            self.assertEqual(Payment.query.count(), 0)

    def test_transaction_code_length_is_validated(self):
        with self.app.app_context():
            with self.assertRaises(ValueError):
                self._create_payment(
                    method="transfer", transaction_code="X" * 121
                )
            self.assertEqual(Payment.query.count(), 0)

    def test_second_pending_payment_is_rejected(self):
        with self.app.app_context():
            self._create_payment()
            with self.assertRaises(ValueError):
                self._create_payment(method="transfer", transaction_code="TX-2")
            self.assertEqual(Payment.query.count(), 1)

    def test_payment_cannot_be_created_after_order_is_paid(self):
        with self.app.app_context():
            payment = self._create_payment()
            payment_service.confirm_payment(payment.id)
            with self.assertRaises(ValueError):
                self._create_payment()
            self.assertEqual(Payment.query.count(), 1)

    def test_confirm_pending_payment_sets_paid_and_paid_at(self):
        with self.app.app_context():
            payment = self._create_payment()
            confirmed = payment_service.confirm_payment(payment.id)
            self.assertEqual(confirmed.status, "paid")
            self.assertIsNotNone(confirmed.paid_at)
            self.assertEqual(confirmed.amount, self.order_amount)

    def test_confirm_transfer_can_save_transaction_code(self):
        with self.app.app_context():
            payment = self._create_payment(method="transfer")
            confirmed = payment_service.confirm_payment(
                payment.id, transaction_code="TX-CONFIRM"
            )
            self.assertEqual(confirmed.transaction_code, "TX-CONFIRM")

    def test_confirm_transfer_keeps_existing_transaction_code(self):
        with self.app.app_context():
            payment = self._create_payment(
                method="transfer", transaction_code="TX-CREATE"
            )
            confirmed = payment_service.confirm_payment(payment.id)
            self.assertEqual(confirmed.transaction_code, "TX-CREATE")

    def test_confirm_rejects_transaction_code_for_cash(self):
        with self.app.app_context():
            payment = self._create_payment()
            with self.assertRaises(ValueError):
                payment_service.confirm_payment(
                    payment.id, transaction_code="TX-CASH"
                )
            self.assertEqual(db.session.get(Payment, payment.id).status, "pending")

    def test_confirm_rejects_transfer_code_too_long(self):
        with self.app.app_context():
            payment = self._create_payment(method="transfer")
            with self.assertRaises(ValueError):
                payment_service.confirm_payment(payment.id, "X" * 121)
            self.assertEqual(db.session.get(Payment, payment.id).status, "pending")

    def test_confirm_rejects_payment_already_paid(self):
        with self.app.app_context():
            payment = self._create_payment()
            payment_service.confirm_payment(payment.id)
            with self.assertRaises(ValueError):
                payment_service.confirm_payment(payment.id)

    def test_confirm_rejects_cancelled_payment(self):
        with self.app.app_context():
            payment = self._create_payment()
            payment_service.cancel_payment(payment.id)
            with self.assertRaises(ValueError):
                payment_service.confirm_payment(payment.id)

    def test_confirm_rejects_order_cancelled_after_payment_creation(self):
        with self.app.app_context():
            payment = self._create_payment()
            order = db.session.get(Order, self.order_id)
            order.status = "cancelled"
            db.session.commit()
            with self.assertRaises(ValueError):
                payment_service.confirm_payment(payment.id)
            self.assertEqual(db.session.get(Payment, payment.id).status, "pending")

    def test_cancel_pending_payment(self):
        with self.app.app_context():
            payment = self._create_payment()
            cancelled = payment_service.cancel_payment(payment.id)
            self.assertEqual(cancelled.status, "cancelled")

    def test_paid_payment_cannot_be_cancelled(self):
        with self.app.app_context():
            payment = self._create_payment()
            payment_service.confirm_payment(payment.id)
            with self.assertRaises(ValueError):
                payment_service.cancel_payment(payment.id)
            self.assertEqual(db.session.get(Payment, payment.id).status, "paid")

    def test_cancelled_payment_cannot_be_cancelled_again(self):
        with self.app.app_context():
            payment = self._create_payment()
            payment_service.cancel_payment(payment.id)
            with self.assertRaises(ValueError):
                payment_service.cancel_payment(payment.id)

    def test_payment_can_be_retried_after_pending_payment_cancelled(self):
        with self.app.app_context():
            first = self._create_payment()
            payment_service.cancel_payment(first.id)
            second = self._create_payment(method="transfer", transaction_code="TX-NEW")
            self.assertNotEqual(first.id, second.id)
            self.assertEqual(second.status, "pending")
            self.assertEqual(Payment.query.count(), 2)

    def test_retry_payment_takes_new_order_amount_snapshot(self):
        with self.app.app_context():
            first = self._create_payment()
            payment_service.cancel_payment(first.id)
            order = db.session.get(Order, self.order_id)
            order.total_amount = Decimal("31999.25")
            db.session.commit()
            second = self._create_payment()
            self.assertEqual(first.amount, self.order_amount)
            self.assertEqual(second.amount, Decimal("31999.25"))

    def test_search_by_order_code(self):
        with self.app.app_context():
            payment = self._create_payment()
            results = payment_service.get_payments(search=self.order_code[-6:])
            self.assertEqual([result.id for result in results], [payment.id])

    def test_filter_payments_by_status(self):
        with self.app.app_context():
            payment = self._create_payment()
            payment_service.confirm_payment(payment.id)
            results = payment_service.get_payments(status="paid")
            self.assertEqual([result.id for result in results], [payment.id])

    def test_filter_payments_by_method(self):
        with self.app.app_context():
            cash = self._create_payment()
            payment_service.cancel_payment(cash.id)
            transfer = self._create_payment(method="transfer")
            results = payment_service.get_payments(method="transfer")
            self.assertEqual([result.id for result in results], [transfer.id])

    def test_payments_are_sorted_newest_first(self):
        with self.app.app_context():
            first_order = db.session.get(Order, self.order_id)
            first = self._create_payment()
            payment_service.cancel_payment(first.id)
            second_order = create_order(
                [{"menu_item_id": self.menu_item_id, "quantity": 1}]
            )
            second = self._create_payment(order_id=second_order.id)
            results = payment_service.get_payments()
            self.assertEqual([item.id for item in results], [second.id, first.id])
            self.assertIsNotNone(first_order)

    def test_order_cannot_be_deleted_while_payment_exists(self):
        with self.app.app_context():
            self._create_payment()
            order = db.session.get(Order, self.order_id)
            db.session.delete(order)
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()
            self.assertIsNotNone(db.session.get(Order, self.order_id))

    def test_create_payment_rolls_back_on_commit_failure(self):
        with self.app.app_context():
            session = db.session()
            with patch.object(session, "commit", side_effect=RuntimeError("commit")):
                with self.assertRaises(RuntimeError):
                    self._create_payment()
            self.assertEqual(Payment.query.count(), 0)

    def test_confirm_payment_rolls_back_on_commit_failure(self):
        with self.app.app_context():
            payment = self._create_payment()
            session = db.session()
            with patch.object(session, "commit", side_effect=RuntimeError("commit")):
                with self.assertRaises(RuntimeError):
                    payment_service.confirm_payment(payment.id)
            self.assertEqual(db.session.get(Payment, payment.id).status, "pending")

    def test_init_db_creates_payment_table(self):
        with self.app.app_context():
            db.session.remove()
            Payment.__table__.drop(db.engine)
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            self.assertTrue(inspect(db.engine).has_table("payments"))

    def test_sqlite_foreign_keys_are_enabled(self):
        with self.app.app_context():
            enabled = db.session.execute(text("PRAGMA foreign_keys")).scalar_one()
            self.assertEqual(enabled, 1)


if __name__ == "__main__":
    unittest.main()