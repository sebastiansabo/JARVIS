"""Canonical money helpers for CarPark profitability reporting (EUR).

The NET purchase cost is the VAT-deductible cost basis: the stored
`purchase_price_net` when present, otherwise derived from the GROSS
`acquisition_price` and `purchase_vat_rate` (equals `acquisition_price` when
there is no VAT). Used by analytics and per-vehicle profitability so the buy
price is counted exactly once, on a net basis.

NOTE: the canonical convention (acquisition_price = GROSS EUR,
purchase_price_net = NET EUR, acquisition_currency = 'EUR') holds for all data:
imports, transfers, AND the editor write-path. The editor enters the acquisition
in net-LEI + a BNR kurs (or GROSS EUR directly for EUR-native cars) and stores
the canonical EUR pair via toCanonical/canonicalFromGrossEur — so this NET-buy
derivation is valid for every source. As a safety net, a legacy pre-migration
row (acquisition_currency = 'RON': NET LEI + GROSS-EUR purchase_price_net) is
still read correctly via the RON branch below.
"""

# SQL fragment — requires the carpark_vehicles row aliased as `v`.
# Legacy editor-convention rows (acquisition_currency = 'RON') stored
# acquisition_price as NET LEI and purchase_price_net as GROSS EUR, so the
# canonical COALESCE would read the wrong basis. The RON branch derives net EUR
# from NET LEI / kurs (or, without a kurs, from the gross-EUR purchase_price_net)
# — mirrors net_buy() and PricingSheet's 'RON' branch. Defense-in-depth: the
# backfill converts such rows to canonical, but this keeps analytics correct for
# any un-migrated one.
NET_BUY_SQL = (
    "CASE "
    "WHEN v.acquisition_currency = 'RON' "
    "AND COALESCE(v.acquisition_exchange_rate, 0) > 0 "
    "AND COALESCE(v.acquisition_price, 0) > 0 "
    "THEN v.acquisition_price / v.acquisition_exchange_rate "
    "WHEN v.acquisition_currency = 'RON' "
    "THEN COALESCE(v.purchase_price_net, 0) / (1 + COALESCE(v.purchase_vat_rate, 0) / 100.0) "
    "ELSE COALESCE(v.purchase_price_net, "
    "v.acquisition_price / (1 + COALESCE(v.purchase_vat_rate, 0) / 100.0), 0) "
    "END"
)


def net_buy(vehicle) -> float:
    """Python equivalent of NET_BUY_SQL for a vehicle dict/row."""
    if not vehicle:
        return 0.0
    vat = float(vehicle.get('purchase_vat_rate') or 0)
    # Legacy editor convention (acquisition_currency = 'RON'): acquisition_price
    # is NET LEI and purchase_price_net is the GROSS EUR paid — NOT canonical.
    # Net EUR = NET LEI / kurs; if no usable kurs, fall back to deriving net from
    # the gross-EUR purchase_price_net. Mirrors PricingSheet's 'RON' branch and
    # exists as a safety net for any un-backfilled row.
    if vehicle.get('acquisition_currency') == 'RON':
        net_lei = vehicle.get('acquisition_price')
        kurs = vehicle.get('acquisition_exchange_rate')
        if net_lei is not None and kurs is not None and float(kurs) > 0 and float(net_lei) > 0:
            return float(net_lei) / float(kurs)
        gross_eur = vehicle.get('purchase_price_net')
        if gross_eur is None:
            return 0.0
        return float(gross_eur) / (1 + vat / 100.0)
    ppn = vehicle.get('purchase_price_net')
    if ppn is not None:
        return float(ppn)
    gross = vehicle.get('acquisition_price')
    if gross is None:
        return 0.0
    return float(gross) / (1 + vat / 100.0)


# ── Cost currency → EUR ──────────────────────────────────────────────────────
# A cost's amount/vat is stored in its own `currency` (RON stays the source of
# truth). Its EUR value divides by `exchange_rate_eur` (= units of the cost's
# currency per 1 EUR, frozen at the cost's date by the write-path/backfill). A
# non-EUR cost with no rate falls back to its raw amount — today's behavior,
# never worse. Bare column names (amount/currency/exchange_rate_eur/vat_amount)
# are unambiguous in every reader: carpark_vehicles has none of those names.
COST_EUR_SQL = (
    "CASE WHEN currency = 'EUR' THEN amount "
    "WHEN COALESCE(exchange_rate_eur, 0) > 0 THEN amount / exchange_rate_eur "
    "ELSE amount END"
)

COST_VAT_EUR_SQL = (
    "CASE WHEN currency = 'EUR' THEN vat_amount "
    "WHEN COALESCE(exchange_rate_eur, 0) > 0 THEN vat_amount / exchange_rate_eur "
    "ELSE vat_amount END"
)


def _cost_field_eur(cost, field: str) -> float:
    """Python twin of COST_EUR_SQL for a cost dict's numeric field."""
    if not cost:
        return 0.0
    val = float(cost.get(field) or 0)
    if cost.get('currency') == 'EUR':
        return val
    rate = cost.get('exchange_rate_eur')
    if rate is not None and float(rate) > 0:
        return val / float(rate)
    return val


def cost_amount_eur(cost) -> float:
    """A cost's `amount` in EUR (Python twin of COST_EUR_SQL)."""
    return _cost_field_eur(cost, 'amount')


def cost_vat_eur(cost) -> float:
    """A cost's `vat_amount` in EUR (Python twin of COST_VAT_EUR_SQL)."""
    return _cost_field_eur(cost, 'vat_amount')


# Revenues convert identically (carpark_vehicle_revenues has the same
# amount/currency/exchange_rate_eur/vat_amount columns) — alias the one rule
# under revenue-named symbols for clarity at the revenue call sites.
REVENUE_EUR_SQL = COST_EUR_SQL
REVENUE_VAT_EUR_SQL = COST_VAT_EUR_SQL
revenue_amount_eur = cost_amount_eur
revenue_vat_eur = cost_vat_eur
