"""Tests for Task 5 (Autovit Taxonomy Mapping project): the two new
`AutovitClient` taxonomy methods (`get_makes`/`get_models`), the
`taxonomy_sync.pull_taxonomy()` cache-row builder, and the pure
`taxonomy_sync.suggest()` auto-suggest ranker.

API-free: client methods mock `AutovitClient._request` (same idiom as
test_autovit_push.py — the `responses` package isn't in this repo's
dependencies); `pull_taxonomy` is tested against a hand-rolled FakeClient
returning sample category/makes/models payloads (no network, no DB);
`suggest` is a pure function tested directly.
"""
from unittest.mock import patch

from carpark.connectors.autovit.client import AutovitClient
from carpark.connectors.autovit import taxonomy_sync as ts


# ─────────────────────────────────────────────────────────────────────────
# AutovitClient.get_makes / get_models
# ─────────────────────────────────────────────────────────────────────────

def _client():
    return AutovitClient("https://www.autovit.ro/api/open", "cid", "sec", "u", "p")


def test_get_makes_parses_options():
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.json.return_value = {
            "options": {"audi": {"en": "Audi", "ro": "Audi"},
                        "bmw": {"en": "BMW", "ro": "BMW"}}
        }
        out = c.get_makes()
        req.assert_called_once_with("GET", "/categories/29/makes", timeout=10)
        assert out == {"audi": {"en": "Audi", "ro": "Audi"},
                        "bmw": {"en": "BMW", "ro": "BMW"}}


def test_get_models_audi():
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.json.return_value = {
            "options": {
                "a6": {"en": "A6", "ro": "A6"},
                "a6-avant-e-tron": {"en": "A6 Avant e-tron", "ro": "A6 Avant e-tron"},
            }
        }
        out = c.get_models("audi")
        req.assert_called_once_with("GET", "/categories/29/models/audi", timeout=10)
        assert set(out) == {"a6", "a6-avant-e-tron"}
        assert out["a6"]["ro"] == "A6"


def test_get_models_missing_options_returns_empty_dict():
    """A malformed/empty response body must not raise — just no models."""
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.json.return_value = {}
        assert c.get_models("unknown-make") == {}


# ─────────────────────────────────────────────────────────────────────────
# taxonomy_sync.pull_taxonomy — shapes a client's live category/makes/models
# into carpark_autovit_taxonomy_cache rows.
# ─────────────────────────────────────────────────────────────────────────

CATEGORY = {
    "id": 29,
    "parameters": [
        {"code": "fuel_type", "type": "select",
         "labels": {"ro": "Combustibil", "en": "Fuel"},
         "options": {"petrol": {"ro": "Benzină", "en": "Petrol"},
                      "diesel": {"ro": "Motorină", "en": "Diesel"}}},
        # drive dimension writes to the Autovit PARAM named "transmission"
        # (taxonomy_map.DIMENSIONS['drive'] == ('param', 'transmission')).
        {"code": "transmission", "type": "select",
         "labels": {"ro": "Tracțiune", "en": "Drive"},
         "options": {"front-wheel": {"ro": "Față", "en": "Front"}}},
        {"code": "air_conditioning_type", "type": "select",
         "labels": {"ro": "Climatizare", "en": "AC"},
         "options": {"manual": {"ro": "Manuală", "en": "Manual"}}},
        # checkbox params -> equipment cache rows
        {"code": "apple_carplay", "type": "checkbox",
         "labels": {"ro": "Apple CarPlay", "en": "Apple CarPlay"}},
        {"code": "360_view_camera", "type": "checkbox",
         "labels": {"ro": "Cameră video 360°", "en": "360 view camera"}},
        # a param belonging to NEITHER a registered dimension NOR type
        # checkbox must be ignored entirely (e.g. a free-text/number field).
        {"code": "door_count", "type": "number", "labels": {"ro": "Uși", "en": "Doors"}},
    ],
}

