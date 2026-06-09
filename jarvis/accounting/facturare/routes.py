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
from .repositories.facturare_repository import FacturareRepository
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

logger = logging.getLogger("jarvis.facturare.routes")
_service = FacturareService()
_proforma_service = ProformaService()
_gen_repo = FacturareRepository()
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


@facturare_bp.route("/facturare/api/bnr-rate")
@login_required
@handle_api_errors
def api_bnr_rate():
    """Get BNR EUR/RON rate for the day before a given date.

    Query params:
      - date: invoice date (YYYY-MM-DD) — rate will be fetched for date-1
    """
    from datetime import datetime, timedelta
    from core.services.currency_converter import get_exchange_rate

    date_str = request.args.get("date")
    if not date_str:
        return error_response("date query param is required", 400)

    try:
        invoice_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return error_response("date must be YYYY-MM-DD", 400)

    kurs_date = invoice_date - timedelta(days=1)
    kurs_date_str = kurs_date.strftime("%Y-%m-%d")

    rate = get_exchange_rate("EUR", kurs_date_str)
    if rate is None:
        return error_response(f"No BNR rate found for {kurs_date_str}", 404)

    return jsonify({
        "success": True,
        "kurs": round(rate, 4),
        "kurs_date": kurs_date_str,
    })


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

    collapse = bool(json.loads(config_json).get("collapse", False))
    result = _service.validate(cfg, anexa_file.read(), collapse=collapse)
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
    collapse = bool(json.loads(config_json).get("collapse", False))

    anexa_file_bytes = anexa_file.read()
    result = _service.generate(cfg, anexa_file_bytes,
                               generate_pdf=gen_pdf, generate_xlsx=gen_xlsx,
                               collapse=collapse)
    if not result.success:
        return error_response(result.error, 400)

    # Persist generation record first — use DB-based URLs to survive multi-worker deployments
    # Parse range from result (handles per-row overrides and collapse)
    range_parts = result.invoice_range.replace('–', '-').split('-')
    start_no = int(range_parts[0]) if range_parts[0].strip() else cfg.invoice.start_no
    last_no = int(range_parts[-1]) if range_parts[-1].strip() else start_no
    gen_id = None
    try:
        record = _gen_repo.save_generation(
            gen_type="invoice", job_id=cfg.job_id,
            start_no=start_no, end_no=last_no,
            line_count=result.lines_count, total_amount=float(result.total_advance),
            currency=cfg.fx.currency, invoice_date=cfg.invoice.date or None,
            supplier_name=cfg.supplier.name, customer_name=cfg.customer.name,
            customer_vat=cfg.customer.vat, intocmit_de=cfg.invoice.intocmit_de,
            pdf_data=result.invoices_pdf, xlsx_data=result.eurofib_xlsx,
            generated_by=getattr(current_user, "id", None),
        )
        gen_id = record['id'] if record else None
    except Exception:
        logger.warning("Failed to save invoice generation record", exc_info=True)

    # Fall back to in-memory temp download if DB save failed
    import uuid
    download_id = str(uuid.uuid4())
    from flask import current_app
    if not hasattr(current_app, "_facturare_downloads"):
        current_app._facturare_downloads = {}
    current_app._facturare_downloads[download_id] = {
        "pdf": result.invoices_pdf,
        "xlsx": result.eurofib_xlsx,
        "job_id": cfg.job_id,
        "cfg": cfg,
        "anexa_bytes": anexa_file_bytes,
        "collapse": collapse,
    }

    response = {
        "success": True,
        "lines_count": result.lines_count,
        "total_advance": result.total_advance,
        "invoice_range": result.invoice_range,
        "download_id": download_id,
    }
    if gen_pdf:
        response["pdf_url"] = f"/facturare/api/generations/{gen_id}/pdf" if gen_id else f"/facturare/api/download/{download_id}/pdf"
        response["zip_url"] = f"/facturare/api/download/{download_id}/zip"
    if gen_xlsx:
        response["xlsx_url"] = f"/facturare/api/generations/{gen_id}/xlsx" if gen_id else f"/facturare/api/download/{download_id}/xlsx"

    return jsonify(response)


