from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.models.payment import PAYMENT_METHODS, PAYMENT_STATUSES
from app.services import payment_service


payment_bp = Blueprint("payments", __name__)

METHOD_LABELS = {"cash": "Tiền mặt", "transfer": "Chuyển khoản"}
STATUS_LABELS = {
    "pending": "Chờ thanh toán",
    "paid": "Đã thanh toán",
    "cancelled": "Đã hủy",
}


def _render_payments(payment_id=None):
    search = request.args.get("q", "")
    status = request.args.get("status", "")
    method = request.args.get("method", "")
    try:
        payments = payment_service.get_payments(
            search=search, status=status, method=method
        )
    except ValueError as error:
        flash(str(error), "error")
        status = ""
        method = ""
        payments = payment_service.get_payments(search=search)

    detail_payment = None
    if payment_id is not None:
        try:
            detail_payment = payment_service.get_payment(payment_id)
        except ValueError:
            abort(404)

    return render_template(
        "payments.html",
        payments=payments,
        payable_orders=payment_service.get_payable_orders(),
        search=search,
        selected_status=status,
        selected_method=method,
        statuses=PAYMENT_STATUSES,
        methods=PAYMENT_METHODS,
        status_labels=STATUS_LABELS,
        method_labels=METHOD_LABELS,
        detail_payment=detail_payment,
    )


def _run_action(action, success_message):
    try:
        action()
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash(success_message, "success")
    return redirect(url_for("payments.payment_list"))


@payment_bp.route("/payments", methods=["GET"])
@login_required
def payment_list():
    return _render_payments()


@payment_bp.route("/payments/<int:payment_id>", methods=["GET"])
@login_required
def payment_detail(payment_id):
    return _render_payments(payment_id=payment_id)


@payment_bp.route("/payments/add", methods=["POST"])
@login_required
def create_payment():
    return _run_action(
        lambda: payment_service.create_payment(
            order_id=request.form.get("order_id"),
            method=request.form.get("method"),
            transaction_code=request.form.get("transaction_code"),
        ),
        "Đã tạo yêu cầu thanh toán.",
    )


@payment_bp.route("/payments/<int:payment_id>/confirm", methods=["POST"])
@login_required
def confirm_payment(payment_id):
    return _run_action(
        lambda: payment_service.confirm_payment(
            payment_id,
            transaction_code=request.form.get("transaction_code"),
        ),
        "Đã xác nhận thanh toán.",
    )


@payment_bp.route("/payments/<int:payment_id>/cancel", methods=["POST"])
@login_required
def cancel_payment(payment_id):
    return _run_action(
        lambda: payment_service.cancel_payment(payment_id),
        "Đã hủy thanh toán.",
    )