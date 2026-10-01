from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.services import inventory_service


inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/inventory", methods=["GET"])
@login_required
def inventory_page():
    search = request.args.get("q", "")
    active_filter = request.args.get("active", "")
    low_stock = request.args.get("low_stock", "")
    try:
        ingredients = inventory_service.get_ingredients(
            search=search,
            is_active=active_filter,
            low_stock=low_stock,
        )
    except ValueError as error:
        flash(str(error), "error")
        active_filter = ""
        low_stock = ""
        ingredients = inventory_service.get_ingredients(search=search)

    return render_template(
        "inventory.html",
        ingredients=ingredients,
        search=search,
        selected_active=active_filter,
        low_stock=low_stock,
    )


def _run_action(action, success_message):
    try:
        action()
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash(success_message, "success")
    return redirect(url_for("inventory.inventory_page"))


@inventory_bp.route("/inventory/ingredients/add", methods=["POST"])
@login_required
def create_ingredient():
    return _run_action(
        lambda: inventory_service.create_ingredient(
            name=request.form.get("name"),
            unit=request.form.get("unit"),
            min_quantity=request.form.get("min_quantity", "0"),
            description=request.form.get("description"),
        ),
        "Đã thêm nguyên liệu.",
    )


@inventory_bp.route(
    "/inventory/ingredients/<int:ingredient_id>/edit", methods=["POST"]
)
@login_required
def update_ingredient(ingredient_id):
    return _run_action(
        lambda: inventory_service.update_ingredient(
            ingredient_id=ingredient_id,
            name=request.form.get("name"),
            unit=request.form.get("unit"),
            min_quantity=request.form.get("min_quantity"),
            description=request.form.get("description"),
            is_active=request.form.get("is_active"),
        ),
        "Đã cập nhật nguyên liệu.",
    )


@inventory_bp.route(
    "/inventory/ingredients/<int:ingredient_id>/delete", methods=["POST"]
)
@login_required
def delete_ingredient(ingredient_id):
    return _run_action(
        lambda: inventory_service.delete_ingredient(ingredient_id),
        "Đã xóa nguyên liệu.",
    )


@inventory_bp.route(
    "/inventory/ingredients/<int:ingredient_id>/import", methods=["POST"]
)
@login_required
def import_stock(ingredient_id):
    return _run_action(
        lambda: inventory_service.import_stock(
            ingredient_id,
            quantity=request.form.get("quantity"),
            note=request.form.get("note"),
        ),
        "Đã nhập kho nguyên liệu.",
    )


@inventory_bp.route(
    "/inventory/ingredients/<int:ingredient_id>/export", methods=["POST"]
)
@login_required
def export_stock(ingredient_id):
    return _run_action(
        lambda: inventory_service.export_stock(
            ingredient_id,
            quantity=request.form.get("quantity"),
            note=request.form.get("note"),
        ),
        "Đã xuất kho nguyên liệu.",
    )


@inventory_bp.route(
    "/inventory/ingredients/<int:ingredient_id>/history", methods=["GET"]
)
@login_required
def ingredient_history(ingredient_id):
    try:
        ingredient = inventory_service.get_ingredient(ingredient_id)
        transactions = inventory_service.get_ingredient_history(ingredient_id)
    except ValueError:
        abort(404)
    return render_template(
        "ingredient_history.html",
        ingredient=ingredient,
        transactions=transactions,
    )