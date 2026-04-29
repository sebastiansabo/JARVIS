"""Facturare API routes — validate, generate, download."""
import logging
from io import BytesIO
from pathlib import Path

from flask import jsonify, request, send_file
from flask_login import login_required, current_user

from . import facturare_bp
from .config import JobConfig
from .loaders.anexa import parse_anexa_metadata
from .services.facturare_service import FacturareService
from .services.proforma_service import ProformaService
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

logger = logging.getLogger("jarvis.facturare.routes")
_service = FacturareService()
_proforma_service = ProformaService()
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_perm_repo = PermissionRepository()


def _check_facturare_perm(action: str) -> bool:
    """Check facturare permission. Falls back to invoices.records for now."""
    role_id = getattr(current_user, "role_id", None)
    if not role_id:
        return False
    # Try facturare-specific permission first
    perm = _perm_repo.check_permission_v2(role_id, "facturare", "records", action)
    if perm.get("has_explicit_entry"):
        return perm.get("has_permission", False)
    # Fall back to invoices permission (accountants who can add invoices can facturare)
    perm = _perm_repo.check_permission_v2(role_id, "invoices", "records", action)
    if perm.get("has_explicit_entry"):
        return perm.get("has_permission", False)
    # Legacy: check can_add_invoices flag
    return bool(getattr(current_user, "can_add_invoices", False))


@facturare_bp.route("/facturare/api/parse-anexa", methods=["POST"])
@login_required
@handle_api_errors
def api_parse_anexa():
    """Upload Anexa xlsx and extract metadata header block.

    Returns auto-detected fields: customer_name, customer_address, customer_vat,
    invoice_date, kurs, start_no, contract_ref, anexa_ref, etc.
    """
    anexa_file = request.files.get("anexa")
    if not anexa_file:
        return error_response("anexa file is required", 400)

    meta = parse_anexa_metadata(anexa_file.read())
    return jsonify({"success": True, "metadata": meta})


@facturare_bp.route("/facturare/api/validate", methods=["POST"])
@login_required
@handle_api_errors
def api_validate():
    """Upload Anexa + config JSON, return sanity report.

    Body: multipart/form-data
      - anexa: xlsx file
      - config: JSON string with JobConfig fields
    """
    if not _check_facturare_perm("add"):
        return error_response("Permission denied", 403)

    anexa_file = request.files.get("anexa")
    if not anexa_file:
        return error_response("anexa file is required", 400)

    config_json = request.form.get("config")
    if not config_json:
        return error_response("config JSON is required", 400)

    import json
    try:
        cfg = JobConfig.model_validate(json.loads(config_json))
    except Exception as e:
        return error_response(f"Invalid config: {e}", 400)

    result = _service.validate(cfg, anexa_file.read())
    if not result.success:
        return error_response(result.error, 400)

    return jsonify({
        "success": True,
        "report": result.validation_report,
    })


@facturare_bp.route("/facturare/api/generate", methods=["POST"])
@login_required
@handle_api_errors
def api_generate():
    """Generate invoice PDFs + EuroFib xlsx. Returns download links.

    Body: multipart/form-data
      - anexa: xlsx file
      - config: JSON string with JobConfig fields
      - output: "all" (default), "pdf", or "xlsx"
    """
    if not _check_facturare_perm("add"):
        return error_response("Permission denied", 403)

    anexa_file = request.files.get("anexa")
    if not anexa_file:
        return error_response("anexa file is required", 400)

    config_json = request.form.get("config")
    if not config_json:
        return error_response("config JSON is required", 400)

    import json
    try:
        cfg = JobConfig.model_validate(json.loads(config_json))
    except Exception as e:
        return error_response(f"Invalid config: {e}", 400)

    output_type = request.form.get("output", "all")
    gen_pdf = output_type in ("all", "pdf")
    gen_xlsx = output_type in ("all", "xlsx")

    result = _service.generate(cfg, anexa_file.read(),
                               generate_pdf=gen_pdf, generate_xlsx=gen_xlsx)
    if not result.success:
        return error_response(result.error, 400)

    # Store bytes in session-scoped temp storage for subsequent download
    import uuid
    download_id = str(uuid.uuid4())

    # Use Flask app-level cache for simplicity (in-memory, single-worker safe)
    from flask import current_app
    if not hasattr(current_app, "_facturare_downloads"):
        current_app._facturare_downloads = {}
    current_app._facturare_downloads[download_id] = {
        "pdf": result.invoices_pdf,
        "xlsx": result.eurofib_xlsx,
        "job_id": cfg.job_id,
    }

    response = {
        "success": True,
        "lines_count": result.lines_count,
        "total_advance": result.total_advance,
        "invoice_range": result.invoice_range,
        "download_id": download_id,
    }
    if gen_pdf:
        response["pdf_url"] = f"/facturare/api/download/{download_id}/pdf"
    if gen_xlsx:
        response["xlsx_url"] = f"/facturare/api/download/{download_id}/xlsx"

    return jsonify(response)


