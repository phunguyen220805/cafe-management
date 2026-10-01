from app.extensions import db


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = (
        db.CheckConstraint("length(trim(name)) > 0", name="ck_category_name_not_empty"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.Text)

    menu_items = db.relationship("MenuItem", back_populates="category")