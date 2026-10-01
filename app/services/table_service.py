from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Table
from app.models.table import TABLE_STATUSES


def _required_name(value):
    name = value.strip() if isinstance(value, str) else ""
    if not name:
        raise ValueError("Tên bàn không được để trống.")
    return name


def _positive_capacity(value):
    try:
        capacity_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Sức chứa phải là số nguyên lớn hơn 0.") from None
    if (
        not capacity_value.is_finite()
        or capacity_value != capacity_value.to_integral_value()
        or capacity_value <= 0
    ):
        raise ValueError("Sức chứa phải là số nguyên lớn hơn 0.")
    return int(capacity_value)


def _valid_status(value):
    status = value.strip() if isinstance(value, str) else ""
    if status not in TABLE_STATUSES:
        raise ValueError("Trạng thái bàn không hợp lệ.")
    return status


def _optional_text(value):
    description = value.strip() if isinstance(value, str) else ""
    return description or None


def _get_table(table_id):
    try:
        identifier = int(table_id)
    except (TypeError, ValueError):
        raise ValueError("Bàn không hợp lệ.") from None
    if identifier <= 0:
        raise ValueError("Bàn không hợp lệ.")
    table = db.session.get(Table, identifier)
    if table is None:
        raise ValueError("Không tìm thấy bàn.")
    return table


def _commit():
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("Tên bàn đã tồn tại hoặc dữ liệu không hợp lệ.") from error
    except Exception:
        db.session.rollback()
        raise


def create_table(name, capacity, status="available", description=None):
    name = _required_name(name)
    capacity = _positive_capacity(capacity)
    status = _valid_status(status)
    if Table.query.filter_by(name=name).first() is not None:
        raise ValueError("Tên bàn đã tồn tại.")

    table = Table(
        name=name,
        capacity=capacity,
        status=status,
        description=_optional_text(description),
    )
    db.session.add(table)
    _commit()
    return table


def update_table(table_id, name, capacity, status, description=None):
    table = _get_table(table_id)
    name = _required_name(name)
    capacity = _positive_capacity(capacity)
    status = _valid_status(status)
    duplicate = Table.query.filter(Table.name == name, Table.id != table.id).first()
    if duplicate is not None:
        raise ValueError("Tên bàn đã tồn tại.")

    table.name = name
    table.capacity = capacity
    table.status = status
    table.description = _optional_text(description)
    _commit()
    return table


def delete_table(table_id):
    table = _get_table(table_id)
    db.session.delete(table)
    _commit()


def get_tables(search=None, status=None):
    query = Table.query
    search_term = search.strip() if isinstance(search, str) else ""
    if search_term:
        query = query.filter(Table.name.ilike(f"%{search_term}%"))
    if status not in (None, ""):
        selected_status = _valid_status(status)
        query = query.filter(Table.status == selected_status)
    return query.order_by(Table.name.asc()).all()