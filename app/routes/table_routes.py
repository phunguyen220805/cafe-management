from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.models.table import TABLE_STATUSES
from app.services import table_service


table_bp = Blueprint("tables", __name__)

STATUS_LABELS = {
    "available": "Sẵn sàng",
    "occupied": "Đang sử dụng",
    "reserved": "Đã đặt",
    "maintenance": "Bảo trì",
}


@table_bp.route("/tables", methods=["GET"])
@login_required
def table_page():
    search = request.args.get("q", "")
    status = request.args.get("status", "")
    try:
        tables = table_service.get_tables(search=search, status=status)
    except ValueError as error:
        flash(str(error), "error")
        status = ""
        tables = table_service.get_tables(search=search)

    return render_template(
        "tables.html",
        tables=tables,
        search=search,
        selected_status=status,
        statuses=TABLE_STATUSES,
        status_labels=STATUS_LABELS,
    )


def _run_action(action, success_message):
    try:
        action()
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash(success_message, "success")
    return redirect(url_for("tables.table_page"))


@table_bp.route("/tables/add", methods=["POST"])
@login_required
def create_table():
    return _run_action(
        lambda: table_service.create_table(
            name=request.form.get("name"),
            capacity=request.form.get("capacity"),
            status=request.form.get("status", "available"),
            description=request.form.get("description"),
        ),
        "Đã thêm bàn.",
    )


@table_bp.route("/tables/<int:table_id>/edit", methods=["POST"])
@login_required
def update_table(table_id):
    return _run_action(
        lambda: table_service.update_table(
            table_id=table_id,
            name=request.form.get("name"),
            capacity=request.form.get("capacity"),
            status=request.form.get("status"),
            description=request.form.get("description"),
        ),
        "Đã cập nhật bàn.",
    )


@table_bp.route("/tables/<int:table_id>/delete", methods=["POST"])
@login_required
def delete_table(table_id):
    return _run_action(
        lambda: table_service.delete_table(table_id), "Đã xóa bàn."
    )