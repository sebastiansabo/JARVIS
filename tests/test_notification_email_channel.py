"""Tests for the email notification channel (generic template, opt-in)."""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

import database  # noqa: E402, F401

from unittest.mock import patch
import core.notifications.notify as notify_mod


class TestRenderEmail:
    def test_absolutizes_relative_link_and_escapes_html(self):
        html = notify_mod._render_email_html('<b>Salut</b>', 'rand1\nrand2', '/app/x')
        assert 'https://jarvis.autoworld.ro/app/x' in html
        assert '&lt;b&gt;Salut&lt;/b&gt;' in html   # title escaped
        assert 'rand1<br>rand2' in html             # newline -> <br>

    def test_absolute_link_left_as_is_and_no_button_without_link(self):
        assert 'http://x.com/y' in notify_mod._render_email_html('t', 'm', 'http://x.com/y')
        assert 'Deschide' not in notify_mod._render_email_html('t', 'm', None)


class TestDeliverEmail:
    def test_sends_only_to_gated_recipient_with_email(self):
        with patch('core.notifications.notify._gate', return_value=[2]), \
             patch('core.notifications.repositories.UserNotificationPreferenceRepository') as MockRepo, \
             patch('core.services.notification_service.send_email') as mock_send:
            MockRepo.return_value.get_contacts.return_value = {2: {'email': 'u2@x.com', 'phone': None}}
            notify_mod._deliver_email([1, 2, 3], 'Titlu', 'Mesaj', '/app/x', 'chat')
        mock_send.assert_called_once()
        assert mock_send.call_args.args[0] == 'u2@x.com'   # to_email
        assert mock_send.call_args.args[1] == 'Titlu'      # subject

    def test_no_gated_recipients_sends_nothing(self):
        with patch('core.notifications.notify._gate', return_value=[]), \
             patch('core.services.notification_service.send_email') as mock_send:
            notify_mod._deliver_email([1, 2], 'T', 'M', None, 'chat')
        mock_send.assert_not_called()

    def test_skips_recipient_without_email(self):
        with patch('core.notifications.notify._gate', return_value=[2]), \
             patch('core.notifications.repositories.UserNotificationPreferenceRepository') as MockRepo, \
             patch('core.services.notification_service.send_email') as mock_send:
            MockRepo.return_value.get_contacts.return_value = {2: {'email': None, 'phone': None}}
            notify_mod._deliver_email([2], 'T', 'M', None, 'chat')
        mock_send.assert_not_called()


class TestWiring:
    def test_notify_users_triggers_email_delivery(self):
        with patch('core.notifications.notify._deliver_email') as mock_email, \
             patch('core.notifications.notify._gate', return_value=[1]), \
             patch('core.notifications.push_service.send_push_to_users'), \
             patch.object(notify_mod._repo, 'create_bulk', return_value=[]):
            notify_mod.notify_users([1, 2], 'T', category='chat')
        mock_email.assert_called_once()
        assert list(mock_email.call_args.args[0]) == [1, 2]
