from app.extensions import db


class OrderItem(db.Model):
    __tablename__ = "order_items"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_order_item_quantity_positive"),
        db.CheckConstraint("unit_price > 0", name="ck_order_item_unit_price_positive"),
        db.CheckConstraint("subtotal >= 0", name="ck_order_item_subtotal_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    menu_item_id = db.Column(
        db.Integer,
        db.ForeignKey("menu_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")
    menu_item = db.relationship("MenuItem")