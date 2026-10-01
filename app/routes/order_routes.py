from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.models.order import ORDER_STATUSES
from app.services import order_service


order_bp = Blueprint("orders", __name__)

STATUS_LABELS = {
    "pending": "Chờ xử lý",
    "preparing": "Đang pha chế",
    "completed": "Hoàn tất",
    "cancelled": "Đã hủy",
}


def _render_orders(detail_order_id=None):
    search = request.args.get("q", "")
    status = request.args.get("status", "")
    table_id = request.args.get("table_id", "")
    try:
        orders = order_service.get_orders(
            search=search, status=status, table_id=table_id
        )
    except ValueError as error:
        flash(str(error), "error")
        status = ""
        table_id = ""
        orders = order_service.get_orders(search=search)

    detail_order = None
    if detail_order_id is not None:
        try:
            detail_order = order_service.get_order(detail_order_id)
        except ValueError:
            abort(404)

    tables, menu_items = order_service.get_order_form_options()
    return render_template(
        "orders.html",
        orders=orders,
        tables=tables,
        menu_items=menu_items,
        search=search,
        selected_status=status,
        selected_table_id=table_id,
        statuses=ORDER_STATUSES,
        status_labels=STATUS_LABELS,
        detail_order=detail_order,
    )


def _run_action(action, success_message):
    try:
        action()
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash(success_message, "success")
    return redirect(url_for("orders.order_list"))


@order_bp.route("/orders", methods=["GET"])
@login_required
def order_list():
    return _render_orders()


@order_bp.route("/orders/<int:order_id>", methods=["GET"])
@login_required
def order_detail(order_id):
    return _render_orders(detail_order_id=order_id)


@order_bp.route("/orders/add", methods=["POST"])
@login_required
def create_order():
    selected_ids = request.form.getlist("menu_item_id")
    items = [
        {
            "menu_item_id": menu_item_id,
            "quantity": request.form.get(f"quantity_{menu_item_id}"),
        }
        for menu_item_id in selected_ids
    ]
    return _run_action(
        lambda: order_service.create_order(
            items=items,
            table_id=request.form.get("table_id"),
            description=request.form.get("description"),
        ),
        "Đã tạo đơn hàng.",
    )


@order_bp.route("/orders/<int:order_id>/status", methods=["POST"])
@login_required
def update_order_status(order_id):
    return _run_action(
        lambda: order_service.update_order_status(
            order_id, request.form.get("status")
        ),
        "Đã cập nhật trạng thái đơn hàng.",
    )


@order_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    return _run_action(
        lambda: order_service.cancel_order(order_id), "Đã hủy đơn hàng."
    )