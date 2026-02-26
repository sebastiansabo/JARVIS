"""JARVIS CRM — Car Sales Database & Client Hub.

Admin-only module for importing and managing car dealership data
(NW new cars, GW used cars, Workleto leads, CRM clients).
Data is indexed into RAG for AI-powered queries.
"""
from flask import Blueprint

crm_bp = Blueprint('crm', __name__)

from . import routes  # noqa: E402, F401
