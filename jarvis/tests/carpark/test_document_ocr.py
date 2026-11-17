"""Unit tests for the talon/CIV OCR response parser.

`parse_document_response` is pure (no HTTP/LLM/DB) — it normalises the vision
model's JSON. Focus here: the engine-capacity "cm3 fusion" recovery that stops
Autovit rejecting adverts with engine_capacity >= 9000.
"""
import json

from carpark.services.document_ocr import parse_document_response


def _resp(**fields):
    fields.setdefault('document_type', 'talon')
    return json.dumps(fields)


def test_engine_capacity_cm3_fusion_is_recovered():
    # The talon prints "2967 cm3"; the vision model sometimes fuses the unit's
    # trailing "3" into the number (-> 29673). No car engine is >= 9000 cmc, so
    # the parser drops the extra digit back to the real value.
    fields, doc_type = parse_document_response(_resp(engine_displacement_cc=29673))
    assert fields['engine_displacement_cc'] == 2967
    assert doc_type == 'talon'


def test_engine_capacity_realistic_value_untouched():
    fields, _ = parse_document_response(_resp(engine_displacement_cc=2967))
    assert fields['engine_displacement_cc'] == 2967


def test_engine_capacity_absent_does_not_crash():
    fields, _ = parse_document_response(_resp(brand='Audi'))
    assert 'engine_displacement_cc' not in fields
    assert fields['brand'] == 'Audi'


def test_other_fusion_examples_recovered():
    # Spot-check the real production corruptions (correct = stored // 10).
    for bad, good in [(39963, 3996), (19843, 1984), (13533, 1353), (19693, 1969)]:
        fields, _ = parse_document_response(_resp(engine_displacement_cc=bad))
        assert fields['engine_displacement_cc'] == good, (bad, good)


def test_kw_to_hp_derivation_still_works():
    # Regression: the existing kW->hp fill must be unaffected by the new guard.
    fields, _ = parse_document_response(_resp(engine_power_kw=210))
    assert fields['engine_power_hp'] == round(210 * 1.35962)