MAKES = {"audi": {"en": "Audi", "ro": "Audi"}, "bmw": {"en": "BMW", "ro": "BMW"}}
MODELS = {
    "audi": {"a6": {"en": "A6", "ro": "A6"}},
    "bmw": {"x5": {"en": "X5", "ro": "X5"}},
}


class FakeClient:
    def __init__(self):
        self.get_models_calls = []

    def get_category(self, category_id):
        assert category_id == 29
        return CATEGORY

    def get_makes(self):
        return MAKES

    def get_models(self, make):
        self.get_models_calls.append(make)
        return MODELS[make]


def _rows_by(rows, **kwargs):
    return [r for r in rows if all(r.get(k) == v for k, v in kwargs.items())]


def test_pull_taxonomy_shapes_rows():
    rows = ts.pull_taxonomy(FakeClient())

    # fuel_type: one row per option value, param_type carried from the param.
    fuel = _rows_by(rows, dimension="fuel_type", code="petrol")
    assert len(fuel) == 1
    assert fuel[0]["ro_label"] == "Benzină"
    assert fuel[0]["param_type"] == "select"
    assert fuel[0]["make"] is None

    # drive dimension sourced from the "transmission" PARAM (not a "drive"
    # named param -- there isn't one).
    drive = _rows_by(rows, dimension="drive", code="front-wheel")
    assert len(drive) == 1
    assert drive[0]["ro_label"] == "Față"

    # select dimension (air_conditioning_type) treated the same way.
    ac = _rows_by(rows, dimension="air_conditioning_type", code="manual")
    assert len(ac) == 1
    assert ac[0]["param_type"] == "select"

    # equipment: one row per checkbox PARAM; code IS the equipment code.
    carplay = _rows_by(rows, dimension="equipment", code="apple_carplay")
    assert len(carplay) == 1
    assert carplay[0]["ro_label"] == "Apple CarPlay"
    assert carplay[0]["param_type"] == "checkbox"

    cam360 = _rows_by(rows, dimension="equipment", code="360_view_camera")
    assert len(cam360) == 1
    assert cam360[0]["param_type"] == "checkbox"

    # the "door_count"/number param is neither a registered dimension's
    # param nor a checkbox -- no row should be emitted for it at all.
    assert not _rows_by(rows, code="door_count")

    # make rows: unscoped (make column is None on the make dimension itself).
    audi_make = _rows_by(rows, dimension="make", code="audi")
    assert len(audi_make) == 1
    assert audi_make[0]["ro_label"] == "Audi"
    assert audi_make[0]["make"] is None

    # model rows: carry the owning make.
    a6 = _rows_by(rows, dimension="model", code="a6")
    assert len(a6) == 1
    assert a6[0]["make"] == "audi"
    assert a6[0]["ro_label"] == "A6"

    x5 = _rows_by(rows, dimension="model", code="x5")
    assert len(x5) == 1
    assert x5[0]["make"] == "bmw"


def test_pull_taxonomy_fetches_models_once_per_make():
    client = FakeClient()
    ts.pull_taxonomy(client)
    assert sorted(client.get_models_calls) == ["audi", "bmw"]


def test_pull_taxonomy_empty_category_and_makes_returns_no_rows():
    class EmptyClient:
        def get_category(self, category_id):
            return {}

        def get_makes(self):
            return {}

        def get_models(self, make):
            raise AssertionError("must not be called with no makes")

    assert ts.pull_taxonomy(EmptyClient()) == []


# ─────────────────────────────────────────────────────────────────────────
# taxonomy_sync.suggest — pure auto-suggest ranker over cache rows.
# ─────────────────────────────────────────────────────────────────────────

def _row(dimension, code, ro_label, make=None):
    return {"dimension": dimension, "code": code, "ro_label": ro_label,
            "param_type": "checkbox" if dimension == "equipment" else None,
            "make": make, "options": None}


