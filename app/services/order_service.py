from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models import MenuItem, Order, OrderItem, Table
from app.models.order import ORDER_STATUSES


_CENT = Decimal("0.01")


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


def _positive_quantity(value):
    if isinstance(value, bool):
        raise ValueError("Số lượng phải là số nguyên lớn hơn 0.")
    try:
        quantity_value = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Số lượng phải là số nguyên lớn hơn 0.") from None
    if (
        not quantity_value.is_finite()
        or quantity_value != quantity_value.to_integral_value()
        or quantity_value <= 0
    ):
        raise ValueError("Số lượng phải là số nguyên lớn hơn 0.")
    return int(quantity_value)


def _valid_status(value):
    status = value.strip() if isinstance(value, str) else ""
    if status not in ORDER_STATUSES:
        raise ValueError("Trạng thái đơn hàng không hợp lệ.")
    return status


def _optional_text(value):
    description = value.strip() if isinstance(value, str) else ""
    return description or None


def _get_order(order_id):
    identifier = _required_id(order_id, "Đơn hàng")
    order = (
        Order.query.options(
            joinedload(Order.table),
            selectinload(Order.items).joinedload(OrderItem.menu_item),
        )
        .filter_by(id=identifier)
        .first()
    )
    if order is None:
        raise ValueError("Không tìm thấy đơn hàng.")
    return order


def _generate_order_code():
    return f"ORD-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"


def _commit(integrity_message):
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError(integrity_message) from error
    except Exception:
        db.session.rollback()
        raise


def _validated_items(items):
    if not isinstance(items, (list, tuple)) or not items:
        raise ValueError("Đơn hàng phải có ít nhất một món.")

    quantities = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Danh sách món không hợp lệ.")
        menu_item_id = _required_id(item.get("menu_item_id"), "Món")
        quantity = _positive_quantity(item.get("quantity"))
        quantities[menu_item_id] = quantities.get(menu_item_id, 0) + quantity

    menu_items = {
        menu_item.id: menu_item
        for menu_item in MenuItem.query.filter(MenuItem.id.in_(quantities)).all()
    }
    missing_ids = set(quantities) - set(menu_items)
    if missing_ids:
        raise ValueError("Có món không tồn tại trong thực đơn.")

    validated = []
    for menu_item_id, quantity in quantities.items():
        menu_item = menu_items[menu_item_id]
        if not menu_item.is_available:
            raise ValueError(f'Món "{menu_item.name}" hiện không được phục vụ.')
        unit_price = Decimal(str(menu_item.price)).quantize(_CENT)
        subtotal = (unit_price * quantity).quantize(_CENT, rounding=ROUND_HALF_UP)
        validated.append((menu_item, quantity, unit_price, subtotal))
    return validated


def _validated_table(table_id):
    if table_id in (None, ""):
        return None
    identifier = _required_id(table_id, "Bàn")
    table = db.session.get(Table, identifier)
    if table is None:
        raise ValueError("Bàn được chọn không tồn tại.")
    return table


def create_order(items, table_id=None, description=None):
    try:
        validated_items = _validated_items(items)
        table = _validated_table(table_id)
        total_amount = sum(
            (subtotal for _, _, _, subtotal in validated_items), Decimal("0.00")
        ).quantize(_CENT, rounding=ROUND_HALF_UP)
        order = Order(
            order_code=_generate_order_code(),
            table=table,
            status="pending",
            total_amount=total_amount,
            description=_optional_text(description),
        )
        db.session.add(order)
        db.session.flush()
        for menu_item, quantity, unit_price, subtotal in validated_items:
            db.session.add(
                OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=quantity,
                    unit_price=unit_price,
                    subtotal=subtotal,
                )
            )
        _commit("Không thể tạo đơn hàng do mã đơn bị trùng hoặc dữ liệu không hợp lệ.")
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError(
            "Không thể tạo đơn hàng do mã đơn bị trùng hoặc dữ liệu không hợp lệ."
        ) from error
    except Exception:
        db.session.rollback()
        raise
    return order


def get_order(order_id):
    return _get_order(order_id)


def get_orders(search=None, status=None, table_id=None):
    query = Order.query.options(
        joinedload(Order.table),
        selectinload(Order.items).joinedload(OrderItem.menu_item),
    )
    search_term = search.strip() if isinstance(search, str) else ""
    if search_term:
        query = query.filter(Order.order_code.ilike(f"%{search_term}%"))
    if status not in (None, ""):
        query = query.filter(Order.status == _valid_status(status))
    if table_id not in (None, ""):
        table = _validated_table(table_id)
        query = query.filter(Order.table_id == table.id)
    return query.order_by(Order.created_at.desc(), Order.id.desc()).all()


def get_order_form_options():
    tables = Table.query.order_by(Table.name.asc()).all()
    menu_items = (
        MenuItem.query.filter_by(is_available=True).order_by(MenuItem.name.asc()).all()
    )
    return tables, menu_items


def update_order_status(order_id, status):
    order = _get_order(order_id)
    order.status = _valid_status(status)
    _commit("Không thể cập nhật trạng thái đơn hàng.")
    return order


def cancel_order(order_id):
    return update_order_status(order_id, "cancelled")