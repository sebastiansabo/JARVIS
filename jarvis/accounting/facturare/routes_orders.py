"""Comenzi API routes — Contract → Anexa → Invoice lifecycle.

Endpoints:
  Contracts:  GET/POST /facturare/api/contracts
  Anexas:     GET/POST /facturare/api/contracts/<id>/anexas
  Lifecycle:  POST /facturare/api/invoices/proforma|invoice|storno|final
  Detail:     GET  /facturare/api/anexas/<id>
  Delete:     DELETE /facturare/api/invoices/<id>
  Users:      GET  /facturare/api/users?q=
  PDF:        GET  /facturare/api/invoices/<id>/pdf
"""
import logging
import time
from decimal import Decimal, InvalidOperation

from flask import jsonify, request
from flask_login import login_required, current_user

from . import facturare_bp
from .models import InvoiceTypeEnum
from .repositories.invoice_storage_repository import InvoiceStorageRepository
from .services.invoice_state_machine import InvoiceStateMachine, InvoiceStateMachineError
from .schemas import (
    ContractCreateRequest, AnexaCreateRequest, AnexaLineCreate,
    ProformaCreateRequest, InvoiceCreateRequest,
    StornoCreateRequest, FinalCreateRequest,
)
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

logger = logging.getLogger("jarvis.facturare.orders")
_repo = InvoiceStorageRepository()
_sm = InvoiceStateMachine(_repo)
_perm_repo = PermissionRepository()

TYPE_LABELS = {"PROFORMA": "Proforma", "INVOICE": "Factura", "STORNO": "Storno", "FINAL": "Final"}

# ── Document items cache (in-memory, per doc_type key) ──────────
_doc_items_cache: dict[str, tuple[float, list]] = {}  # key -> (timestamp, items)
_DOC_ITEMS_TTL = 60  # seconds

def _invalidate_doc_items_cache():
    _doc_items_cache.clear()


def _check_perm(action: str) -> bool:
    if not current_user or not current_user.is_authenticated:
        return False
    role_id = getattr(current_user, "role_id", None)
    if not role_id:
        return getattr(current_user, "can_access_accounting", False)
    perm = _perm_repo.check_permission_v2(role_id, "facturare", "records", action)
    if perm is not None:
        return perm
    perm = _perm_repo.check_permission_v2(role_id, "invoices", "records", action)
    if perm is not None:
        return perm
    return getattr(current_user, "can_access_accounting", False)


def _inv_to_dict(row):
    return {
        "id": row["id"], "anexa_id": row["anexa_id"],
        "invoice_type": row["invoice_type"], "invoice_state": row["invoice_state"],
        "sequence_number": row.get("sequence_number", 1),
        "invoice_number": row.get("invoice_number"),
        "issued_date": str(row["issued_date"]) if row.get("issued_date") else None,
        "total_amount_eur": float(row["total_amount_eur"]),
        "total_amount_ron": float(row["total_amount_ron"]),
        "kurs_applied": float(row["kurs_applied"]) if row.get("kurs_applied") else None,
        "currency": row["currency"],
        "intocmit_de": row.get("intocmit_de"),
        "notes": row.get("notes"),
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
    }


def _line_to_dict(row):
    return {
        "id": row["id"], "line_number": row["line_number"],
        "nr_comanda": row.get("nr_comanda"), "vin": row.get("vin"),
        "model": row["model"], "culoare": row.get("culoare"),
        "list_price_eur": float(row["list_price_eur"]),
        "selling_price_eur": float(row["selling_price_eur"]),
        "qty": row["qty"],
    }


# ── Contracts ────────────────────────────────────────────────────

@facturare_bp.route("/facturare/api/contracts")
@login_required
@handle_api_errors
def api_list_contracts():
    if not _check_perm("view"):
        return error_response("Permission denied", 403)
    rows = _repo.list_contracts()
    contracts = []
    for r in rows:
        contracts.append({
            "id": r["id"], "contract_ref": r["contract_ref"],
            "supplier_id": r["supplier_id"], "customer_id": r["customer_id"],
            "supplier_name": r.get("supplier_name", ""),
            "customer_name": r.get("customer_name", ""),
            "contract_date": str(r["contract_date"]) if r.get("contract_date") else None,
            "responsible": r.get("responsible"),
            "anexa_count": r.get("anexa_count", 0),
            "total_value": float(r.get("total_value", 0) or 0),
            "invoiced_total": float(r.get("invoiced_total", 0) or 0),
            "notes": r.get("notes"),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
        })
    return jsonify({"contracts": contracts})


