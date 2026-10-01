from app.extensions import db


class MenuItem(db.Model):
    __tablename__ = "menu_items"
    __table_args__ = (
        db.CheckConstraint("length(trim(name)) > 0", name="ck_menu_item_name_not_empty"),
        db.CheckConstraint("price > 0", name="ck_menu_item_price_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    price = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text)
    image = db.Column(db.String(500))
    is_available = db.Column(db.Boolean, nullable=False, default=True)

    category = db.relationship("Category", back_populates="menu_items")