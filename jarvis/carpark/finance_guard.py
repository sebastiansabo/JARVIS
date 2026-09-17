"""Single source of truth for CarPark finance fields hidden from users
without can_view_carpark_finance. Used by the Dispo board, the vehicle
detail payload and analytics so JSON/xlsx paths can never drift."""

# Money fields on a vehicle / dispo row.
FINANCE_VEHICLE_FIELDS = ('acquisition_price', 'total_costs', 'gross_margin',
                          'margin_pct', 'bonus_leasing')
# Money fields on analytics KPI blocks.
FINANCE_KPI_FIELDS = ('gross_margin_mtd',)


def strip_finance_fields(payload, fields=FINANCE_VEHICLE_FIELDS):
    """Remove `fields` from a dict in place; returns it. No-op if not a dict."""
    if isinstance(payload, dict):
        for f in fields:
            payload.pop(f, None)
    return payload