@facturare_bp.route("/facturare/api/contracts", methods=["POST"])
@login_required
@handle_api_errors
def api_create_contract():
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    data = request.get_json(force=True)
    try:
        req = ContractCreateRequest(**data)
    except Exception as e:
        return error_response(str(e))
    row = _repo.create_contract(
        contract_ref=req.contract_ref, supplier_id=req.supplier_id,
        customer_id=req.customer_id, contract_date=req.contract_date,
        responsible=req.responsible, notes=req.notes, created_by=current_user.id,
    )
    return jsonify({"success": True, "contract": {"id": row["id"], "contract_ref": row["contract_ref"]}}), 201


@facturare_bp.route("/facturare/api/contracts/<int:contract_id>", methods=["DELETE"])
@login_required
@handle_api_errors
def api_delete_contract(contract_id):
    if not _check_perm("delete"):
        return error_response("Permission denied", 403)
    anexas = _repo.list_anexas_by_contract(contract_id)
    if anexas:
        return error_response("Cannot delete contract with existing anexas. Delete anexas first.", 409)
    _repo.delete_contract(contract_id)
    return jsonify({"success": True})


# ── Anexas ───────────────────────────────────────────────────────

@facturare_bp.route("/facturare/api/contracts/<int:contract_id>/anexas")
@login_required
@handle_api_errors
def api_list_anexas(contract_id):
    if not _check_perm("view"):
        return error_response("Permission denied", 403)
    contract = _repo.get_contract_by_id(contract_id)
    if not contract:
        return error_response("Contract not found", 404)

    anexas = _repo.list_anexas_by_contract(contract_id)
    result = []
    for a in anexas:
        lines = _repo.get_lines_by_anexa(a["id"])
        invoices = _repo.get_invoices_by_anexa(a["id"])
        total_value = sum(float(l["selling_price_eur"]) for l in lines)

        types = list({inv["invoice_type"] for inv in invoices})
        if "FINAL" in types:
            stage = "COMPLETE"
        elif "STORNO" in types:
            stage = "STORNO"
        elif "INVOICE" in types:
            stage = "INVOICE"
        elif "PROFORMA" in types:
            stage = "PROFORMA"
        else:
            stage = "NEW"

        proformas_total = sum(float(inv["total_amount_eur"]) for inv in invoices if inv["invoice_type"] == "PROFORMA")
        invoiced_total = sum(float(inv["total_amount_eur"]) for inv in invoices if inv["invoice_type"] == "INVOICE")
        pct_proforma = round((proformas_total / total_value * 100), 1) if total_value else 0
        pct_invoiced = round((invoiced_total / total_value * 100), 1) if total_value else 0

        result.append({
            "id": a["id"], "anexa_number": a["anexa_number"],
            "notes": a.get("notes"),
            "line_count": len(lines), "total_value": total_value,
            "proformas_total": proformas_total, "invoiced_total": invoiced_total,
            "pct_proforma": pct_proforma, "pct_invoiced": pct_invoiced,
            "invoice_count": len(invoices), "stage": stage, "types": types,
            "created_at": str(a["created_at"]) if a.get("created_at") else None,
        })
    return jsonify({"anexas": result, "contract": {
        "id": contract["id"], "contract_ref": contract["contract_ref"],
        "supplier_id": contract["supplier_id"], "customer_id": contract["customer_id"],
    }})


@facturare_bp.route("/facturare/api/contracts/<int:contract_id>/anexas", methods=["POST"])
@login_required
@handle_api_errors
def api_create_anexa(contract_id):
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    contract = _repo.get_contract_by_id(contract_id)
    if not contract:
        return error_response("Contract not found", 404)

    data = request.get_json(force=True)
    data["contract_id"] = contract_id
    try:
        req = AnexaCreateRequest(**data)
    except Exception as e:
        return error_response(str(e))

    # Check uniqueness
    existing = _repo.get_anexa_by_contract_and_number(contract_id, req.anexa_number)
    if existing:
        return error_response(f"Anexa {req.anexa_number} already exists for this contract", 409)

    anexa_row = _repo.create_anexa(
        contract_id=contract_id, anexa_number=req.anexa_number,
        notes=req.notes, created_by=current_user.id,
    )

    for idx, line in enumerate(req.lines, start=1):
        _repo.create_anexa_line(
            anexa_id=anexa_row["id"], line_number=idx,
            model=line.model, list_price_eur=line.list_price_eur,
            selling_price_eur=line.selling_price_eur, qty=line.qty,
            nr_comanda=line.nr_comanda, vin=line.vin, culoare=line.culoare,
        )

    return jsonify({"success": True, "anexa": {"id": anexa_row["id"], "anexa_number": anexa_row["anexa_number"]}}), 201


