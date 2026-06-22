"""Voucher module — issuance, approval, tracking, redemption."""
from flask import Blueprint

vouchers_bp = Blueprint('vouchers', __name__)

from .routes import crud, accounting as accounting_routes  # noqa: E402, F401
