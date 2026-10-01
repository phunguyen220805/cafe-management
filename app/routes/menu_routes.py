from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import menu_service


menu_bp = Blueprint("menu", __name__)


@menu_bp.route("/menu", methods=["GET"])
@login_required
def menu_page():
    search = request.args.get("q", "")
    category_id = request.args.get("category_id", "")
    try:
        menu_items = menu_service.get_menu_items(search, category_id)
    except ValueError as error:
        flash(str(error), "error")
        category_id = ""
        menu_items = menu_service.get_menu_items(search)

    return render_template(
        "menu.html",
        current_user=current_user,
        categories=menu_service.get_categories(),
        menu_items=menu_items,
        search=search,
        selected_category_id=category_id,
    )


def _run_action(action, success_message):
    try:
        action()
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash(success_message, "success")
    return redirect(url_for("menu.menu_page"))


@menu_bp.route("/menu/items/add", methods=["POST"])
@login_required
def create_menu_item():
    return _run_action(
        lambda: menu_service.create_menu_item(
            name=request.form.get("name"),
            category_id=request.form.get("category_id"),
            price=request.form.get("price"),
            description=request.form.get("description"),
            image=request.form.get("image"),
            is_available=request.form.get("is_available"),
        ),
        "Đã thêm món vào thực đơn.",
    )


@menu_bp.route("/menu/items/<int:item_id>/edit", methods=["POST"])
@login_required
def update_menu_item(item_id):
    return _run_action(
        lambda: menu_service.update_menu_item(
            menu_item_id=item_id,
            name=request.form.get("name"),
            category_id=request.form.get("category_id"),
            price=request.form.get("price"),
            description=request.form.get("description"),
            image=request.form.get("image"),
            is_available=request.form.get("is_available"),
        ),
        "Đã cập nhật món.",
    )


@menu_bp.route("/menu/items/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_menu_item(item_id):
    return _run_action(
        lambda: menu_service.delete_menu_item(item_id), "Đã xóa món khỏi thực đơn."
    )


@menu_bp.route("/menu/categories/add", methods=["POST"])
@login_required
def create_category():
    return _run_action(
        lambda: menu_service.create_category(
            request.form.get("name"), request.form.get("description")
        ),
        "Đã thêm danh mục.",
    )


@menu_bp.route("/menu/categories/<int:category_id>/edit", methods=["POST"])
@login_required
def update_category(category_id):
    return _run_action(
        lambda: menu_service.update_category(
            category_id,
            request.form.get("name"),
            request.form.get("description"),
        ),
        "Đã cập nhật danh mục.",
    )


@menu_bp.route("/menu/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id):
    return _run_action(
        lambda: menu_service.delete_category(category_id), "Đã xóa danh mục."
    )