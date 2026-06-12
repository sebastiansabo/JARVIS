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
            """SELECT c.*, comp.company AS supplier_name, cl.display_name AS customer_name,
                      (SELECT COUNT(*) FROM facturare_anexas a WHERE a.contract_id = c.id) AS anexa_count,
                      COALESCE((SELECT SUM(al.selling_price_eur)
                         FROM facturare_anexa_lines al
                         JOIN facturare_anexas a2 ON a2.id = al.anexa_id
                         WHERE a2.contract_id = c.id), 0) AS total_value,
                      COALESCE((SELECT SUM(i.total_amount_eur)
                         FROM facturare_invoices i
                         JOIN facturare_anexas a3 ON a3.id = i.anexa_id
                         WHERE a3.contract_id = c.id AND i.invoice_type = 'INVOICE'), 0) AS invoiced_total
               FROM facturare_contracts c
               JOIN companies comp ON comp.id = c.supplier_id
               JOIN crm_clients cl ON cl.id = c.customer_id
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
                       notes=None, created_by=None, split_mode="equal"):
        return self.execute(
            """INSERT INTO facturare_invoices
               (anexa_id, invoice_type, invoice_state, sequence_number,
                invoice_number, issued_date, total_amount_eur, total_amount_ron,
                currency, kurs_applied, intocmit_de, notes, created_by, split_mode)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (anexa_id, invoice_type.value, invoice_state.value, sequence_number,
             invoice_number, issued_date, total_amount_eur, total_amount_ron,
             currency, kurs_applied, intocmit_de, notes, created_by, split_mode),
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

    # ── Invoice Links ────────────────────────────────────────────

    def create_link(self, source_invoice_id, target_invoice_id, link_type):
        return self.execute(
            """INSERT INTO facturare_invoice_links (source_invoice_id, target_invoice_id, link_type)
               VALUES (%s,%s,%s) RETURNING *""",
            (source_invoice_id, target_invoice_id, link_type.value), returning=True)
