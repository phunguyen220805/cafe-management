from datetime import datetime, timezone

from app.extensions import db


STOCK_TRANSACTION_TYPES = ("import", "export")


class StockTransaction(db.Model):
    __tablename__ = "stock_transactions"
    __table_args__ = (
        db.CheckConstraint(
            "type IN ('import', 'export')", name="ck_stock_transaction_type_valid"
        ),
        db.CheckConstraint(
            "quantity > 0", name="ck_stock_transaction_quantity_positive"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(
        db.Integer,
        db.ForeignKey("ingredients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    type = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    ingredient = db.relationship("Ingredient", back_populates="stock_transactions")