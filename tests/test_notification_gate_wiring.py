"""Integration tests for the notification delivery gates.

Verifies notify.py applies the in-app preference gate to the in-app insert while
still handing the full recipient list to push (push runs its own gate), and that
send_push_to_users applies the push gate / mandatory bypass.
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

import database  # noqa: E402, F401  (init before core.* to avoid circular import)

from unittest.mock import patch
import core.notifications.notify as notify_mod
import core.notifications.push_service as push_mod


class TestInAppGate:
    def test_in_app_filtered_but_push_gets_everyone(self):
        with patch('core.notifications.repositories.UserNotificationPreferenceRepository') as MockRepo, \
             patch('core.notifications.push_service.send_push_to_users') as mock_push, \
             patch.object(notify_mod._repo, 'create_bulk', return_value=[]) as mock_create:
            # user 2 has opted out of in-app for 'chat'
            MockRepo.return_value.preference_filter.return_value = [1, 3]
            notify_mod.notify_users([1, 2, 3], 'Hello', category='chat')

        # in-app insert only for gate-approved users
        assert mock_create.call_args.kwargs['user_ids'] == [1, 3]
        # push still offered all three; its own gate decides push delivery
        mock_push.assert_called_once()
        assert list(mock_push.call_args.args[0]) == [1, 2, 3]

    def test_nobody_approved_skips_insert_but_still_pushes(self):
        with patch('core.notifications.repositories.UserNotificationPreferenceRepository') as MockRepo, \
             patch('core.notifications.push_service.send_push_to_users') as mock_push, \
             patch.object(notify_mod._repo, 'create_bulk') as mock_create:
            MockRepo.return_value.preference_filter.return_value = []
            notify_mod.notify_users([1, 2], 'Hello', category='chat')

        mock_create.assert_not_called()
        mock_push.assert_called_once()
        assert list(mock_push.call_args.args[0]) == [1, 2]

    def test_single_notify_user_respects_in_app_gate(self):
        with patch('core.notifications.repositories.UserNotificationPreferenceRepository') as MockRepo, \
             patch('core.notifications.push_service.send_push_to_users') as mock_push, \
             patch.object(notify_mod._repo, 'create') as mock_create:
            MockRepo.return_value.preference_filter.return_value = []  # opted out of in-app
            notify_mod.notify_user(7, 'Hello', category='chat')

        mock_create.assert_not_called()
        # push still attempted for the user
        mock_push.assert_called_once()
        assert list(mock_push.call_args.args[0]) == [7]


class TestPushGate:
    def test_mandatory_bypasses_global_killswitch(self):
        # Kill-switch ON, but 'system' is mandatory -> admin pipeline skipped,
        # reaches firebase init (which is unavailable in tests -> returns there).
        with patch.object(push_mod, '_cache') as mock_cache, \
             patch.object(push_mod, '_init_firebase', return_value=False) as mock_fb:
            mock_cache.get_settings.return_value = {'push_global_enabled': 'false'}
            mock_cache.get_category.return_value = {'is_active': True, 'priority': 'critical'}
            push_mod.send_push_to_users([1], 'T', 'B', category='system')
        mock_fb.assert_called_once()

    def test_non_mandatory_respects_global_killswitch(self):
        with patch.object(push_mod, '_cache') as mock_cache, \
             patch.object(push_mod, '_init_firebase', return_value=False) as mock_fb:
            mock_cache.get_settings.return_value = {'push_global_enabled': 'false'}
            mock_cache.get_category.return_value = {'is_active': True}
            push_mod.send_push_to_users([1], 'T', 'B', category='chat')
        mock_fb.assert_not_called()

    def test_push_gate_drops_opted_out_users(self):
        with patch.object(push_mod, '_cache') as mock_cache, \
             patch.object(push_mod, '_is_quiet_hours', return_value=False), \
             patch.object(push_mod, '_init_firebase', return_value=False) as mock_fb, \
             patch('core.notifications.repositories.UserNotificationPreferenceRepository') as MockRepo:
            mock_cache.get_settings.return_value = {'push_global_enabled': 'true'}
            mock_cache.get_category.return_value = {'is_active': True}
            MockRepo.return_value.preference_filter.return_value = []  # all opted out of push
            push_mod.send_push_to_users([1, 2], 'T', 'B', category='chat')
        MockRepo.return_value.preference_filter.assert_called_once()
        mock_fb.assert_not_called()  # nobody left -> returns before firebase

    def test_admin_bypass_skips_gate_entirely(self):
        with patch.object(push_mod, '_cache') as mock_cache, \
             patch.object(push_mod, '_init_firebase', return_value=False) as mock_fb, \
             patch('core.notifications.repositories.UserNotificationPreferenceRepository') as MockRepo:
            mock_cache.get_settings.return_value = {'push_global_enabled': 'false'}
            mock_cache.get_category.return_value = {'is_active': False}
            push_mod.send_push_to_users([1], 'T', 'B', category='chat', bypass_rules=True)
        MockRepo.return_value.preference_filter.assert_not_called()
        mock_fb.assert_called_once()  # bypass reaches firebase despite kill-switch
