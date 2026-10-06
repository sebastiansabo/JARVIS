"""Tests for CarPark talon/CIV document OCR extraction.

The scan-first intake generalises the CIV-only AI-vision flow to also read a
Romanian talon (Certificat de Înmatriculare), auto-detect which document it is,
and normalise the extracted fields. The parsing + normalisation is pure logic
and is tested here directly; the HTTP route is a thin wrapper around it.
"""
import os
import sys
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


class TestParseDocumentResponse:
    def test_civ_response_detected_as_civ(self):
        from carpark.services.document_ocr import parse_document_response
        text = (
            '{"document_type": "civ", "vin": "WVWZZZ1KZAW000001", '
            '"brand": "VW", "model": "Golf", "first_registration_date": "2020-05-01"}'
        )
        fields, doc_type = parse_document_response(text)
        assert doc_type == 'civ'
        assert fields['vin'] == 'WVWZZZ1KZAW000001'
        assert fields['brand'] == 'VW'
        # document_type must be stripped out of the applied vehicle fields
        assert 'document_type' not in fields

    def test_talon_response_detected_and_keeps_registration_number(self):
        from carpark.services.document_ocr import parse_document_response
        text = (
            '{"document_type": "talon", "registration_number": "B123ABC", '
            '"vin": "WVWZZZ1KZAW000001", "brand": "VW"}'
        )
        fields, doc_type = parse_document_response(text)
        assert doc_type == 'talon'
        assert fields['registration_number'] == 'B123ABC'

    def test_markdown_fenced_json_is_parsed(self):
        from carpark.services.document_ocr import parse_document_response
        text = '```json\n{"document_type": "civ", "brand": "Audi"}\n```'
        fields, doc_type = parse_document_response(text)
        assert doc_type == 'civ'
        assert fields['brand'] == 'Audi'

    def test_kw_only_derives_horsepower(self):
        from carpark.services.document_ocr import parse_document_response
        text = '{"document_type": "civ", "engine_power_kw": 100}'
        fields, _ = parse_document_response(text)
        # 100 kW * 1.35962 ≈ 136 CP
        assert fields['engine_power_hp'] == 136

    def test_empty_values_are_dropped(self):
        from carpark.services.document_ocr import parse_document_response
        text = '{"document_type": "talon", "brand": "VW", "model": "", "variant": null}'
        fields, _ = parse_document_response(text)
        assert fields['brand'] == 'VW'
        assert 'model' not in fields
        assert 'variant' not in fields

    def test_unreadable_text_is_unknown_with_no_fields(self):
        from carpark.services.document_ocr import parse_document_response
        fields, doc_type = parse_document_response('nu am putut citi nimic')
        assert fields == {}
        assert doc_type == 'unknown'

    def test_missing_document_type_defaults_to_unknown(self):
        from carpark.services.document_ocr import parse_document_response
        fields, doc_type = parse_document_response('{"brand": "VW"}')
        assert doc_type == 'unknown'
        assert fields['brand'] == 'VW'


class TestExtractVehicleDocument:
    def test_image_upload_builds_image_block_and_returns_parsed(self):
        from carpark.services import document_ocr
        captured = {}

        def fake_call(messages, max_tokens=1024):
            captured['messages'] = messages
            return '{"document_type": "talon", "registration_number": "B99XYZ"}'

        with patch.object(document_ocr, '_llm_call', fake_call):
            fields, doc_type = document_ocr.extract_vehicle_document(b'\xff\xd8\xff', 'image/jpeg')

        assert doc_type == 'talon'
        assert fields['registration_number'] == 'B99XYZ'
        block = captured['messages'][0]['content'][0]
        assert block['type'] == 'image'
        assert block['source']['media_type'] == 'image/jpeg'

    def test_pdf_upload_builds_document_block(self):
        from carpark.services import document_ocr

        def fake_call(messages, max_tokens=1024):
            return '{"document_type": "civ", "brand": "BMW"}'

        with patch.object(document_ocr, '_llm_call', fake_call):
            fields, doc_type = document_ocr.extract_vehicle_document(b'%PDF-1.4', 'application/pdf')

        assert doc_type == 'civ'
        assert fields['brand'] == 'BMW'
