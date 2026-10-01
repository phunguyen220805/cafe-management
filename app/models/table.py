from app.extensions import db


TABLE_STATUSES = ("available", "occupied", "reserved", "maintenance")


class Table(db.Model):
    __tablename__ = "cafe_tables"
    __table_args__ = (
        db.CheckConstraint(
            "length(trim(name)) > 0", name="ck_cafe_table_name_not_empty"
        ),
        db.CheckConstraint("capacity > 0", name="ck_cafe_table_capacity_positive"),
        db.CheckConstraint(
            "status IN ('available', 'occupied', 'reserved', 'maintenance')",
            name="ck_cafe_table_status_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default="available", server_default="available"
    )
    description = db.Column(db.Text)