# ── Anexa import from Excel ───────────────────────────────────────

@facturare_bp.route("/facturare/api/contracts/<int:contract_id>/anexas/import", methods=["POST"])
@login_required
@handle_api_errors
def api_import_anexa(contract_id):
    """Create an Anexa by importing vehicles from an Anexa XLSX file."""
    from .loaders.anexa import load_anexa

    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    contract = _repo.get_contract_by_id(contract_id)
    if not contract:
        return error_response("Contract not found", 404)

    anexa_file = request.files.get("anexa")
    if not anexa_file:
        return error_response("File required")

    anexa_number = request.form.get("anexa_number")
    if not anexa_number:
        return error_response("anexa_number required")

    notes = request.form.get("notes") or None

    # Check uniqueness
    existing = _repo.get_anexa_by_contract_and_number(contract_id, int(anexa_number))
    if existing:
        return error_response(f"Anexa {anexa_number} already exists for this contract", 409)

    try:
        order_lines = load_anexa(anexa_file.read())
    except ValueError as e:
        return error_response(f"Parse error: {e}")

    anexa_row = _repo.create_anexa(
        contract_id=contract_id, anexa_number=int(anexa_number),
        notes=notes, created_by=current_user.id,
    )

    for idx, ol in enumerate(order_lines, start=1):
        _repo.create_anexa_line(
            anexa_id=anexa_row["id"], line_number=idx,
            model=ol.model, list_price_eur=Decimal(str(ol.list_price or 0)),
            selling_price_eur=Decimal(str(ol.selling_price or 0)),
            qty=ol.qty,
            nr_comanda=str(ol.comanda) if ol.comanda else None,
            vin=ol.vin, culoare=ol.culoare,
        )

    return jsonify({
        "success": True,
        "anexa": {"id": anexa_row["id"], "anexa_number": anexa_row["anexa_number"]},
        "lines_imported": len(order_lines),
    }), 201


# ── Delete anexa (only if no invoices) ───────────────────────────

@facturare_bp.route("/facturare/api/anexas/<int:anexa_id>", methods=["DELETE"])
@login_required
@handle_api_errors
def api_delete_anexa(anexa_id):
    """Delete an anexa. Only allowed if no invoices have been issued."""
    if not _check_perm("delete"):
        return error_response("Permission denied", 403)
    anexa = _repo.get_anexa_by_id(anexa_id)
    if not anexa:
        return error_response("Anexa not found", 404)
    invoices = _repo.get_invoices_by_anexa(anexa_id)
    if invoices:
        return error_response("Cannot delete anexa — invoices already exist. Delete all invoices first.", 409)
    _repo.delete_anexa(anexa_id)
    return jsonify({"success": True})


# ── Anexa line CRUD ──────────────────────────────────────────────

@facturare_bp.route("/facturare/api/anexa-lines", methods=["POST"])
@login_required
@handle_api_errors
def api_create_anexa_line():
    """Add a vehicle to an existing anexa (only if no invoices yet)."""
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    data = request.get_json(force=True)
    anexa_id = data.get("anexa_id")
    if not anexa_id:
        return error_response("anexa_id required")

    # Check no invoices exist
    invoices = _repo.get_invoices_by_anexa(int(anexa_id))
    if invoices:
        return error_response("Cannot add vehicles after invoices have been issued", 409)

    row = _repo.create_anexa_line(
        anexa_id=int(anexa_id),
        line_number=int(data.get("line_number", 1)),
        model=data.get("model", ""),
        list_price_eur=Decimal(str(data.get("list_price_eur", 0))),
        selling_price_eur=Decimal(str(data.get("selling_price_eur", 0))),
        qty=1,
        nr_comanda=data.get("nr_comanda"),
        vin=data.get("vin"),
        culoare=data.get("culoare"),
    )
    return jsonify({"success": True, "line": _line_to_dict(row)}), 201


