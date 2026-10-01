from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Category, MenuItem, OrderItem


_CENT = Decimal("0.01")


def _required_name(value, label):
    name = value.strip() if isinstance(value, str) else ""
    if not name:
        raise ValueError(f"{label} không được để trống.")
    return name


def _optional_text(value):
    text = value.strip() if isinstance(value, str) else ""
    return text or None


def _positive_price(value):
    try:
        price = Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Giá món phải là số hợp lệ lớn hơn 0.") from None
    if not price.is_finite() or price <= 0:
        raise ValueError("Giá món phải lớn hơn 0.")
    return price


def _required_id(value, label):
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} không hợp lệ.") from None
    if identifier <= 0:
        raise ValueError(f"{label} không hợp lệ.")
    return identifier


def _availability(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "on", "yes"}:
        return True
    if normalized in {"0", "false", "off", "no", ""}:
        return False
    raise ValueError("Trạng thái món không hợp lệ.")


def _commit(duplicate_category_message=None):
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        if duplicate_category_message:
            raise ValueError(duplicate_category_message) from error
        raise
    except Exception:
        db.session.rollback()
        raise


def _get_category(category_id):
    identifier = _required_id(category_id, "Danh mục")
    category = db.session.get(Category, identifier)
    if category is None:
        raise ValueError("Danh mục không tồn tại.")
    return category


def _get_menu_item(menu_item_id):
    identifier = _required_id(menu_item_id, "Món")
    menu_item = db.session.get(MenuItem, identifier)
    if menu_item is None:
        raise ValueError("Món không tồn tại.")
    return menu_item


def create_category(name, description=None):
    name = _required_name(name, "Tên danh mục")
    if Category.query.filter_by(name=name).first() is not None:
        raise ValueError("Tên danh mục đã tồn tại.")

    category = Category(name=name, description=_optional_text(description))
    db.session.add(category)
    _commit("Tên danh mục đã tồn tại.")
    return category


def update_category(category_id, name, description=None):
    category = _get_category(category_id)
    name = _required_name(name, "Tên danh mục")
    duplicate = Category.query.filter(
        Category.name == name, Category.id != category.id
    ).first()
    if duplicate is not None:
        raise ValueError("Tên danh mục đã tồn tại.")

    category.name = name
    category.description = _optional_text(description)
    _commit("Tên danh mục đã tồn tại.")
    return category


def delete_category(category_id):
    category = _get_category(category_id)
    if MenuItem.query.filter_by(category_id=category.id).first() is not None:
        raise ValueError("Không thể xóa danh mục đang có món.")

    db.session.delete(category)
    _commit()


def get_categories():
    return Category.query.order_by(Category.name.asc()).all()


def create_menu_item(
    name,
    category_id,
    price,
    description=None,
    image=None,
    is_available=True,
):
    name = _required_name(name, "Tên món")
    category = _get_category(category_id)
    menu_item = MenuItem(
        name=name,
        category=category,
        price=_positive_price(price),
        description=_optional_text(description),
        image=_optional_text(image),
        is_available=_availability(is_available),
    )
    db.session.add(menu_item)
    _commit()
    return menu_item


def update_menu_item(
    menu_item_id,
    name,
    category_id,
    price,
    description=None,
    image=None,
    is_available=True,
):
    menu_item = _get_menu_item(menu_item_id)
    category = _get_category(category_id)
    menu_item.name = _required_name(name, "Tên món")
    menu_item.category = category
    menu_item.price = _positive_price(price)
    menu_item.description = _optional_text(description)
    menu_item.image = _optional_text(image)
    menu_item.is_available = _availability(is_available)
    _commit()
    return menu_item


def delete_menu_item(menu_item_id):
    menu_item = _get_menu_item(menu_item_id)
    if OrderItem.query.filter_by(menu_item_id=menu_item.id).first() is not None:
        raise ValueError("Không thể xóa món đang được sử dụng trong đơn hàng.")
    db.session.delete(menu_item)
    _commit("Không thể xóa món đang được sử dụng trong đơn hàng.")


def get_menu_items(search=None, category_id=None):
    query = MenuItem.query.options(joinedload(MenuItem.category))
    search_term = search.strip() if isinstance(search, str) else ""
    if search_term:
        pattern = f"%{search_term}%"
        query = query.filter(
            or_(MenuItem.name.ilike(pattern), MenuItem.description.ilike(pattern))
        )
    if category_id not in (None, ""):
        category = _get_category(category_id)
        query = query.filter(MenuItem.category_id == category.id)
    return query.order_by(MenuItem.name.asc()).all()