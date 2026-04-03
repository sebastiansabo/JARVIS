"""Analytics Repository — Aggregated queries for CarPark KPIs & dashboard."""
from typing import Dict, Any, List, Optional
from core.base_repository import BaseRepository


class AnalyticsRepository(BaseRepository):
    """Read-only analytics queries for the CarPark dashboard."""

    # ── Inventory summary ────────────────────────────────────

    def get_inventory_summary(self, company_id: int) -> Dict[str, Any]:
        """High-level counts: total, by status, by category."""
        return self.query_one('''
            SELECT
                COUNT(*) AS total_vehicles,
                COUNT(*) FILTER (WHERE status NOT IN ('SOLD','DELIVERED','SCRAPPED','RETURNED'))
                    AS in_stock,
                COUNT(*) FILTER (WHERE status IN ('SOLD','DELIVERED'))
                    AS sold_delivered,
                COUNT(*) FILTER (WHERE status = 'READY_FOR_SALE')
                    AS ready_for_sale,
                COUNT(*) FILTER (WHERE status = 'LISTED')
                    AS listed,
                COUNT(*) FILTER (WHERE status = 'RESERVED')
                    AS reserved,
                COUNT(*) FILTER (WHERE status IN ('INSPECTION','RECONDITIONING','AT_BODYSHOP'))
                    AS in_preparation,
                COALESCE(SUM(current_price) FILTER (
                    WHERE status NOT IN ('SOLD','DELIVERED','SCRAPPED','RETURNED')
                ), 0) AS total_stock_value,
                COALESCE(SUM(acquisition_price) FILTER (
                    WHERE status NOT IN ('SOLD','DELIVERED','SCRAPPED','RETURNED')
                ), 0) AS total_acquisition_value
            FROM carpark_vehicles
            WHERE company_id = %s
        ''', (company_id,))

    def get_status_breakdown(self, company_id: int) -> List[Dict[str, Any]]:
        """Vehicle count per status."""
        return self.query_all('''
            SELECT status, COUNT(*) AS count
            FROM carpark_vehicles
            WHERE company_id = %s
            GROUP BY status
            ORDER BY count DESC
        ''', (company_id,))

    def get_category_breakdown(self, company_id: int) -> List[Dict[str, Any]]:
        """Vehicle count per category."""
        return self.query_all('''
            SELECT category, COUNT(*) AS count,
                   COALESCE(SUM(current_price), 0) AS total_value
            FROM carpark_vehicles
            WHERE company_id = %s
              AND status NOT IN ('SOLD','DELIVERED','SCRAPPED','RETURNED')
            GROUP BY category
            ORDER BY count DESC
        ''', (company_id,))

    # ── KPIs ─────────────────────────────────────────────────

    def get_kpis(self, company_id: int) -> Dict[str, Any]:
        """Core KPI metrics."""
        return self.query_one('''
            WITH stock AS (
                SELECT *,
                    COALESCE(days_listed, (CURRENT_DATE - COALESCE(arrival_date, acquisition_date))) AS age_days
                FROM carpark_vehicles
                WHERE company_id = %(cid)s
                  AND status NOT IN ('SOLD','DELIVERED','SCRAPPED','RETURNED')
            ),
            sold_30 AS (
                SELECT COUNT(*) AS cnt
                FROM carpark_vehicles
                WHERE company_id = %(cid)s
                  AND status IN ('SOLD','DELIVERED')
                  AND sale_date >= CURRENT_DATE - INTERVAL '30 days'
            ),
            sold_365 AS (
                SELECT COUNT(*) AS cnt
                FROM carpark_vehicles
                WHERE company_id = %(cid)s
                  AND status IN ('SOLD','DELIVERED')
                  AND sale_date >= CURRENT_DATE - INTERVAL '365 days'
            ),
            fast_sold AS (
                SELECT COUNT(*) AS cnt
                FROM carpark_vehicles
                WHERE company_id = %(cid)s
                  AND status IN ('SOLD','DELIVERED')
                  AND sale_date >= CURRENT_DATE - INTERVAL '365 days'
                  AND (sale_date - COALESCE(arrival_date, acquisition_date)) <= 30
            )
            SELECT
                -- Average days on lot (in-stock)
                COALESCE(ROUND(AVG(s.age_days)), 0) AS avg_days_on_lot,
                -- Aged stock > 60 days
                COUNT(*) FILTER (WHERE s.age_days > 60) AS aged_count,
                CASE WHEN COUNT(*) > 0
                     THEN ROUND(100.0 * COUNT(*) FILTER (WHERE s.age_days > 60) / COUNT(*), 1)
                     ELSE 0 END AS aged_percent,
                -- Current stock count
                COUNT(*) AS current_stock,
                -- Sales velocity
                (SELECT cnt FROM sold_30) AS sold_last_30d,
                (SELECT cnt FROM sold_365) AS sold_last_365d,
                -- Inventory turn rate (annual sales / avg inventory)
                CASE WHEN COUNT(*) > 0
                     THEN ROUND((SELECT cnt FROM sold_365)::numeric / NULLIF(COUNT(*), 0), 2)
                     ELSE 0 END AS inventory_turn_rate,
                -- Stocking efficiency (sold < 30 days / total sold, last year)
                CASE WHEN (SELECT cnt FROM sold_365) > 0
                     THEN ROUND(100.0 * (SELECT cnt FROM fast_sold) / (SELECT cnt FROM sold_365), 1)
                     ELSE 0 END AS stocking_efficiency
            FROM stock s
        ''', {'cid': company_id})

    # ── Aging distribution ───────────────────────────────────

    def get_aging_distribution(self, company_id: int) -> List[Dict[str, Any]]:
        """Bucket in-stock vehicles by days on lot."""
        return self.query_all('''
            SELECT bucket, COUNT(*) AS count,
                   COALESCE(SUM(current_price), 0) AS total_value
            FROM (
                SELECT
                    CASE
                        WHEN COALESCE(days_listed, CURRENT_DATE - COALESCE(arrival_date, acquisition_date)) <= 15 THEN '0-15'
                        WHEN COALESCE(days_listed, CURRENT_DATE - COALESCE(arrival_date, acquisition_date)) <= 30 THEN '16-30'
                        WHEN COALESCE(days_listed, CURRENT_DATE - COALESCE(arrival_date, acquisition_date)) <= 45 THEN '31-45'
                        WHEN COALESCE(days_listed, CURRENT_DATE - COALESCE(arrival_date, acquisition_date)) <= 60 THEN '46-60'
                        WHEN COALESCE(days_listed, CURRENT_DATE - COALESCE(arrival_date, acquisition_date)) <= 90 THEN '61-90'
                        ELSE '90+'
                    END AS bucket,
                    current_price
                FROM carpark_vehicles
                WHERE company_id = %s
                  AND status NOT IN ('SOLD','DELIVERED','SCRAPPED','RETURNED')
            ) sub
            GROUP BY bucket
            ORDER BY
                CASE bucket
                    WHEN '0-15' THEN 1 WHEN '16-30' THEN 2 WHEN '31-45' THEN 3
                    WHEN '46-60' THEN 4 WHEN '61-90' THEN 5 ELSE 6
                END
        ''', (company_id,))

    # ── Profitability overview ───────────────────────────────

    def get_profitability_overview(self, company_id: int,
                                    period_days: int = 90) -> Dict[str, Any]:
        """Aggregate profitability for recently sold vehicles."""
        return self.query_one('''
            WITH sold AS (
                SELECT
                    v.id,
                    v.sale_price,
                    v.acquisition_price,
                    COALESCE(v.total_cost, 0) AS total_cost,
                    (v.sale_price - COALESCE(v.acquisition_price, 0) - COALESCE(v.total_cost, 0)) AS gross_profit,
                    (v.sale_date - COALESCE(v.arrival_date, v.acquisition_date)) AS days_to_sell
                FROM carpark_vehicles v
                WHERE v.company_id = %s
                  AND v.status IN ('SOLD','DELIVERED')
                  AND v.sale_date >= CURRENT_DATE - (%s || ' days')::INTERVAL
                  AND v.sale_price IS NOT NULL
                  AND v.sale_price > 0
            )
            SELECT
                COUNT(*) AS vehicles_sold,
                COALESCE(SUM(sale_price), 0) AS total_revenue,
                COALESCE(SUM(acquisition_price), 0) AS total_acquisition,
                COALESCE(SUM(total_cost), 0) AS total_costs,
                COALESCE(SUM(gross_profit), 0) AS total_gross_profit,
                CASE WHEN SUM(sale_price) > 0
                     THEN ROUND(100.0 * SUM(gross_profit) / SUM(sale_price), 2)
                     ELSE 0 END AS avg_margin_percent,
                COALESCE(ROUND(AVG(gross_profit)), 0) AS avg_profit_per_unit,
                COALESCE(ROUND(AVG(days_to_sell)), 0) AS avg_days_to_sell
            FROM sold
        ''', (company_id, period_days))

    # ── Brand breakdown ──────────────────────────────────────

    def get_brand_breakdown(self, company_id: int) -> List[Dict[str, Any]]:
        """In-stock vehicle count and value by brand."""
        return self.query_all('''
            SELECT brand, COUNT(*) AS count,
                   COALESCE(SUM(current_price), 0) AS total_value,
                   COALESCE(ROUND(AVG(
                       COALESCE(days_listed, CURRENT_DATE - COALESCE(arrival_date, acquisition_date))
                   )), 0) AS avg_days
            FROM carpark_vehicles
            WHERE company_id = %s
              AND status NOT IN ('SOLD','DELIVERED','SCRAPPED','RETURNED')
              AND brand IS NOT NULL
            GROUP BY brand
            ORDER BY count DESC
        ''', (company_id,))

    # ── Monthly sales trend ──────────────────────────────────

    def get_monthly_sales(self, company_id: int,
                          months: int = 12) -> List[Dict[str, Any]]:
        """Monthly sold count + revenue for the last N months."""
        return self.query_all('''
            SELECT
                TO_CHAR(sale_date, 'YYYY-MM') AS month,
                COUNT(*) AS sold,
                COALESCE(SUM(sale_price), 0) AS revenue,
                COALESCE(SUM(sale_price - COALESCE(acquisition_price, 0) - COALESCE(total_cost, 0)), 0) AS gross_profit
            FROM carpark_vehicles
            WHERE company_id = %s
              AND status IN ('SOLD','DELIVERED')
              AND sale_date >= (DATE_TRUNC('month', CURRENT_DATE) - (%s || ' months')::INTERVAL)
              AND sale_price IS NOT NULL
            GROUP BY TO_CHAR(sale_date, 'YYYY-MM')
            ORDER BY month
        ''', (company_id, months))

    # ── Publishing performance ───────────────────────────────

    def get_publishing_stats(self, company_id: int) -> Dict[str, Any]:
        """Aggregate listing views/inquiries across active listings."""
        return self.query_one('''
            SELECT
                COUNT(DISTINCT l.vehicle_id) AS vehicles_published,
                COUNT(l.id) AS total_listings,
                COALESCE(SUM(l.views), 0) AS total_views,
                COALESCE(SUM(l.inquiries), 0) AS total_inquiries,
                CASE WHEN SUM(l.views) > 0
                     THEN ROUND(100.0 * SUM(l.inquiries) / SUM(l.views), 2)
                     ELSE 0 END AS inquiry_rate
            FROM carpark_vehicle_listings l
            JOIN carpark_vehicles v ON v.id = l.vehicle_id
            WHERE v.company_id = %s
              AND l.status = 'active'
        ''', (company_id,))

    # ── Cost analysis ────────────────────────────────────────

    def get_cost_overview(self, company_id: int) -> List[Dict[str, Any]]:
        """Aggregate costs by type across all in-stock vehicles."""
        return self.query_all('''
            SELECT c.cost_type,
                   COUNT(*) AS entries,
                   COUNT(DISTINCT c.vehicle_id) AS vehicles,
                   COALESCE(SUM(c.amount), 0) AS total_amount
            FROM carpark_vehicle_costs c
            JOIN carpark_vehicles v ON v.id = c.vehicle_id
            WHERE v.company_id = %s
              AND v.status NOT IN ('SOLD','DELIVERED','SCRAPPED','RETURNED')
            GROUP BY c.cost_type
            ORDER BY total_amount DESC
        ''', (company_id,))

    # ── Recent activity ──────────────────────────────────────

    def get_recent_activity(self, company_id: int,
                            limit: int = 20) -> List[Dict[str, Any]]:
        """Recent status changes across all vehicles."""
        return self.query_all('''
            SELECT h.id, h.vehicle_id, h.old_status, h.new_status,
                   h.created_at, h.notes,
                   v.brand, v.model, v.vin
            FROM carpark_status_history h
            JOIN carpark_vehicles v ON v.id = h.vehicle_id
            WHERE v.company_id = %s
            ORDER BY h.created_at DESC
            LIMIT %s
        ''', (company_id, limit))
