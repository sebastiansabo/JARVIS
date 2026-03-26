"""Forms Module — public forms with UTM tracking and approval integration."""
from flask import Blueprint

forms_bp = Blueprint('forms', __name__)

from .routes import forms, submissions, public  # noqa: E402, F401
