"""Temporary admin utility routes (superadmin-only)."""
import subprocess
import sys
import os

from flask import Blueprint, jsonify
from flask_login import current_user

admin_bp = Blueprint('admin', __name__)

MIGRATION_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'scripts', 'migrate_legacy_to_new.py'
)


@admin_bp.post('/api/admin/run-migration')
def run_migration():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if current_user.role_id != 1:
        return jsonify({'success': False, 'error': 'Admin only'}), 403

    try:
        result = subprocess.run(
            [sys.executable, MIGRATION_SCRIPT],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return jsonify({'success': False, 'error': output}), 500
        return jsonify({'success': True, 'output': output})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Migration timed out (>120s)'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
