from flask import Blueprint, render_template
from flask_login import login_required

from app.services.dashboard_service import get_demo_dashboard


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def home():
    return render_template("home.html", dashboard=get_demo_dashboard())