"""Repository for facturare invoice storage.

Entity hierarchy: Contract → Anexa (with vehicle lines) → Invoices (lifecycle docs).
"""
from decimal import Decimal
from core.base_repository import BaseRepository
from ..models import InvoiceTypeEnum, InvoiceStateEnum, InvoiceLinkTypeEnum


class InvoiceStorageRepository(BaseRepository):

    # ── Contract CRUD ────────────────────────────────────────────

    def create_contract(self, contract_ref, supplier_id, customer_id,
                        contract_date=None, responsible=None, notes=None, created_by=None):
        return self.execute(
            """INSERT INTO facturare_contracts
               (contract_ref, supplier_id, customer_id, contract_date, responsible, notes, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (contract_ref, supplier_id, customer_id, contract_date, responsible, notes, created_by),
            returning=True)

    def get_contract_by_id(self, contract_id):
        return self.query_one("SELECT * FROM facturare_contracts WHERE id = %s", (contract_id,))

    def get_contract_by_ref_and_supplier(self, contract_ref, supplier_id):
        return self.query_one(
            "SELECT * FROM facturare_contracts WHERE contract_ref = %s AND supplier_id = %s",
            (contract_ref, supplier_id))

    def list_contracts(self):
        return self.query_all(
            """WITH anexa_stats AS (
                   SELECT a.contract_id,
                          COUNT(DISTINCT a.id) AS anexa_count,
                          COALESCE(SUM(al.selling_price_eur), 0) AS total_value
                   FROM facturare_anexas a
                   LEFT JOIN facturare_anexa_lines al ON al.anexa_id = a.id
                   GROUP BY a.contract_id
               ), invoice_stats AS (
                   SELECT a.contract_id,
                          COALESCE(SUM(i.total_amount_eur), 0) AS invoiced_total
                   FROM facturare_invoices i
                   JOIN facturare_anexas a ON a.id = i.anexa_id
                   WHERE i.invoice_type = 'INVOICE'
                   GROUP BY a.contract_id
               )
               SELECT c.*, comp.company AS supplier_name, cl.display_name AS customer_name,
                      COALESCE(ast.anexa_count, 0) AS anexa_count,
                      COALESCE(ast.total_value, 0) AS total_value,
                      COALESCE(ist.invoiced_total, 0) AS invoiced_total
               FROM facturare_contracts c
               JOIN companies comp ON comp.id = c.supplier_id
               JOIN crm_clients cl ON cl.id = c.customer_id
               LEFT JOIN anexa_stats ast ON ast.contract_id = c.id
               LEFT JOIN invoice_stats ist ON ist.contract_id = c.id
               ORDER BY c.created_at DESC""")

    def delete_contract(self, contract_id):
        self.execute("DELETE FROM facturare_contracts WHERE id = %s", (contract_id,))

    # ── Anexa CRUD ───────────────────────────────────────────────

    def create_anexa(self, contract_id, anexa_number, notes=None, created_by=None):
        return self.execute(
            """INSERT INTO facturare_anexas (contract_id, anexa_number, notes, created_by)
               VALUES (%s,%s,%s,%s) RETURNING *""",
            (contract_id, anexa_number, notes, created_by), returning=True)

    def get_anexa_by_id(self, anexa_id):
        return self.query_one("SELECT * FROM facturare_anexas WHERE id = %s", (anexa_id,))

    def get_anexa_by_contract_and_number(self, contract_id, anexa_number):
        return self.query_one(
            "SELECT * FROM facturare_anexas WHERE contract_id = %s AND anexa_number = %s",
            (contract_id, anexa_number))

    def list_anexas_by_contract(self, contract_id):
        return self.query_all(
            "SELECT * FROM facturare_anexas WHERE contract_id = %s ORDER BY anexa_number",
            (contract_id,))

    def delete_anexa(self, anexa_id):
        self.execute("DELETE FROM facturare_anexas WHERE id = %s", (anexa_id,))

    # ── Anexa Lines (vehicles) ───────────────────────────────────

    def create_anexa_line(self, anexa_id, line_number, model, list_price_eur, selling_price_eur,
                          qty=1, nr_comanda=None, vin=None, culoare=None):
        return self.execute(
            """INSERT INTO facturare_anexa_lines
               (anexa_id, line_number, nr_comanda, vin, model, culoare,
                list_price_eur, selling_price_eur, qty)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (anexa_id, line_number, nr_comanda, vin, model, culoare,
             list_price_eur, selling_price_eur, qty), returning=True)

    def get_lines_by_anexa(self, anexa_id):
        return self.query_all(
            "SELECT * FROM facturare_anexa_lines WHERE anexa_id = %s ORDER BY line_number",
            (anexa_id,))

    def update_anexa_line(self, line_id, **fields):
        sets = ", ".join(f"{k} = %s" for k in fields)
        vals = list(fields.values()) + [line_id]
        return self.execute(
            f"UPDATE facturare_anexa_lines SET {sets} WHERE id = %s RETURNING *",
            tuple(vals), returning=True)

    # ── Invoice CRUD ─────────────────────────────────────────────

    def create_invoice(self, anexa_id, invoice_type, invoice_state,
                       total_amount_eur, total_amount_ron=Decimal("0"),
                       currency="EUR", sequence_number=1,
                       invoice_number=None, issued_date=None,
                       kurs_applied=None, intocmit_de=None,
                       notes=None, created_by=None, split_mode="equal",
                       line_ids=None, doc_mode="per_car"):
        import json
        return self.execute(
            """INSERT INTO facturare_invoices
               (anexa_id, invoice_type, invoice_state, sequence_number,
                invoice_number, issued_date, total_amount_eur, total_amount_ron,
                currency, kurs_applied, intocmit_de, notes, created_by, split_mode, line_ids, doc_mode)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (anexa_id, invoice_type.value, invoice_state.value, sequence_number,
             invoice_number, issued_date, total_amount_eur, total_amount_ron,
             currency, kurs_applied, intocmit_de, notes, created_by, split_mode,
             json.dumps(line_ids) if line_ids else None, doc_mode),
            returning=True)

    def get_invoice_by_id(self, invoice_id):
        return self.query_one("SELECT * FROM facturare_invoices WHERE id = %s", (invoice_id,))

    def get_invoices_by_anexa(self, anexa_id):
        return self.query_all(
            "SELECT * FROM facturare_invoices WHERE anexa_id = %s ORDER BY created_at",
            (anexa_id,))

    def get_invoice_by_anexa_type_and_seq(self, anexa_id, invoice_type, sequence_number):
        return self.query_one(
            "SELECT * FROM facturare_invoices WHERE anexa_id = %s AND invoice_type = %s AND sequence_number = %s",
            (anexa_id, invoice_type.value, sequence_number))

    def get_invoice_by_anexa_and_type(self, anexa_id, invoice_type):
        return self.query_one(
            "SELECT * FROM facturare_invoices WHERE anexa_id = %s AND invoice_type = %s",
            (anexa_id, invoice_type.value))

    def get_invoices_by_anexa_and_type_list(self, anexa_id, invoice_type):
        return self.query_all(
            "SELECT * FROM facturare_invoices WHERE anexa_id = %s AND invoice_type = %s ORDER BY sequence_number",
            (anexa_id, invoice_type.value))

    def count_invoices_by_anexa_and_type(self, anexa_id, invoice_type):
        row = self.query_one(
            "SELECT COUNT(*) AS cnt FROM facturare_invoices WHERE anexa_id = %s AND invoice_type = %s",
            (anexa_id, invoice_type.value))
        return row["cnt"] if row else 0

    def delete_invoice(self, invoice_id):
        self.execute("DELETE FROM facturare_invoices WHERE id = %s", (invoice_id,))

    # ── Konto Config ────────────────────────────────────────────

    def get_konto_config(self):
        return self.query_all(
            """SELECT kc.*, comp.company AS supplier_name
               FROM facturare_konto_config kc
               JOIN companies comp ON comp.id = kc.supplier_id
               ORDER BY kc.supplier_id, kc.invoice_type""")

    def upsert_konto_config(self, supplier_id, invoice_type, konto_debit, konto_credit, centru_gestiune, text_template=None, updated_by=None):
        return self.execute(
            """INSERT INTO facturare_konto_config (supplier_id, invoice_type, konto_debit, konto_credit, centru_gestiune, text_template, updated_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (supplier_id, invoice_type) DO UPDATE SET
                 konto_debit = EXCLUDED.konto_debit, konto_credit = EXCLUDED.konto_credit,
                 centru_gestiune = EXCLUDED.centru_gestiune, text_template = EXCLUDED.text_template,
                 updated_at = now(), updated_by = EXCLUDED.updated_by
               RETURNING *""",
            (supplier_id, invoice_type, konto_debit, konto_credit, centru_gestiune, text_template, updated_by), returning=True)

    # ── Venituri Rules ─────────────────────────────────────────────

    def get_venituri_rules(self):
        return self.query_all(
            """SELECT vr.*, comp.company AS supplier_name
               FROM facturare_venituri_rules vr
               JOIN companies comp ON comp.id = vr.supplier_id
               ORDER BY vr.supplier_id, vr.comanda_prefix""")

    def upsert_venituri_rule(self, supplier_id, comanda_prefix, konto_venituri, kostenstelle, updated_by=None):
        return self.execute(
            """INSERT INTO facturare_venituri_rules (supplier_id, comanda_prefix, konto_venituri, kostenstelle, updated_by)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (supplier_id, comanda_prefix) DO UPDATE SET
                 konto_venituri = EXCLUDED.konto_venituri, kostenstelle = EXCLUDED.kostenstelle,
                 updated_at = now(), updated_by = EXCLUDED.updated_by
               RETURNING *""",
            (supplier_id, comanda_prefix, konto_venituri, kostenstelle, updated_by), returning=True)

    def delete_venituri_rule(self, rule_id):
        self.execute("DELETE FROM facturare_venituri_rules WHERE id = %s", (rule_id,))

    def match_venituri_rule(self, supplier_id, nr_comanda):
        """Find the venituri rule for a supplier + order number.
        Tries prefix match first, then wildcard '*'."""
        nr_str = str(nr_comanda)
        rules = self.query_all(
            "SELECT * FROM facturare_venituri_rules WHERE supplier_id = %s ORDER BY comanda_prefix DESC",
            (supplier_id,))
        for rule in rules:
            if rule["comanda_prefix"] != "*" and nr_str.startswith(rule["comanda_prefix"]):
                return rule
        for rule in rules:
            if rule["comanda_prefix"] == "*":
                return rule
        return None

    # ── Invoice Links ────────────────────────────────────────────

    def create_link(self, source_invoice_id, target_invoice_id, link_type):
        return self.execute(
            """INSERT INTO facturare_invoice_links (source_invoice_id, target_invoice_id, link_type)
               VALUES (%s,%s,%s) RETURNING *""",
            (source_invoice_id, target_invoice_id, link_type.value), returning=True)

    # ── Document numbers registry ────────────────────────────────

    def replace_document_numbers(self, invoice_id, supplier_id, rows):
        """Delete-then-insert the document number rows for an invoice.

        Idempotent: calling this twice with the same rows yields the same
        stored state (no duplicate-key errors), since existing rows for the
        invoice are removed first within the same transaction.
        """
        def _work(cursor):
            cursor.execute("DELETE FROM facturare_document_numbers WHERE invoice_id=%s", (invoice_id,))
            for r in rows:
                cursor.execute(
                    """INSERT INTO facturare_document_numbers
                       (invoice_id, supplier_id, series, line_id, position, document_number)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (invoice_id, supplier_id, r["series"], r["line_id"], r["position"], r["document_number"]))
        return self.execute_many(_work)

    def get_document_number_map(self, invoice_id):
        """Return {line_id: document_number} for an invoice, skipping None numbers."""
        rows = self.query_all(
            "SELECT line_id, document_number FROM facturare_document_numbers "
            "WHERE invoice_id=%s AND document_number IS NOT NULL", (invoice_id,))
        return {r["line_id"]: r["document_number"] for r in (rows or [])}