@facturare_bp.route("/facturare/api/download/<download_id>/<file_type>")
@login_required
def api_download(download_id: str, file_type: str):
    """Download a previously generated PDF or xlsx."""
    if file_type not in ("pdf", "xlsx"):
        return error_response("file_type must be 'pdf' or 'xlsx'", 400)

    from flask import current_app
    downloads = getattr(current_app, "_facturare_downloads", {})
    entry = downloads.get(download_id)
    if not entry:
        return error_response("Download expired or not found", 404)

    data = entry.get(file_type)
    if not data:
        return error_response(f"No {file_type} in this generation", 404)

    job_id = entry.get("job_id", "facturare")
    if file_type == "pdf":
        filename = f"{job_id}_invoices.pdf"
        mimetype = "application/pdf"
    else:
        filename = f"{job_id}_eurofib.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return send_file(
        BytesIO(data),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@facturare_bp.route("/facturare/api/proforma/validate", methods=["POST"])
@login_required
@handle_api_errors
def api_proforma_validate():
    """Validate proforma Anexa — lighter config, no EuroFib.

    Body: multipart/form-data
      - anexa: xlsx file
      - config: JSON string with {supplier, customer, start_no, invoice_date, intocmit_de}
    """
    if not _check_facturare_perm("add"):
        return error_response("Permission denied", 403)

    anexa_file = request.files.get("anexa")
    if not anexa_file:
        return error_response("anexa file is required", 400)

    config_json = request.form.get("config")
    if not config_json:
        return error_response("config JSON is required", 400)

    import json
    try:
        cfg = json.loads(config_json)
    except Exception as e:
        return error_response(f"Invalid config: {e}", 400)

    result = _proforma_service.validate(
        supplier=cfg.get("supplier", {}),
        customer=cfg.get("customer", {}),
        start_no=int(cfg.get("start_no", 0)),
        invoice_date=cfg.get("invoice_date", ""),
        anexa_bytes=anexa_file.read(),
        sheet_name=cfg.get("sheet", "Sheet1"),
    )
    if not result.success:
        return error_response(result.error, 400)

    return jsonify({"success": True, "report": result.validation_report})


@facturare_bp.route("/facturare/api/proforma/generate", methods=["POST"])
@login_required
@handle_api_errors
def api_proforma_generate():
    """Generate proforma PDFs (no EuroFib). Returns download link.

    Body: multipart/form-data
      - anexa: xlsx file
      - config: JSON string with {supplier, customer, start_no, invoice_date, intocmit_de}
    """
    if not _check_facturare_perm("add"):
        return error_response("Permission denied", 403)

    anexa_file = request.files.get("anexa")
    if not anexa_file:
        return error_response("anexa file is required", 400)

    config_json = request.form.get("config")
    if not config_json:
        return error_response("config JSON is required", 400)

    import json
    try:
        cfg = json.loads(config_json)
    except Exception as e:
        return error_response(f"Invalid config: {e}", 400)

    result = _proforma_service.generate(
        supplier=cfg.get("supplier", {}),
        customer=cfg.get("customer", {}),
        start_no=int(cfg.get("start_no", 0)),
        invoice_date=cfg.get("invoice_date", ""),
        intocmit_de=cfg.get("intocmit_de", "Gabriela Oltean"),
        anexa_bytes=anexa_file.read(),
        sheet_name=cfg.get("sheet", "Sheet1"),
    )
    if not result.success:
        return error_response(result.error, 400)

    import uuid
    download_id = str(uuid.uuid4())
    job_id = cfg.get("job_id", "proforma")

    from flask import current_app
    if not hasattr(current_app, "_facturare_downloads"):
        current_app._facturare_downloads = {}
    current_app._facturare_downloads[download_id] = {
        "pdf": result.proforma_pdf,
        "xlsx": None,
        "job_id": job_id,
    }

    return jsonify({
        "success": True,
        "lines_count": result.lines_count,
        "total_amount": result.total_amount,
        "proforma_range": result.proforma_range,
        "download_id": download_id,
        "pdf_url": f"/facturare/api/download/{download_id}/pdf",
    })


@facturare_bp.route("/facturare/api/template/<kind>")
@login_required
def api_download_template(kind: str):
    """Download an Anexa template xlsx (invoice or proforma)."""
    templates = {
        "invoice": ("Anexa_Invoice_Template.xlsx", "Anexa_Invoice_Template.xlsx"),
        "proforma": ("Anexa_Proforma_Template.xlsx", "Anexa_Proforma_Template.xlsx"),
    }
    if kind not in templates:
        return error_response("kind must be 'invoice' or 'proforma'", 400)

    filename, download_name = templates[kind]
    template_path = _ASSETS_DIR / filename
    if not template_path.exists():
        return error_response("Template not found", 404)
    return send_file(
        str(template_path),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=download_name,
    )
