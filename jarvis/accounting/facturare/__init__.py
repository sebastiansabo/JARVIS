"""Facturare — Invoice & EuroFib Import Generator.

Generates batch invoice PDFs (FACTURA/PROFORMA) and EuroFib 'Note contabile'
import xlsx from Anexa xlsx + YAML config.
"""
from flask import Blueprint

facturare_bp = Blueprint('facturare', __name__)

from . import routes  # noqa: E402, F401