@facturare_bp.route("/facturare/api/anexa-lines/<int:line_id>", methods=["DELETE"])
@login_required
@handle_api_errors
def api_delete_anexa_line(line_id):
    """Delete a vehicle from an anexa (only if no invoices yet)."""
    if not _check_perm("delete"):
        return error_response("Permission denied", 403)

    # Find the line's anexa and check for invoices
    line_row = _repo.query_one("SELECT * FROM facturare_anexa_lines WHERE id = %s", (line_id,))
    if not line_row:
        return error_response("Line not found", 404)

    invoices = _repo.get_invoices_by_anexa(line_row["anexa_id"])
    if invoices:
        return error_response("Cannot remove vehicles after invoices have been issued", 409)

    _repo.execute("DELETE FROM facturare_anexa_lines WHERE id = %s", (line_id,))
    return jsonify({"success": True})


# ── Anexa line update (VIN, etc.) ────────────────────────────────

@facturare_bp.route("/facturare/api/anexa-lines/<int:line_id>", methods=["PATCH"])
@login_required
@handle_api_errors
def api_update_anexa_line(line_id):
    """Update an anexa line (e.g., add VIN)."""
    if not _check_perm("edit"):
        return error_response("Permission denied", 403)
    data = request.get_json(force=True)
    if not data:
        return error_response("Request body required")

    allowed_fields = {"vin", "nr_comanda", "culoare", "model", "selling_price_eur", "list_price_eur"}
    updates = {k: v for k, v in data.items() if k in allowed_fields}
    if not updates:
        return error_response("No valid fields to update")

    row = _repo.update_anexa_line(line_id, **updates)
    if not row:
        return error_response("Line not found", 404)
    return jsonify({"success": True, "line": _line_to_dict(row)})


# ── Anexa detail ─────────────────────────────────────────────────

@facturare_bp.route("/facturare/api/anexas/<int:anexa_id>")
@login_required
@handle_api_errors
def api_get_anexa_detail(anexa_id):
    if not _check_perm("view"):
        return error_response("Permission denied", 403)

    anexa = _repo.get_anexa_by_id(anexa_id)
    if not anexa:
        return error_response("Anexa not found", 404)

    contract = _repo.get_contract_by_id(anexa["contract_id"])
    lines = [_line_to_dict(l) for l in _repo.get_lines_by_anexa(anexa_id)]
    invoices = [_inv_to_dict(inv) for inv in _repo.get_invoices_by_anexa(anexa_id)]
    next_actions = _sm.get_next_actions(anexa_id)
    unpaired = [
        {"sequence_number": r["sequence_number"], "total_amount_eur": float(r["total_amount_eur"]),
         "invoice_number": r.get("invoice_number")}
        for r in _sm.get_unpaired_proformas(anexa_id)
    ]

    # Get names
    sup = _repo.query_one("SELECT company FROM companies WHERE id = %s", (contract["supplier_id"],))
    cust = _repo.query_one("SELECT display_name FROM crm_clients WHERE id = %s", (contract["customer_id"],))

    # Compute remaining proforma capacity
    raw_lines = _repo.get_lines_by_anexa(anexa_id)
    anexa_total = sum(float(l["selling_price_eur"]) for l in raw_lines)
    proformas_total = sum(inv["total_amount_eur"] for inv in _repo.get_invoices_by_anexa(anexa_id) if inv["invoice_type"] == "PROFORMA")
    remaining_eur = anexa_total - float(proformas_total)

    return jsonify({
        "anexa_id": anexa_id,
        "anexa_number": anexa["anexa_number"],
        "contract_ref": contract["contract_ref"],
        "supplier_name": sup["company"] if sup else "",
        "customer_name": cust["display_name"] if cust else "",
        "lines": lines,
        "invoices": invoices,
        "next_actions": next_actions,
        "unpaired_proformas": unpaired,
        "anexa_total_eur": anexa_total,
        "proformas_total_eur": float(proformas_total),
        "remaining_eur": remaining_eur,
    })


# ── Invoice lifecycle endpoints ──────────────────────────────────

