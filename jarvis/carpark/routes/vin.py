"""VIN Decoder API routes.

Endpoints:
  GET /api/carpark/vin/decode/<vin>   — Decode VIN (with caching)
  GET /api/carpark/vin/validate/<vin> — Validate VIN format
  GET /api/carpark/vin/providers      — Provider status

All endpoints require authentication + carpark access permission.
"""
import logging

from flask import request, jsonify
from flask_login import login_required

from carpark import carpark_bp
from carpark.routes.vehicles import carpark_required
from carpark.connectors.vin_decoder import (
    VINDecoderClient,
    VINDecoderError,
    VINValidationError,
    VINNotFoundError,
    QuotaExhaustedError,
    ProviderUnavailableError,
)

logger = logging.getLogger('jarvis.carpark.vin_decoder')

_vin_client = None


def _get_vin_client() -> VINDecoderClient:
    """Lazy-init VIN decoder client (avoids import-time env var issues)."""
    global _vin_client
    if _vin_client is None:
        _vin_client = VINDecoderClient()
    return _vin_client


@carpark_bp.route('/vin/decode/<vin>', methods=['GET'])
@login_required
@carpark_required
def decode_vin(vin):
    """Decode VIN and return vehicle specs.

    Query params:
        refresh=true — skip cache and re-decode from provider
    """
    skip_cache = request.args.get('refresh', 'false').lower() == 'true'

    try:
        client = _get_vin_client()
        specs = client.decode(vin, skip_cache=skip_cache)
        return jsonify({
            'success': True,
            'data': {
                'specs': specs.to_dict(),
                'vehicle_fields': specs.to_vehicle_fields(),
                'provider': specs.provider,
                'confidence': specs.confidence_score,
            },
        })
    except VINValidationError as e:
        return jsonify({
            'success': False, 'error': str(e), 'code': e.code,
        }), 400
    except VINNotFoundError as e:
        return jsonify({
            'success': False, 'error': str(e), 'code': e.code,
        }), 404
    except QuotaExhaustedError as e:
        return jsonify({
            'success': False, 'error': str(e), 'code': e.code,
        }), 429
    except ProviderUnavailableError as e:
        return jsonify({
            'success': False, 'error': str(e), 'code': e.code,
        }), 503
    except VINDecoderError as e:
        logger.exception(f'VIN decode failed: {e}')
        return jsonify({
            'success': False, 'error': 'Internal error',
        }), 500


@carpark_bp.route('/vin/validate/<vin>', methods=['GET'])
@login_required
@carpark_required
def validate_vin(vin):
    """Validate VIN format without decoding (no API calls)."""
    client = _get_vin_client()
    result = client.validate(vin)
    return jsonify({'success': True, 'data': result})


@carpark_bp.route('/vin/providers', methods=['GET'])
@login_required
@carpark_required
def vin_provider_status():
    """Get status of VIN decoder providers."""
    client = _get_vin_client()
    status = client.get_provider_status()
    return jsonify({'success': True, 'data': status})
