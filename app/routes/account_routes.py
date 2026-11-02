from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import or_

from app.extensions import db
from app.models import User
from app.services.auth_service import (
    admin_required,
    create_user,
    update_user_profile,
    update_user_role,
    update_user_status,
)


account_bp = Blueprint("accounts", __name__)


@account_bp.route("/accounts", methods=["GET"])
@admin_required
def account_list():
    search = request.args.get("q", "").strip()
    role = request.args.get("role", "")
    status = request.args.get("status", "")
    query = User.query
    if search:
        query = query.filter(
            or_(User.username.ilike(f"%{search}%"), User.full_name.ilike(f"%{search}%"))
        )
    if role in User.ROLES:
        query = query.filter_by(role=role)
    else:
        role = ""
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "locked":
        query = query.filter_by(is_active=False)
    else:
        status = ""
    stats = {
        "total": User.query.count(),
        "admins": User.query.filter_by(role=User.ADMIN_ROLE).count(),
        "employees": User.query.filter_by(role=User.EMPLOYEE_ROLE).count(),
        "active": User.query.filter_by(is_active=True).count(),
    }
    return render_template(
        "accounts.html",
        users=query.order_by(User.username).all(),
        search=search,
        selected_role=role,
        selected_status=status,
        stats=stats,
        today=date.today(),
    )


@account_bp.route("/accounts/add", methods=["POST"])
@admin_required
def create_account():
    try:
        create_user(
            request.form.get("username"),
            request.form.get("password", ""),
            request.form.get("role", User.EMPLOYEE_ROLE),
            request.form.get("full_name"),
            request.form.get("date_of_birth"),
        )
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Đã tạo tài khoản.", "success")
    return redirect(url_for("accounts.account_list"))


@account_bp.route("/accounts/<int:user_id>/edit", methods=["POST"])
@admin_required
def edit_account(user_id):
    user = db.get_or_404(User, user_id)
    try:
        update_user_profile(
            user,
            request.form.get("full_name"),
            request.form.get("date_of_birth"),
            request.form.get("role"),
        )
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Đã cập nhật thông tin tài khoản.", "success")
    return redirect(url_for("accounts.account_list"))


@account_bp.route("/accounts/<int:user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    user = db.get_or_404(User, user_id)
    try:
        update_user_role(user, request.form.get("role"))
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Đã cập nhật vai trò.", "success")
    return redirect(url_for("accounts.account_list"))


@account_bp.route("/accounts/<int:user_id>/status", methods=["POST"])
@admin_required
def change_status(user_id):
    user = db.get_or_404(User, user_id)
    try:
        update_user_status(user, request.form.get("is_active") == "1")
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Đã cập nhật trạng thái tài khoản.", "success")
    return redirect(url_for("accounts.account_list"))