@facturare_bp.route("/facturare/api/invoices/proforma", methods=["POST"])
@login_required
@handle_api_errors
def api_issue_proforma():
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    data = request.get_json(force=True)
    try:
        req = ProformaCreateRequest(**data)
    except Exception as e:
        return error_response(str(e))
    try:
        inv = _sm.issue_proforma(
            anexa_id=req.anexa_id, amount_eur=req.amount_eur,
            split_mode=req.split_mode,
            invoice_number=req.invoice_number, issued_date=req.issued_date,
            intocmit_de=req.intocmit_de, notes=req.notes,
            created_by_user_id=current_user.id,
        )
    except InvoiceStateMachineError as e:
        return error_response(str(e), 409)
    _invalidate_doc_items_cache()
    return jsonify({"success": True, "invoice": _inv_to_dict(_repo.get_invoice_by_id(inv.id))}), 201


@facturare_bp.route("/facturare/api/invoices/invoice", methods=["POST"])
@login_required
@handle_api_errors
def api_issue_invoice():
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    data = request.get_json(force=True)
    try:
        req = InvoiceCreateRequest(**data)
    except Exception as e:
        return error_response(str(e))
    try:
        inv = _sm.issue_invoice(
            anexa_id=req.anexa_id, sequence_number=req.sequence_number,
            invoice_number=req.invoice_number, issued_date=req.issued_date,
            intocmit_de=req.intocmit_de, notes=req.notes,
            created_by_user_id=current_user.id,
        )
    except InvoiceStateMachineError as e:
        return error_response(str(e), 409)
    _invalidate_doc_items_cache()
    return jsonify({"success": True, "invoice": _inv_to_dict(_repo.get_invoice_by_id(inv.id))}), 201


@facturare_bp.route("/facturare/api/invoices/storno", methods=["POST"])
@login_required
@handle_api_errors
def api_issue_storno():
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    data = request.get_json(force=True)
    try:
        req = StornoCreateRequest(**data)
    except Exception as e:
        return error_response(str(e))
    try:
        inv = _sm.issue_storno(
            anexa_id=req.anexa_id, invoice_number=req.invoice_number,
            issued_date=req.issued_date, intocmit_de=req.intocmit_de,
            notes=req.notes, created_by_user_id=current_user.id,
        )
    except InvoiceStateMachineError as e:
        return error_response(str(e), 409)
    _invalidate_doc_items_cache()
    return jsonify({"success": True, "invoice": _inv_to_dict(_repo.get_invoice_by_id(inv.id))}), 201


@facturare_bp.route("/facturare/api/invoices/final", methods=["POST"])
@login_required
@handle_api_errors
def api_issue_final():
    if not _check_perm("add"):
        return error_response("Permission denied", 403)
    data = request.get_json(force=True)
    try:
        req = FinalCreateRequest(**data)
    except Exception as e:
        return error_response(str(e))
    try:
        inv = _sm.issue_final(
            anexa_id=req.anexa_id, invoice_number=req.invoice_number,
            issued_date=req.issued_date, intocmit_de=req.intocmit_de,
            notes=req.notes, created_by_user_id=current_user.id,
        )
    except InvoiceStateMachineError as e:
        return error_response(str(e), 409)
    _invalidate_doc_items_cache()
    return jsonify({"success": True, "invoice": _inv_to_dict(_repo.get_invoice_by_id(inv.id))}), 201


# ── Delete invoice (last only) ───────────────────────────────────

@facturare_bp.route("/facturare/api/invoices/<int:invoice_id>", methods=["DELETE"])
@login_required
@handle_api_errors
def api_delete_invoice(invoice_id):
    if not _check_perm("delete"):
        return error_response("Permission denied", 403)
    inv_row = _repo.get_invoice_by_id(invoice_id)
    if not inv_row:
        return error_response("Invoice not found", 404)

    all_invs = _repo.get_invoices_by_anexa(inv_row["anexa_id"])
    if not all_invs:
        return error_response("No invoices found", 404)

    last = all_invs[-1]
    if last["id"] != invoice_id:
        return error_response(
            f'Only the last document can be deleted. Delete "{TYPE_LABELS.get(last["invoice_type"], last["invoice_type"])} '
            f'#{last.get("sequence_number", 1)}" first.', 409)

    _repo.delete_invoice(invoice_id)
    _invalidate_doc_items_cache()
    return jsonify({"success": True})


# ── User search ──────────────────────────────────────────────────