@facturare_bp.route("/facturare/api/download/<download_id>/<file_type>")
@login_required
def api_download(download_id: str, file_type: str):
    """Download a previously generated PDF, xlsx, or ZIP of individual invoices."""
    if file_type not in ("pdf", "xlsx", "zip"):
        return error_response("file_type must be 'pdf', 'xlsx', or 'zip'", 400)

    from flask import current_app
    downloads = getattr(current_app, "_facturare_downloads", {})
    entry = downloads.get(download_id)
    if not entry:
        return error_response("Download expired or not found", 404)

    job_id = entry.get("job_id", "facturare")

    if file_type == "zip":
        # Generate individual PDFs on-the-fly, return as ZIP
        cfg = entry.get("cfg")
        anexa_bytes = entry.get("anexa_bytes")
        if not cfg or not anexa_bytes:
            return error_response("ZIP generation data not available", 404)
        try:
            from ..facturare.loaders.anexa import load_anexa
            from ..facturare.generators.invoice_pdf import InvoicePdfRenderer
            lines = load_anexa(anexa_bytes, sheet_name=cfg.input.sheet)
            renderer = InvoicePdfRenderer(cfg)
            zip_bytes = renderer.render_individual_zip(lines)
            return send_file(
                BytesIO(zip_bytes),
                mimetype="application/zip",
                as_attachment=True,
                download_name=f"{job_id}_invoices.zip",
            )
        except Exception as e:
            return error_response(f"ZIP generation failed: {e}", 500)

    data = entry.get(file_type)
    if not data:
        return error_response(f"No {file_type} in this generation", 404)

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
        collapse=bool(cfg.get("collapse", False)),
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
        collapse=bool(cfg.get("collapse", False)),
        note=cfg.get("note", ""),
    )
    if not result.success:
        return error_response(result.error, 400)

    job_id = cfg.get("job_id", "proforma")

    # Persist generation record first — use DB-based URL to survive multi-worker deployments
    start_no = int(cfg.get("start_no", 0))
    last_no = start_no + result.lines_count - 1
    gen_id = None
    try:
        record = _gen_repo.save_generation(
            gen_type="proforma", job_id=job_id,
            start_no=start_no, end_no=last_no,
            line_count=result.lines_count, total_amount=float(result.total_amount),
            currency="EUR", invoice_date=cfg.get("invoice_date") or None,
            supplier_name=cfg.get("supplier", {}).get("name", ""),
            customer_name=cfg.get("customer", {}).get("name", ""),
            customer_vat=cfg.get("customer", {}).get("vat", ""),
            intocmit_de=cfg.get("intocmit_de", "Gabriela Oltean"),
            pdf_data=result.proforma_pdf,
            generated_by=getattr(current_user, "id", None),
            note=cfg.get("note") or None,
        )
        gen_id = record['id'] if record else None
    except Exception:
        logger.warning("Failed to save proforma generation record", exc_info=True)

    # Fall back to in-memory temp download if DB save failed
    import uuid
    download_id = str(uuid.uuid4())
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
        "pdf_url": f"/facturare/api/generations/{gen_id}/pdf" if gen_id else f"/facturare/api/download/{download_id}/pdf",
    })


@facturare_bp.route("/facturare/api/generations")
@login_required
@handle_api_errors
def api_list_generations():
    """List all generation records (without binary data)."""
    gen_type = request.args.get("type")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    rows = _gen_repo.list_generations(gen_type=gen_type, limit=limit, offset=offset)
    total = _gen_repo.count_generations(gen_type=gen_type)
    return jsonify({"generations": rows, "total": total})


@facturare_bp.route("/facturare/api/generations/<int:gen_id>/<file_type>")
@login_required
def api_download_generation(gen_id: int, file_type: str):
    """Download PDF, xlsx, or ZIP of individual invoices from a stored generation."""
    if file_type not in ("pdf", "xlsx", "zip"):
        return error_response("file_type must be 'pdf', 'xlsx', or 'zip'", 400)

    row = _gen_repo.get_generation(gen_id)
    if not row:
        return error_response("Generation not found", 404)

    if file_type == "zip":
        # Split stored multi-page PDF into individual pages, ZIP them
        pdf_data = row.get("pdf_data")
        if not pdf_data:
            return error_response("No PDF stored for this generation", 404)
        if isinstance(pdf_data, memoryview):
            pdf_data = bytes(pdf_data)

        try:
            import zipfile
            from PyPDF2 import PdfReader, PdfWriter

            reader = PdfReader(BytesIO(pdf_data))
            start_no = row.get("start_no", 1)
            job_id = row.get("job_id") or row.get("gen_type", "facturare")
            customer = row.get("customer_name", "")
            inv_date = row.get("invoice_date", "")
            if inv_date:
                try:
                    from datetime import datetime as _dt
                    inv_date = _dt.strptime(str(inv_date), "%Y-%m-%d").strftime("%d.%m.%Y")
                except Exception:
                    pass
            gen_type = row.get("gen_type", "invoice")
            inv_type = "avans" if "avans" in (job_id or "").lower() else gen_type

            buf = BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, page in enumerate(reader.pages):
                    writer = PdfWriter()
                    writer.add_page(page)
                    page_buf = BytesIO()
                    writer.write(page_buf)
                    inv_no = start_no + i
                    name = f"invoice {customer} {inv_no} {inv_date} {inv_type}".strip()
                    name = "".join(c for c in name if c.isalnum() or c in " ._-+").strip()
                    zf.writestr(f"{name}.pdf", page_buf.getvalue())

            return send_file(BytesIO(buf.getvalue()), mimetype="application/zip",
                             as_attachment=True, download_name=f"{job_id}_invoices.zip")
        except Exception as e:
            return error_response(f"ZIP generation failed: {e}", 500)

    col = "pdf_data" if file_type == "pdf" else "xlsx_data"
    data = row.get(col)
    if not data:
        return error_response(f"No {file_type} stored for this generation", 404)

    # Handle memoryview from psycopg2
    if isinstance(data, memoryview):
        data = bytes(data)

    job_id = row.get("job_id") or row.get("gen_type", "facturare")
    if file_type == "pdf":
        filename = f"{job_id}_{row['gen_type']}.pdf"
        mimetype = "application/pdf"
    else:
        filename = f"{job_id}_eurofib.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return send_file(BytesIO(data), mimetype=mimetype,
                     as_attachment=True, download_name=filename)


@facturare_bp.route("/facturare/api/generations/<int:gen_id>", methods=["DELETE"])
@login_required
@handle_api_errors
def api_delete_generation(gen_id: int):
    """Delete a generation record."""
    if not _check_facturare_perm("add"):
        return error_response("Permission denied", 403)
    row = _gen_repo.get_generation(gen_id)
    if not row:
        return error_response("Generation not found", 404)
    _gen_repo.delete_generation(gen_id)
    return jsonify({"success": True})


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
