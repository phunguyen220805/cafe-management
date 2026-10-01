from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Ingredient, StockTransaction


_QUANTITY_SCALE = Decimal("0.001")
_MAX_QUANTITY = Decimal("999999999.999")


def _required_text(value, label):
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise ValueError(f"{label} không được để trống.")
    return text


def _optional_text(value):
    text = value.strip() if isinstance(value, str) else ""
    return text or None


def _quantity(value, label, *, allow_zero):
    try:
        parsed = Decimal(str(value).strip())
        if not parsed.is_finite():
            raise ValueError
        normalized = parsed.quantize(_QUANTITY_SCALE)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} phải là số thập phân hợp lệ.") from None

    if normalized != parsed:
        raise ValueError(f"{label} chỉ được có tối đa 3 chữ số thập phân.")
    if normalized < 0 or (not allow_zero and normalized == 0):
        comparison = "không âm" if allow_zero else "lớn hơn 0"
        raise ValueError(f"{label} phải {comparison}.")
    if normalized > _MAX_QUANTITY:
        raise ValueError(f"{label} vượt quá giới hạn lưu trữ.")
    return normalized


def _boolean(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower() if value is not None else ""
    if normalized in {"1", "true", "on", "yes", "active"}:
        return True
    if normalized in {"0", "false", "off", "no", "inactive", ""}:
        return False
    raise ValueError("Trạng thái nguyên liệu không hợp lệ.")


def _get_ingredient(ingredient_id):
    try:
        identifier = int(ingredient_id)
    except (TypeError, ValueError):
        raise ValueError("Nguyên liệu không hợp lệ.") from None
    if identifier <= 0:
        raise ValueError("Nguyên liệu không hợp lệ.")
    ingredient = db.session.get(Ingredient, identifier)
    if ingredient is None:
        raise ValueError("Không tìm thấy nguyên liệu.")
    return ingredient


def _commit(integrity_message="Không thể lưu thay đổi kho."):
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError(integrity_message) from error
    except Exception:
        db.session.rollback()
        raise


def create_ingredient(name, unit, min_quantity=Decimal("0.000"), description=None):
    name = _required_text(name, "Tên nguyên liệu")
    unit = _required_text(unit, "Đơn vị")
    min_quantity = _quantity(min_quantity, "Mức tồn tối thiểu", allow_zero=True)
    if Ingredient.query.filter_by(name=name).first() is not None:
        raise ValueError("Tên nguyên liệu đã tồn tại.")

    ingredient = Ingredient(
        name=name,
        unit=unit,
        quantity=Decimal("0.000"),
        min_quantity=min_quantity,
        description=_optional_text(description),
        is_active=True,
    )
    db.session.add(ingredient)
    _commit("Tên nguyên liệu đã tồn tại hoặc dữ liệu không hợp lệ.")
    return ingredient


def update_ingredient(
    ingredient_id,
    name,
    unit,
    min_quantity,
    description=None,
    is_active=True,
):
    ingredient = _get_ingredient(ingredient_id)
    name = _required_text(name, "Tên nguyên liệu")
    unit = _required_text(unit, "Đơn vị")
    min_quantity = _quantity(min_quantity, "Mức tồn tối thiểu", allow_zero=True)
    is_active = _boolean(is_active)

    if unit != ingredient.unit and StockTransaction.query.filter_by(
        ingredient_id=ingredient.id
    ).first() is not None:
        raise ValueError("Không thể đổi đơn vị khi nguyên liệu đã có lịch sử kho.")
    duplicate = Ingredient.query.filter(
        Ingredient.name == name, Ingredient.id != ingredient.id
    ).first()
    if duplicate is not None:
        raise ValueError("Tên nguyên liệu đã tồn tại.")

    ingredient.name = name
    ingredient.unit = unit
    ingredient.min_quantity = min_quantity
    ingredient.description = _optional_text(description)
    ingredient.is_active = is_active
    _commit("Tên nguyên liệu đã tồn tại hoặc dữ liệu không hợp lệ.")
    return ingredient


def delete_ingredient(ingredient_id):
    ingredient = _get_ingredient(ingredient_id)
    if StockTransaction.query.filter_by(ingredient_id=ingredient.id).first() is not None:
        raise ValueError("Không thể xóa nguyên liệu đã có lịch sử kho.")
    db.session.delete(ingredient)
    _commit("Không thể xóa nguyên liệu đã có lịch sử kho.")


def get_ingredients(search=None, is_active=None, low_stock=False):
    query = Ingredient.query
    search_term = search.strip() if isinstance(search, str) else ""
    if search_term:
        query = query.filter(Ingredient.name.ilike(f"%{search_term}%"))
    if is_active not in (None, ""):
        if isinstance(is_active, str) and is_active.strip().lower() in {
            "active",
            "inactive",
        }:
            active_filter = is_active.strip().lower() == "active"
        else:
            active_filter = _boolean(is_active)
        query = query.filter(Ingredient.is_active.is_(active_filter))
    if _boolean(low_stock):
        query = query.filter(Ingredient.quantity <= Ingredient.min_quantity)
    return query.order_by(Ingredient.name.asc()).all()


def get_ingredient(ingredient_id):
    return _get_ingredient(ingredient_id)


def _active_ingredient(ingredient_id):
    ingredient = _get_ingredient(ingredient_id)
    if not ingredient.is_active:
        raise ValueError("Nguyên liệu đã ngừng hoạt động.")
    return ingredient


def _movement(ingredient_id, quantity, note, transaction_type):
    try:
        ingredient = _active_ingredient(ingredient_id)
        amount = _quantity(quantity, "Số lượng", allow_zero=False)
        if transaction_type == "import":
            ingredient.quantity = _quantity(
                Decimal(str(ingredient.quantity)) + amount,
                "Tồn kho",
                allow_zero=True,
            )
        else:
            result = db.session.execute(
                update(Ingredient)
                .where(
                    Ingredient.id == ingredient.id,
                    Ingredient.is_active.is_(True),
                    Ingredient.quantity >= amount,
                )
                .values(
                    quantity=Ingredient.quantity - amount,
                    updated_at=datetime.now(timezone.utc),
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                db.session.rollback()
                raise ValueError("Số lượng xuất vượt quá tồn kho hiện tại.")

        transaction = StockTransaction(
            ingredient_id=ingredient.id,
            type=transaction_type,
            quantity=amount,
            note=_optional_text(note),
        )
        db.session.add(transaction)
        _commit("Không thể lưu giao dịch kho.")
        return transaction
    except Exception:
        db.session.rollback()
        raise


def import_stock(ingredient_id, quantity, note=None):
    return _movement(ingredient_id, quantity, note, "import")


def export_stock(ingredient_id, quantity, note=None):
    return _movement(ingredient_id, quantity, note, "export")


def get_stock_transactions(ingredient_id):
    ingredient = _get_ingredient(ingredient_id)
    return (
        StockTransaction.query.filter_by(ingredient_id=ingredient.id)
        .order_by(StockTransaction.created_at.desc(), StockTransaction.id.desc())
        .all()
    )


def get_ingredient_history(ingredient_id):
    return get_stock_transactions(ingredient_id)