@facturare_bp.route("/facturare/api/users")
@login_required
@handle_api_errors
def api_search_users():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"users": []})
    rows = _repo.query_all(
        "SELECT id, name FROM users WHERE is_active = TRUE AND name ILIKE %s ORDER BY name LIMIT 10",
        (f"%{q}%",))
    return jsonify({"users": [{"id": r["id"], "name": r["name"]} for r in rows]})


# ── Individual document items (per car) ──────────────────────────

@facturare_bp.route("/facturare/api/document-items")
@login_required
@handle_api_errors
def api_document_items():
    """List individual per-car document items.

    Query params:
        type: PROFORMA or INVOICE (required)

    Returns one row per car per document, with calculated per-car amount.
    """
    if not _check_perm("view"):
        return error_response("Permission denied", 403)

    doc_types_raw = request.args.get("type", "").upper()
    allowed = {"PROFORMA", "INVOICE", "STORNO", "FINAL"}
    doc_types = [t.strip() for t in doc_types_raw.split(",") if t.strip() in allowed]
    if not doc_types:
        return error_response("type must be PROFORMA, INVOICE, STORNO or comma-separated")

    cache_key = ",".join(sorted(doc_types))
    cached = _doc_items_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _DOC_ITEMS_TTL:
        return jsonify({"items": cached[1], "total": len(cached[1])})

    placeholders = ",".join(["%s"] * len(doc_types))
    rows = _repo.query_all(
        f"""SELECT i.id AS invoice_id, i.invoice_type, i.sequence_number,
                  i.invoice_number, i.issued_date, i.total_amount_eur,
                  i.kurs_applied, i.intocmit_de, i.split_mode, i.notes,
                  a.id AS anexa_id, a.anexa_number,
                  c.id AS contract_id, c.contract_ref,
                  c.supplier_id, c.customer_id,
                  comp.company AS supplier_name,
                  cl.display_name AS customer_name
           FROM facturare_invoices i
           JOIN facturare_anexas a ON a.id = i.anexa_id
           JOIN facturare_contracts c ON c.id = a.contract_id
           JOIN companies comp ON comp.id = c.supplier_id
           JOIN crm_clients cl ON cl.id = c.customer_id
           WHERE i.invoice_type IN ({placeholders})
           ORDER BY i.issued_date DESC, i.id DESC""",
        tuple(doc_types),
    )

    items = []
    for inv in rows:
        lines = _repo.get_lines_by_anexa(inv["anexa_id"])
        total_selling = sum(float(l["selling_price_eur"]) for l in lines) or 1
        total_amount = float(inv["total_amount_eur"])
        split_mode = inv.get("split_mode", "equal")
        start_no = inv.get("invoice_number") or inv["invoice_id"]

        for idx, l in enumerate(lines):
            selling = float(l["selling_price_eur"])
            if split_mode == "proportional" and total_selling > 0:
                car_amount = total_amount * (selling / total_selling)
            else:
                car_amount = total_amount / max(len(lines), 1)

            items.append({
                "invoice_id": inv["invoice_id"],
                "invoice_type": inv["invoice_type"],
                "sequence_number": inv["sequence_number"],
                "doc_number": start_no + idx if start_no else None,
                "car_index": idx,
                "issued_date": str(inv["issued_date"]) if inv.get("issued_date") else None,
                "kurs_applied": float(inv["kurs_applied"]) if inv.get("kurs_applied") else None,
                "intocmit_de": inv.get("intocmit_de"),
                "contract_ref": inv["contract_ref"],
                "anexa_number": inv["anexa_number"],
                "supplier_name": inv["supplier_name"],
                "customer_name": inv["customer_name"],
                "nr_comanda": l.get("nr_comanda"),
                "model": l["model"],
                "culoare": l.get("culoare"),
                "vin": l.get("vin"),
                "unit_price": selling,
                "doc_amount": round(car_amount, 2),
                "notes": inv.get("notes"),
            })

    _doc_items_cache[cache_key] = (time.time(), items)
    return jsonify({"items": items, "total": len(items)})


# ── PDF generation ───────────────────────────────────────────────

