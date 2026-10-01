from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Order, Payment
from app.models.payment import (
    PAYMENT_METHODS,
    PAYMENT_STATUSES,
    TRANSACTION_CODE_MAX_LENGTH,
)


def _required_id(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} không hợp lệ.")
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} không hợp lệ.") from None
    if identifier <= 0 or str(value).strip() not in {str(identifier), f"+{identifier}"}:
        raise ValueError(f"{label} không hợp lệ.")
    return identifier


def _valid_method(value):
    method = value.strip() if isinstance(value, str) else ""
    if method not in PAYMENT_METHODS:
        raise ValueError("Phương thức thanh toán không hợp lệ.")
    return method


def _valid_status(value):
    status = value.strip() if isinstance(value, str) else ""
    if status not in PAYMENT_STATUSES:
        raise ValueError("Trạng thái thanh toán không hợp lệ.")
    return status


def _transaction_code(value, method, required):
    code = value.strip() if isinstance(value, str) else ""
    if method == "cash":
        if code:
            raise ValueError("Tiền mặt không sử dụng mã giao dịch.")
        return None
    if not code:
        if required:
            raise ValueError("Vui lòng nhập mã giao dịch chuyển khoản.")
        return None
    if len(code) > TRANSACTION_CODE_MAX_LENGTH:
        raise ValueError("Mã giao dịch vượt quá độ dài cho phép.")
    return code


def _get_order(order_id):
    identifier = _required_id(order_id, "Đơn hàng")
    order = db.session.get(Order, identifier)
    if order is None:
        raise ValueError("Không tìm thấy đơn hàng.")
    return order


def _get_payment(payment_id):
    identifier = _required_id(payment_id, "Thanh toán")
    payment = (
        Payment.query.options(joinedload(Payment.order).joinedload(Order.table))
        .filter_by(id=identifier)
        .first()
    )
    if payment is None:
        raise ValueError("Không tìm thấy thanh toán.")
    return payment


def _has_active_payment(order_id, exclude_payment_id=None):
    query = Payment.query.filter(
        Payment.order_id == order_id,
        Payment.status.in_(("pending", "paid")),
    )
    if exclude_payment_id is not None:
        query = query.filter(Payment.id != exclude_payment_id)
    return query.first() is not None


def _commit(error_message):
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError(error_message) from error
    except Exception:
        db.session.rollback()
        raise


def create_payment(order_id, method, transaction_code=None):
    try:
        order = _get_order(order_id)
        if order.status == "cancelled":
            raise ValueError("Không thể thanh toán đơn hàng đã hủy.")
        method = _valid_method(method)
        code = _transaction_code(transaction_code, method, required=False)
        if _has_active_payment(order.id):
            raise ValueError(
                "Đơn hàng đã có thanh toán đang chờ hoặc đã thanh toán."
            )

        payment = Payment(
            order=order,
            amount=Decimal(str(order.total_amount)),
            method=method,
            status="pending",
            transaction_code=code,
        )
        db.session.add(payment)
        _commit("Đơn hàng đã có một thanh toán đang chờ hoặc đã thanh toán.")
        return payment
    except Exception:
        db.session.rollback()
        raise


def get_payment(payment_id):
    return _get_payment(payment_id)


def get_payments(search=None, status=None, method=None):
    query = Payment.query.options(
        joinedload(Payment.order).joinedload(Order.table)
    )
    search_term = search.strip() if isinstance(search, str) else ""
    if search_term:
        query = query.join(Payment.order).filter(
            Order.order_code.ilike(f"%{search_term}%")
        )
    if status not in (None, ""):
        query = query.filter(Payment.status == _valid_status(status))
    if method not in (None, ""):
        query = query.filter(Payment.method == _valid_method(method))
    return query.order_by(Payment.created_at.desc(), Payment.id.desc()).all()


def get_payable_orders():
    active_order_ids = select(Payment.order_id).where(
        Payment.status.in_(("pending", "paid"))
    )
    return (
        Order.query.filter(
            Order.status != "cancelled",
            ~Order.id.in_(active_order_ids),
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )


def confirm_payment(payment_id, transaction_code=None):
    try:
        payment = _get_payment(payment_id)
        if payment.status != "pending":
            raise ValueError("Chỉ có thể xác nhận thanh toán đang chờ.")
        if payment.order.status == "cancelled":
            raise ValueError("Không thể thanh toán đơn hàng đã hủy.")
        if _has_active_payment(payment.order_id, exclude_payment_id=payment.id):
            raise ValueError("Đơn hàng đã có một thanh toán khác đang hoạt động.")

        supplied_code = transaction_code.strip() if isinstance(transaction_code, str) else ""
        code = supplied_code or payment.transaction_code
        code = _transaction_code(
            code,
            payment.method,
            required=False,
        )
        payment.transaction_code = code
        payment.status = "paid"
        payment.paid_at = datetime.now(timezone.utc)
        _commit("Đơn hàng đã có một thanh toán khác đang hoạt động.")
        return payment
    except Exception:
        db.session.rollback()
        raise


def cancel_payment(payment_id):
    try:
        payment = _get_payment(payment_id)
        if payment.status != "pending":
            raise ValueError("Chỉ có thể hủy thanh toán đang chờ.")
        payment.status = "cancelled"
        _commit("Không thể hủy thanh toán do dữ liệu đã thay đổi.")
        return payment
    except Exception:
        db.session.rollback()
        raise