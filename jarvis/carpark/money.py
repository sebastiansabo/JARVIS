"""Canonical money helpers for CarPark profitability reporting (EUR).

The NET purchase cost is the VAT-deductible cost basis: the stored
`purchase_price_net` when present, otherwise derived from the GROSS
`acquisition_price` and `purchase_vat_rate` (equals `acquisition_price` when
there is no VAT). Used by analytics and per-vehicle profitability so the buy
price is counted exactly once, on a net basis.

NOTE: assumes the import-created convention (acquisition_price = GROSS EUR,
purchase_price_net = NET EUR), which holds for all current prod data. The editor
write-path stores the opposite (acquisition_price = NET RON, purchase_price_net =
GROSS EUR); no editor-created cars exist on prod yet, but that write-path must be
reconciled before editor-created cars are sold.
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
