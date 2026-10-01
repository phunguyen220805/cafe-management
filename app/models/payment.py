from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Index, text

from app.extensions import db


PAYMENT_METHODS = ("cash", "transfer")
PAYMENT_STATUSES = ("pending", "paid", "cancelled")
TRANSACTION_CODE_MAX_LENGTH = 120


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        db.CheckConstraint(
            "method IN ('cash', 'transfer')", name="ck_payment_method_valid"
        ),
        db.CheckConstraint(
            "status IN ('pending', 'paid', 'cancelled')",
            name="ck_payment_status_valid",
        ),
        db.CheckConstraint("amount >= 0", name="ck_payment_amount_nonnegative"),
        db.CheckConstraint(
            "transaction_code IS NULL OR "
            "(method = 'transfer' AND length(trim(transaction_code)) > 0 "
            "AND length(transaction_code) <= 120)",
            name="ck_payment_transaction_code_valid",
        ),
        Index(
            "uq_payment_one_active_per_order",
            "order_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'paid')"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    method = db.Column(db.String(20), nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default="pending", server_default="pending"
    )
    transaction_code = db.Column(
        db.String(TRANSACTION_CODE_MAX_LENGTH), nullable=True
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)

    order = db.relationship("Order", back_populates="payments")