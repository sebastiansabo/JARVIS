"""Unit test for the NOT NULL -> user-facing message helper (no DB needed)."""
from carpark.routes.vehicles import _missing_field_message


class _Diag:
    def __init__(self, col):
        self.column_name = col


class _NotNull(Exception):
    def __init__(self, col):
        self.diag = _Diag(col)


def test_maps_known_column_to_romanian_label():
    assert _missing_field_message(_NotNull('category')) == 'Câmp obligatoriu lipsă: Tip stoc (categorie)'


def test_falls_back_to_raw_column_when_unknown():
    assert _missing_field_message(_NotNull('some_column')) == 'Câmp obligatoriu lipsă: some_column'


def test_handles_exception_without_diagnostics():
    assert _missing_field_message(Exception('boom')) == 'Câmp obligatoriu lipsă: necunoscut'
