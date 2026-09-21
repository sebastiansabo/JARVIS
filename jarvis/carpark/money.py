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
derivation is valid for every source.
"""

# SQL fragment — requires the carpark_vehicles row aliased as `v`.
NET_BUY_SQL = (
    "COALESCE(v.purchase_price_net, "
    "v.acquisition_price / (1 + COALESCE(v.purchase_vat_rate, 0) / 100.0), 0)"
)


def net_buy(vehicle) -> float:
    """Python equivalent of NET_BUY_SQL for a vehicle dict/row."""
    if not vehicle:
        return 0.0
    ppn = vehicle.get('purchase_price_net')
    if ppn is not None:
        return float(ppn)
    gross = vehicle.get('acquisition_price')
    if gross is None:
        return 0.0
    vat = float(vehicle.get('purchase_vat_rate') or 0)
    return float(gross) / (1 + vat / 100.0)
