"""Facturare Repository — tracks generated invoices and proformas."""

from core.base_repository import BaseRepository


class FacturareRepository(BaseRepository):

    def save_generation(self, gen_type, job_id, start_no, end_no, line_count,
                        total_amount, currency, invoice_date, supplier_name,
                        customer_name, customer_vat, intocmit_de,
                        pdf_data=None, xlsx_data=None, generated_by=None):
        return self.execute(
            """INSERT INTO facturare_generations
               (gen_type, job_id, start_no, end_no, line_count, total_amount,
                currency, invoice_date, supplier_name, customer_name,
                customer_vat, intocmit_de, pdf_data, xlsx_data, generated_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (gen_type, job_id, start_no, end_no, line_count, total_amount,
             currency, invoice_date, supplier_name, customer_name,
             customer_vat, intocmit_de, pdf_data, xlsx_data, generated_by),
            returning=True,
        )

    def list_generations(self, gen_type=None, limit=50, offset=0):
        conditions, params = [], []
        if gen_type:
            conditions.append("gen_type = %s")
            params.append(gen_type)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])
        return self.query_all(
            f"""SELECT id, gen_type, job_id, start_no, end_no, line_count,
                       total_amount, currency, invoice_date, supplier_name,
                       customer_name, customer_vat, intocmit_de,
                       (pdf_data IS NOT NULL) AS has_pdf,
                       (xlsx_data IS NOT NULL) AS has_xlsx,
                       generated_by, created_at
                FROM facturare_generations {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s""",
            tuple(params),
        )

    def count_generations(self, gen_type=None):
        if gen_type:
            row = self.query_one(
                "SELECT COUNT(*) AS cnt FROM facturare_generations WHERE gen_type = %s",
                (gen_type,),
            )
        else:
            row = self.query_one("SELECT COUNT(*) AS cnt FROM facturare_generations")
        return row["cnt"] if row else 0

    def get_generation(self, gen_id):
        return self.query_one(
            "SELECT * FROM facturare_generations WHERE id = %s", (gen_id,),
        )

    def delete_generation(self, gen_id):
        self.execute("DELETE FROM facturare_generations WHERE id = %s", (gen_id,))
