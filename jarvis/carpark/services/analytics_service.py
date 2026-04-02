"""Analytics Service — Business logic for CarPark dashboard & KPIs."""
import logging
from typing import Dict, Any

from carpark.repositories.analytics_repository import AnalyticsRepository

logger = logging.getLogger('jarvis.carpark.analytics')

_repo = AnalyticsRepository()


class AnalyticsService:
    """Assembles dashboard data from repository queries."""

    def get_dashboard(self, company_id: int,
                      profit_period: int = 90) -> Dict[str, Any]:
        """Full dashboard payload — single call for the frontend."""
        summary = _repo.get_inventory_summary(company_id) or {}
        kpis = _repo.get_kpis(company_id) or {}
        aging = _repo.get_aging_distribution(company_id) or []
        profitability = _repo.get_profitability_overview(company_id, profit_period) or {}
        brands = _repo.get_brand_breakdown(company_id) or []
        monthly = _repo.get_monthly_sales(company_id, 12) or []
        publishing = _repo.get_publishing_stats(company_id) or {}
        costs = _repo.get_cost_overview(company_id) or []
        activity = _repo.get_recent_activity(company_id, 15) or []

        # Compute GROI: margin% × turn rate
        margin_pct = float(profitability.get('avg_margin_percent') or 0)
        turn_rate = float(kpis.get('inventory_turn_rate') or 0)
        groi = round(margin_pct * turn_rate / 100, 2) if margin_pct and turn_rate else 0

        return {
            'summary': summary,
            'kpis': {**kpis, 'groi': groi},
            'aging_distribution': aging,
            'profitability': profitability,
            'brand_breakdown': brands,
            'monthly_sales': monthly,
            'publishing': publishing,
            'cost_overview': costs,
            'recent_activity': activity,
        }

    def get_summary(self, company_id: int) -> Dict[str, Any]:
        """Lightweight summary — for sidebar badges or quick stats."""
        return _repo.get_inventory_summary(company_id) or {}

    def get_kpis(self, company_id: int) -> Dict[str, Any]:
        """KPIs only."""
        kpis = _repo.get_kpis(company_id) or {}
        profitability = _repo.get_profitability_overview(company_id, 90) or {}
        margin_pct = float(profitability.get('avg_margin_percent') or 0)
        turn_rate = float(kpis.get('inventory_turn_rate') or 0)
        groi = round(margin_pct * turn_rate / 100, 2) if margin_pct and turn_rate else 0
        return {**kpis, 'groi': groi, 'profitability': profitability}

    def get_status_breakdown(self, company_id: int):
        return _repo.get_status_breakdown(company_id)

    def get_category_breakdown(self, company_id: int):
        return _repo.get_category_breakdown(company_id)

    def get_aging_distribution(self, company_id: int):
        return _repo.get_aging_distribution(company_id)

    def get_brand_breakdown(self, company_id: int):
        return _repo.get_brand_breakdown(company_id)

    def get_monthly_sales(self, company_id: int, months: int = 12):
        return _repo.get_monthly_sales(company_id, months)

    def get_cost_overview(self, company_id: int):
        return _repo.get_cost_overview(company_id)

    def get_recent_activity(self, company_id: int, limit: int = 15):
        return _repo.get_recent_activity(company_id, limit)
