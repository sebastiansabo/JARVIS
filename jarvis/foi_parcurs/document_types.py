"""Document-type axis for Foi de Parcurs: Sales vs Service (courtesy car).

`document_type` rides alongside route_type/source/is_internal on foi_de_parcurs
AND on fp_vehicles. A session may only attach to a vehicle in the same pool.
Values are the internal keys; user-facing labels ("Vânzări" / "Mașini de
curtoazie") live in the frontend only.
"""

SALES = 'sales'
SERVICE = 'service'
VALID = {SALES, SERVICE}


def normalize(value) -> str:
    """Coerce any input to a valid document_type; unknown/blank -> 'sales'
    (all legacy data is Sales)."""
    v = (value or '').strip().lower() if isinstance(value, str) else (value or '')
    return v if v in VALID else SALES


def pools_match(session_document_type, vehicle_document_type) -> bool:
    """True when a session's document_type equals its vehicle's pool (after
    normalizing blanks to 'sales'). The submit-time isolation rule."""
    return normalize(session_document_type) == normalize(vehicle_document_type)
