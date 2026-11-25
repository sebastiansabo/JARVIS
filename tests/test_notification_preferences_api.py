"""Unit tests for the preferences API payload assembly + update validation.

Pure-logic layer behind GET/POST /notifications/api/preferences:
  - build_preferences_view(rows): effective per-channel values for every
    registry category given the user's stored rows, plus the category list +
    mandatory set + channel order (so the client renders without the rules).
  - validate_preference_update(slug): reject unknown + mandatory slugs.
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

import database  # noqa: E402, F401  (init before core.* to avoid circular import)

from core.notifications.categories import (
    build_preferences_view, validate_preference_update, CATEGORY_REGISTRY, CHANNELS,
)


class TestBuildView:
    def test_empty_rows_yields_defaults_for_every_category(self):
        view = build_preferences_view([])
        assert set(view['preferences']) == set(CATEGORY_REGISTRY)
        assert view['preferences']['chat'] == {
            'in_app': True, 'push': True, 'email': False, 'sms': False,
        }
        assert view['preferences']['allocation'] == {
            'in_app': False, 'push': False, 'email': True, 'sms': False,
        }

    def test_mandatory_categories_effective_all_on(self):
        view = build_preferences_view([])
        assert view['preferences']['approvals'] == {
            'in_app': True, 'push': True, 'email': True, 'sms': True,
        }
        assert sorted(view['mandatory']) == ['approvals', 'system']

    def test_stored_optout_reflected_in_effective(self):
        rows = [{'category_slug': 'chat', 'in_app_enabled': None,
                 'push_enabled': False, 'email_enabled': True, 'sms_enabled': None}]
        view = build_preferences_view(rows)
        assert view['preferences']['chat'] == {
            'in_app': True, 'push': False, 'email': True, 'sms': False,
        }

    def test_categories_carry_name_and_mandatory_flag(self):
        view = build_preferences_view([])
        by_slug = {c['slug']: c for c in view['categories']}
        assert by_slug['approvals']['mandatory'] is True
        assert by_slug['chat']['mandatory'] is False
        assert by_slug['chat']['name']  # Romanian display name present

    def test_channels_order(self):
        assert build_preferences_view([])['channels'] == list(CHANNELS)


class TestValidateUpdate:
    def test_unknown_slug_rejected_400(self):
        err = validate_preference_update('not_a_category')
        assert err is not None and err[1] == 400

    def test_mandatory_slug_rejected_422(self):
        err = validate_preference_update('approvals')
        assert err is not None and err[1] == 422

    def test_valid_slug_ok(self):
        assert validate_preference_update('chat') is None
