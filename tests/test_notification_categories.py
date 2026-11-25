"""Unit tests for the notification category registry.

Tests the canonical category registry that backs per-user notification
preferences — the single source of truth for which category slugs exist, which
are mandatory, and each category's default per-channel posture.

The registry's job is to prevent the slug-mismatch bug class (a preference that
looks set but never binds because its slug doesn't match what the code emits)
and to encode the locked defaults:
  - most categories: in-app + push ON, email + SMS OFF (opt-in)
  - 'allocation' (migrated from users.notify_on_allocation): email-only ON
  - mandatory ('approvals', 'system'): forced (resolution handled elsewhere)
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

# Import database (and its on-import init) BEFORE anything under core.*, so
# base_repository -> database resolves fully and we don't trip the known
# init-on-import circular import (see reference_jarvis_test_venv_python).
import database  # noqa: E402, F401

from core.notifications.categories import (
    CHANNELS,
    MANDATORY_CATEGORIES,
    CATEGORY_REGISTRY,
    default_channels,
    is_mandatory,
)


# Slugs actually emitted by notify_*/push call sites (grep of category=).
# Hardcoded here on purpose: this list is the contract the registry must cover.
EMITTED_SLUGS = {
    'system', 'approvals', 'chat', 'digest', 'smart_alert', 'hr_attendance',
    'hr_course_expiry', 'field_sales', 'ticketing', 'marketing', 'carpark',
    'buyback', 'performance', 'accounting', 'test_drive', 'happy_announce',
    'bnr_feed_down', 'fp_scheduled_block', 'fp_vehicle_expiry',
}


class TestChannels:
    def test_four_channels_in_order(self):
        assert CHANNELS == ('in_app', 'push', 'email', 'sms')


class TestRegistryCoverage:
    def test_registry_covers_every_emitted_slug(self):
        missing = EMITTED_SLUGS - set(CATEGORY_REGISTRY)
        assert not missing, f'registry missing emitted slugs: {sorted(missing)}'

    def test_registry_includes_allocation_migrated_slug(self):
        assert 'allocation' in CATEGORY_REGISTRY

    def test_every_category_has_a_romanian_name(self):
        for slug, meta in CATEGORY_REGISTRY.items():
            assert meta.get('name'), f'{slug} has no display name'

    def test_every_category_defines_all_four_channel_defaults(self):
        for slug in CATEGORY_REGISTRY:
            defaults = default_channels(slug)
            assert set(defaults) == set(CHANNELS), f'{slug} defaults incomplete'
            assert all(isinstance(v, bool) for v in defaults.values())


class TestMandatory:
    def test_mandatory_is_exactly_approvals_and_system(self):
        assert MANDATORY_CATEGORIES == frozenset({'approvals', 'system'})

    def test_is_mandatory_true_for_approvals(self):
        assert is_mandatory('approvals') is True

    def test_is_mandatory_false_for_chat(self):
        assert is_mandatory('chat') is False


class TestChannelDefaults:
    def test_normal_category_in_app_and_push_on_email_sms_off(self):
        # 'chat' is a representative non-mandatory broadcast category.
        assert default_channels('chat') == {
            'in_app': True, 'push': True, 'email': False, 'sms': False,
        }

    def test_allocation_is_email_only(self):
        # Preserves today's behaviour: allocation was email-only, default on.
        assert default_channels('allocation') == {
            'in_app': False, 'push': False, 'email': True, 'sms': False,
        }

    def test_unknown_slug_falls_back_to_safe_default(self):
        # An un-registered slug must not silently enable paid channels.
        assert default_channels('totally_unknown') == {
            'in_app': True, 'push': True, 'email': False, 'sms': False,
        }