@facturare_bp.route("/facturare/api/invoices/<int:invoice_id>/pdf")
@login_required
@handle_api_errors
def api_generate_pdf(invoice_id):
    from flask import send_file
    from .generators.proforma_pdf import ProformaPdfRenderer
    from .models import OrderLine
    from datetime import date as date_type
    import io

    if not _check_perm("view"):
        return error_response("Permission denied", 403)

    inv_row = _repo.get_invoice_by_id(invoice_id)
    if not inv_row:
        return error_response("Invoice not found", 404)

    anexa = _repo.get_anexa_by_id(inv_row["anexa_id"])
    contract = _repo.get_contract_by_id(anexa["contract_id"])
    lines = _repo.get_lines_by_anexa(anexa["id"])

    # Build supplier/customer dicts
    sup_row = _repo.query_one(
        "SELECT company, vat, reg_no, iban, bank, swift, street, city, county FROM companies WHERE id = %s",
        (contract["supplier_id"],))
    cust_row = _repo.query_one(
        "SELECT display_name, nr_reg, street, city, country FROM crm_clients WHERE id = %s",
        (contract["customer_id"],))

    supplier = {
        "name": sup_row["company"] if sup_row else "",
        "address_lines": [sup_row.get("street"), f"{sup_row.get('city')}, jud. {sup_row.get('county')}" if sup_row.get("city") else None, "Romania"] if sup_row else [],
        "vat": (sup_row or {}).get("vat", ""), "reg_no": (sup_row or {}).get("reg_no", ""),
        "iban": ((sup_row or {}).get("iban") or "").split("+")[0].strip(),
        "bank": ((sup_row or {}).get("bank") or "").split(";")[0].strip(),
        "swift": (sup_row or {}).get("swift", ""),
    }
    supplier["address_lines"] = [a for a in supplier["address_lines"] if a]

    customer = {
        "name": cust_row["display_name"] if cust_row else "",
        "address_lines": [a for a in [(cust_row or {}).get("street"), (cust_row or {}).get("city"), (cust_row or {}).get("country")] if a],
        "vat": (cust_row or {}).get("nr_reg", ""),
    }

    inv_type_str = inv_row["invoice_type"]

    if inv_type_str == "STORNO":
        # Build per-car groups: each car gets a list of its reversed invoice items
        reversed_invoices = _repo.query_all(
            "SELECT invoice_number, issued_date, total_amount_eur, sequence_number, split_mode "
            "FROM facturare_invoices WHERE anexa_id = %s AND invoice_type = 'INVOICE' "
            "ORDER BY sequence_number",
            (anexa["id"],))
        total_selling = sum(float(l["selling_price_eur"]) for l in lines) or 1
        # storno_groups[car_idx] = list of OrderLine (one per reversed invoice)
        storno_groups = []
        for car in lines:
            selling = float(car["selling_price_eur"])
            car_items = []
            for ri in reversed_invoices:
                ri_total = float(ri["total_amount_eur"])
                ri_split = ri.get("split_mode") or "equal"
                ri_no = ri.get("invoice_number")
                ri_date = ri.get("issued_date")
                date_fmt = ri_date.strftime("%d.%m.%Y") if hasattr(ri_date, "strftime") else str(ri_date or "")
                storno_ref = f"INVOICE {ri_no}/{date_fmt}" if ri_no else f"Invoice seq.{ri['sequence_number']}"
                if ri_split == "proportional" and total_selling > 0:
                    car_amount = ri_total * (selling / total_selling)
                else:
                    car_amount = ri_total / max(len(lines), 1)
                car_items.append(OrderLine(
                    comanda=int(car["nr_comanda"]) if car.get("nr_comanda") and str(car["nr_comanda"]).isdigit() else 0,
                    model=car.get("model", ""),
                    culoare=car.get("culoare") or "",
                    list_price=float(car["list_price_eur"]) if car.get("list_price_eur") else None,
                    selling_price=selling,
                    advance=-car_amount,
                    rest=None,
                    vin=car.get("vin"),
                    qty=1,
                    storno_description=storno_ref,
                    anexa_ref=f"Anexa {anexa['anexa_number']} / Contract {contract['contract_ref']}",
                ))
            storno_groups.append(car_items)
        order_lines = []  # not used for storno, kept for variable scope
    else:
        # Per-car order lines
        total_amount = float(inv_row["total_amount_eur"])
        split_mode = inv_row.get("split_mode", "equal")
        total_selling = sum(float(l["selling_price_eur"]) for l in lines) or 1

        order_lines = []
        for l in lines:
            selling = float(l["selling_price_eur"])
            if split_mode == "proportional" and total_selling > 0:
                car_advance = total_amount * (selling / total_selling)
            else:
                car_advance = total_amount / max(len(lines), 1)

            order_lines.append(OrderLine(
                comanda=int(l["nr_comanda"]) if l.get("nr_comanda") and str(l["nr_comanda"]).isdigit() else 0,
                model=l["model"], culoare=l.get("culoare") or "",
                list_price=float(l["list_price_eur"]), selling_price=selling,
                advance=car_advance,
                rest=selling, vin=l.get("vin"), qty=l.get("qty", 1),
                anexa_ref=f"Anexa {anexa['anexa_number']} / Contract {contract['contract_ref']}",
            ))

    issued_date = inv_row.get("issued_date")
    date_str = str(issued_date) if issued_date else date_type.today().strftime("%Y-%m-%d")
    start_no = inv_row.get("invoice_number") or inv_row["id"]
    cust_name = (cust_row["display_name"] if cust_row else "")
    if inv_type_str == "PROFORMA":
        filename = f"Proforma {cust_name} {start_no}"
    else:
        type_label = {"INVOICE": "advance", "STORNO": "storno", "FINAL": "final"}.get(inv_type_str, "")
        filename = f"Invoice {cust_name} {start_no} {type_label}"

    title_map = {
        "PROFORMA": ["FACTURA PROFORMA", "PROFORMA INVOICE"],
        "INVOICE":  ["FACTURA", "INVOICE"],
        "STORNO":   ["FACTURA STORNO", "STORNO INVOICE"],
        "FINAL":    ["FACTURA", "INVOICE"],
    }
    desc_map = {
        "PROFORMA": "1. ADVANCE PAYMENT",
        "INVOICE":  "1. ADVANCE PAYMENT",
        "STORNO":   "1. STORNO ADVANCE",
        "FINAL":    "",
    }

    renderer = ProformaPdfRenderer(
        supplier=supplier, customer=customer,
        invoice_date=date_str,
        intocmit_de=inv_row.get("intocmit_de") or "",
        title_lines=title_map.get(inv_type_str, ["FACTURA", "INVOICE"]),
        description_prefix=desc_map.get(inv_type_str, "1."),
        note=inv_row.get("notes") or "",
    )

    mode = request.args.get("mode", "merged")


    # STORNO: one page per car, each page lists all reversed invoices for that car
    if inv_type_str == "STORNO":
        car_idx = request.args.get("car")
        if car_idx is not None and car_idx.isdigit():
            idx = int(car_idx)
            if 0 <= idx < len(storno_groups):
                pdf_bytes = renderer.render_storno_multipage([storno_groups[idx]], start_no + idx)
                return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=f"{filename}_{start_no + idx}.pdf")
        pdf_bytes = renderer.render_storno_multipage(storno_groups, start_no)
        return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=f"{filename}.pdf")

    # Single car PDF via ?car=N
    car_idx = request.args.get("car")
    if car_idx is not None and car_idx.isdigit():
        idx = int(car_idx)
        if 0 <= idx < len(order_lines):
            line = order_lines[idx]
            inv_no = start_no + idx
            single_buf = io.BytesIO()
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as rc
            c = rc.Canvas(single_buf, pagesize=A4)
            renderer.render_one(c, inv_no, line)
            c.showPage()
            c.save()
            return send_file(io.BytesIO(single_buf.getvalue()), mimetype="application/pdf", as_attachment=True,
                             download_name=f"{filename}_{inv_no}.pdf")

    if mode == "individual" and len(order_lines) > 1:
        import zipfile
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, line in enumerate(order_lines):
                inv_no = start_no + i
                single_buf = io.BytesIO()
                from reportlab.lib.pagesizes import A4
                from reportlab.pdfgen import canvas as rc
                c = rc.Canvas(single_buf, pagesize=A4)
                renderer.render_one(c, inv_no, line)
                c.showPage()
                c.save()
                fname = f"{filename}_{inv_no}_{line.model.replace(' ', '_')}.pdf"
                zf.writestr(fname, single_buf.getvalue())
        zip_buf.seek(0)
        return send_file(zip_buf, mimetype="application/zip", as_attachment=True, download_name=f"{filename}.zip")
    else:
        pdf_bytes = renderer.render_all_to_bytes(order_lines, start_no)
        return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=f"{filename}.pdf")