def test_suggest_filters_by_dimension():
    rows = [
        _row("equipment", "apple_carplay", "Apple CarPlay"),
        _row("fuel_type", "petrol", "Benzină"),
    ]
    out = ts.suggest(rows, "fuel_type", "benzina")
    assert [c for c, _, _ in out] == ["petrol"]


def test_suggest_model_scoped_by_make():
    rows = [
        _row("model", "a6", "A6", make="audi"),
        _row("model", "a6-other", "A6 (other make)", make="volkswagen"),
    ]
    out = ts.suggest(rows, "model", "a6", make="audi")
    codes = [c for c, _, _ in out]
    assert codes == ["a6"]        # the volkswagen-scoped row must not appear


def test_suggest_respects_limit():
    rows = [_row("equipment", f"code_{i}", "scaune incalzite") for i in range(10)]
    out = ts.suggest(rows, "equipment", "scaune incalzite", limit=3)
    assert len(out) == 3


def test_suggest_no_match_returns_empty():
    rows = [_row("equipment", "apple_carplay", "Apple CarPlay")]
    assert ts.suggest(rows, "equipment", "cu totul altceva necunoscut") == []


# ── Quality-bar tests (hard requirement): must beat naive token-overlap ──

def _naive_overlap_rank(cache_rows, source_value):
    """The thing suggest() must beat: plain, non-folding exact token-set
    overlap over the RO label ONLY (no diacritic fold, no code tokens). Ties
    are left in cache-row (list) order, as a naive "first match wins"
    implementation would."""
    q = set(source_value.lower().split())
    scored = []
    for row in cache_rows:
        label_tokens = set((row.get("ro_label") or "").lower().split())
        scored.append((row["code"], len(q & label_tokens)))
    scored.sort(key=lambda t: -t[1])
    return scored


def test_suggest_beats_token_overlap():
    """'scaune incalzite fata' (admin types without diacritics) must rank a
    HEATED seat code above a VENTILATED one. A naive, non-folding overlap
    ties 1-1 on the shared 'scaune' token alone (diacritics mean
    'incalzite' != 'încălzite' byte-for-byte) and — resolved by list order —
    wrongly picks the ventilated row, which is listed first here."""
    rows = [
        _row("equipment", "ventilated_seats_front", "Scaune ventilate față"),
        _row("equipment", "heated_seats_front", "Scaune încălzite față"),
    ]
    query = "scaune incalzite fata"

    naive = _naive_overlap_rank(rows, query)
    assert naive[0][0] == "ventilated_seats_front"   # the naive baseline gets it WRONG

    out = ts.suggest(rows, "equipment", query)
    codes = [c for c, _, _ in out]
    assert codes.index("heated_seats_front") < codes.index("ventilated_seats_front")


def test_suggest_360_not_rear():
    """A '360' camera query must rank `360_view_camera` above
    `rear_view_camera`. RO labels here are deliberately identical/generic
    ("Cameră video") so the ranking can ONLY come from the CODE tokens
    ('360' vs 'rear') -- proving suggest() genuinely scores code tokens,
    not just RO labels."""
    rows = [
        _row("equipment", "rear_view_camera", "Cameră video"),
        _row("equipment", "360_view_camera", "Cameră video"),
    ]
    out = ts.suggest(rows, "equipment", "camera 360")
    codes = [c for c, _, _ in out]
    assert codes.index("360_view_camera") < codes.index("rear_view_camera")


def test_suggest_scores_are_descending_and_bounded():
    rows = [
        _row("equipment", "heated_seats_front", "Scaune încălzite față"),
        _row("equipment", "apple_carplay", "Apple CarPlay"),
    ]
    out = ts.suggest(rows, "equipment", "scaune incalzite fata")
    scores = [s for _, _, s in out]
    assert all(0 < s <= 1 for s in scores)
    assert scores == sorted(scores, reverse=True)
