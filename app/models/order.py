from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db


ORDER_STATUSES = ("pending", "preparing", "completed", "cancelled")


class Order(db.Model):
    __tablename__ = "orders"
    __table_args__ = (
        db.CheckConstraint(
            "length(trim(order_code)) > 0", name="ck_order_code_not_empty"
        ),
        db.CheckConstraint(
            "status IN ('pending', 'preparing', 'completed', 'cancelled')",
            name="ck_order_status_valid",
        ),
        db.CheckConstraint("total_amount >= 0", name="ck_order_total_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(32), nullable=False, unique=True, index=True)
    table_id = db.Column(
        db.Integer,
        db.ForeignKey("cafe_tables.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status = db.Column(
        db.String(20), nullable=False, default="pending", server_default="pending"
    )
    total_amount = db.Column(
        db.Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    description = db.Column(db.Text)

    table = db.relationship("Table")
    items = db.relationship("OrderItem", back_populates="order", lazy="selectin")