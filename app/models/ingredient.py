from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db


class Ingredient(db.Model):
    __tablename__ = "ingredients"
    __table_args__ = (
        db.CheckConstraint(
            "length(trim(name)) > 0", name="ck_ingredient_name_not_empty"
        ),
        db.CheckConstraint(
            "length(trim(unit)) > 0", name="ck_ingredient_unit_not_empty"
        ),
        db.CheckConstraint("quantity >= 0", name="ck_ingredient_quantity_nonnegative"),
        db.CheckConstraint(
            "min_quantity >= 0", name="ck_ingredient_min_quantity_nonnegative"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    unit = db.Column(db.String(24), nullable=False)
    quantity = db.Column(
        db.Numeric(12, 3), nullable=False, default=Decimal("0.000"), server_default="0"
    )
    min_quantity = db.Column(
        db.Numeric(12, 3), nullable=False, default=Decimal("0.000"), server_default="0"
    )
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
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

    stock_transactions = db.relationship(
        "StockTransaction", back_populates="ingredient", passive_deletes=True
    )