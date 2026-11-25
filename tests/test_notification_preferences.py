"""Unit tests for per-user notification preference resolution.

Pure-logic tests for the gate's heart: given a category, a channel, and a user's
stored preference row (or none), decide whether the user receives it. Encodes the
locked rules:
  - mandatory categories ('approvals', 'system') are forced ON on every channel,
    regardless of any stored preference (user cannot mute them)
  - otherwise the per-category default applies (in-app+push ON, email+SMS OFF;
    'allocation' email-only) unless the user set an explicit per-channel value
  - a NULL column inherits the category default (only an explicit toggle opts out)
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

import database  # noqa: E402, F401  (init before core.* to avoid circular import)

from core.notifications.categories import effective_channels, filter_recipients


class TestEffectiveChannels:
    def test_mandatory_forced_on_even_if_user_disabled_everything(self):
        pref = {'in_app': False, 'push': False, 'email': False, 'sms': False}
        assert effective_channels('approvals', pref) == {
            'in_app': True, 'push': True, 'email': True, 'sms': True,
        }

    def test_non_mandatory_no_pref_uses_category_default(self):
        assert effective_channels('chat', None) == {
            'in_app': True, 'push': True, 'email': False, 'sms': False,
        }

    def test_explicit_opt_in_enables_email(self):
        pref = {'in_app': None, 'push': None, 'email': True, 'sms': None}
        eff = effective_channels('chat', pref)
        assert eff['email'] is True
        assert eff['in_app'] is True   # NULL inherits default (on)
        assert eff['sms'] is False     # NULL inherits default (off)

    def test_explicit_opt_out_disables_push(self):
        pref = {'in_app': None, 'push': False, 'email': None, 'sms': None}
        eff = effective_channels('chat', pref)
        assert eff['push'] is False
        assert eff['in_app'] is True

    def test_allocation_default_is_email_only(self):
        assert effective_channels('allocation', None) == {
            'in_app': False, 'push': False, 'email': True, 'sms': False,
        }


class TestFilterRecipients:
    def test_no_prefs_inapp_includes_everyone(self):
        result = filter_recipients([1, 2, 3], 'chat', 'in_app', prefs={})
        assert sorted(result) == [1, 2, 3]

    def test_no_prefs_email_excludes_everyone_opt_in_channel(self):
        result = filter_recipients([1, 2, 3], 'chat', 'email', prefs={})
        assert result == []

    def test_user_opted_out_of_push_is_dropped(self):
        prefs = {2: {'in_app': None, 'push': False, 'email': None, 'sms': None}}
        result = filter_recipients([1, 2, 3], 'chat', 'push', prefs=prefs)
        assert sorted(result) == [1, 3]

    def test_user_opted_in_to_email_is_included(self):
        prefs = {2: {'in_app': None, 'push': None, 'email': True, 'sms': None}}
        result = filter_recipients([1, 2, 3], 'chat', 'email', prefs=prefs)
        assert result == [2]

    def test_mandatory_includes_everyone_on_sms_even_without_prefs(self):
        # approvals is mandatory -> SMS forced even though SMS is opt-in elsewhere
        result = filter_recipients([1, 2, 3], 'approvals', 'sms', prefs={})
        assert sorted(result) == [1, 2, 3]

    def test_mandatory_includes_user_who_tried_to_opt_out(self):
        prefs = {1: {'in_app': False, 'push': False, 'email': False, 'sms': False}}
        result = filter_recipients([1, 2], 'system', 'push', prefs=prefs)
        assert sorted(result) == [1, 2]

    def test_preserves_input_order(self):
        result = filter_recipients([3, 1, 2], 'chat', 'in_app', prefs={})
        assert result == [3, 1, 2]
