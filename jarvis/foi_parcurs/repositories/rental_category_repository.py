"""Data access for the courtesy-car rental tariff scheme (per company):
duration intervals, categories, and the category × interval €/day price grid.
A car's `rental_category_id` + the rental day-count resolve to a €/day via
`price_for`. Interval selection is the pure `rental_pricing.select_interval`."""
from core.base_repository import BaseRepository
from ..services.rental_pricing import select_interval


class RentalCategoryRepository(BaseRepository):

    # ── intervals ───────────────────────────────────────────────────────────
    def list_intervals(self, company_id) -> list:
        if not company_id:
            return []
        return self.query_all(
            '''SELECT id, label, min_days, max_days, sort_order
               FROM fp_rental_intervals
               WHERE company_id = %s
               ORDER BY sort_order, min_days''',
            (company_id,),
        ) or []

    def upsert_interval(self, company_id, interval_id, label, min_days,
                        max_days, sort_order):
        if not company_id:
            raise ValueError('company_id required')
        if min_days is None:
            raise ValueError('min_days required')
        if interval_id:
            return self.execute(
                '''UPDATE fp_rental_intervals
                   SET label=%s, min_days=%s, max_days=%s, sort_order=%s
                   WHERE id=%s AND company_id=%s RETURNING id''',
                (label, min_days, max_days, sort_order or 0, interval_id, company_id),
                returning=True,
            )
        return self.execute(
            '''INSERT INTO fp_rental_intervals
                   (company_id, label, min_days, max_days, sort_order)
               VALUES (%s, %s, %s, %s, %s) RETURNING id''',
            (company_id, label, min_days, max_days, sort_order or 0),
            returning=True,
        )

    def delete_interval(self, company_id, interval_id):
        used = self.query_one(
            'SELECT COUNT(*) AS n FROM fp_rental_category_prices '
            'WHERE company_id=%s AND interval_id=%s',
            (company_id, interval_id),
        ) or {}
        if int(used.get('n') or 0):
            raise ValueError('Intervalul are prețuri asociate — șterge întâi prețurile.')
        return self.execute(
            'DELETE FROM fp_rental_intervals WHERE company_id=%s AND id=%s',
            (company_id, interval_id),
        )

    # ── categories (+ price grid) ───────────────────────────────────────────
    def list_categories(self, company_id, active_only=False) -> list:
        if not company_id:
            return []
        where = 'WHERE company_id = %s'
        params = [company_id]
        if active_only:
            where += ' AND is_active = TRUE'
        cats = self.query_all(
            f'''SELECT id, name, models_note, franchise_eur, extra_km_eur,
                       sort_order, is_active
                FROM fp_rental_categories {where}
                ORDER BY sort_order, name''',
            tuple(params),
        ) or []
        prices = self.query_all(
            'SELECT category_id, interval_id, eur_per_day '
            'FROM fp_rental_category_prices WHERE company_id = %s',
            (company_id,),
        ) or []
        by_cat = {}
        for p in prices:
            by_cat.setdefault(p['category_id'], {})[p['interval_id']] = p['eur_per_day']
        for c in cats:
            c['prices'] = by_cat.get(c['id'], {})
        return cats

    def add_category(self, company_id, name):
        if not company_id:
            raise ValueError('company_id required')
        name = (name or '').strip()
        if not name:
            raise ValueError('Denumirea categoriei este obligatorie')
        next_order = self.query_one(
            'SELECT COALESCE(MAX(sort_order), -1) + 1 AS n '
            'FROM fp_rental_categories WHERE company_id=%s',
            (company_id,),
        ) or {}
        return self.execute(
            '''INSERT INTO fp_rental_categories
                   (company_id, name, sort_order, is_active)
               VALUES (%s, %s, %s, TRUE)
               ON CONFLICT (company_id, name) DO NOTHING
               RETURNING id''',
            (company_id, name, int(next_order.get('n') or 0)),
            returning=True,
        )

    def upsert_category(self, company_id, category_id, name, models_note,
                        franchise_eur, extra_km_eur, sort_order, is_active):
        name = (name or '').strip()
        if not name:
            raise ValueError('Denumirea categoriei este obligatorie')
        return self.execute(
            '''UPDATE fp_rental_categories
               SET name=%s, models_note=%s, franchise_eur=%s, extra_km_eur=%s,
                   sort_order=%s, is_active=%s
               WHERE id=%s AND company_id=%s RETURNING id''',
            (name, models_note, franchise_eur, extra_km_eur, sort_order or 0,
             bool(is_active), category_id, company_id),
            returning=True,
        )

    def delete_category(self, company_id, category_id):
        used = self.query_one(
            'SELECT COUNT(*) AS n FROM fp_vehicles '
            'WHERE company_id=%s AND rental_category_id=%s',
            (company_id, category_id),
        ) or {}
        if int(used.get('n') or 0):
            raise ValueError(
                f"Categoria este folosită de {used['n']} mașini — "
                'dezactiveaz-o în loc să o ștergi.')
        # prices FK-orphan cleanup then the category
        self.execute(
            'DELETE FROM fp_rental_category_prices WHERE company_id=%s AND category_id=%s',
            (company_id, category_id),
        )
        return self.execute(
            'DELETE FROM fp_rental_categories WHERE company_id=%s AND id=%s',
            (company_id, category_id),
        )

    def set_price(self, company_id, category_id, interval_id, eur_per_day):
        return self.execute(
            '''INSERT INTO fp_rental_category_prices
                   (company_id, category_id, interval_id, eur_per_day)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (company_id, category_id, interval_id)
               DO UPDATE SET eur_per_day = EXCLUDED.eur_per_day''',
            (company_id, category_id, interval_id, eur_per_day),
        )

    # ── pricing lookup ──────────────────────────────────────────────────────
    def price_for(self, company_id, category_id, days):
        """Resolve a car's category + rental day-count to a €/day + policy.
        Returns None when the category is unknown or no interval covers `days`."""
        cat = self.query_one(
            'SELECT id, franchise_eur, extra_km_eur FROM fp_rental_categories '
            'WHERE company_id=%s AND id=%s',
            (company_id, category_id),
        )
        if not cat:
            return None
        iv = select_interval(self.list_intervals(company_id), days)
        if not iv:
            return None
        price = self.query_one(
            'SELECT eur_per_day FROM fp_rental_category_prices '
            'WHERE company_id=%s AND category_id=%s AND interval_id=%s',
            (company_id, category_id, iv['id']),
        ) or {}
        return {
            'eur_per_day': price.get('eur_per_day'),
            'interval_id': iv['id'],
            'interval_label': iv['label'],
            'franchise_eur': cat['franchise_eur'],
            'extra_km_eur': cat['extra_km_eur'],
        }
