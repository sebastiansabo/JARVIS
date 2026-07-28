import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import tasks.foi_parcurs_sessions as job


def test_notifies_pending_and_marks_then_archives():
    repo = MagicMock()
    repo.get_sessions_pending_late_notify.return_value = [
        {'id': 11, 'advisor_name': 'Ana Pop', 'client_name': 'Ion Ilie',
         'vin': 'WVW1', 'departure_datetime': datetime(2026, 7, 28, 9, 30, tzinfo=timezone.utc)},
    ]
    repo.get_advisor_user_id.return_value = 42
    repo.archive_missed_sessions.return_value = 3

    with patch.object(job, 'FoiParcursRepository', return_value=repo), \
         patch.object(job, 'notify_with_push') as push:
        job.run_session_lifecycle()

    push.assert_called_once()
    args, kwargs = push.call_args
    assert args[0] == [42]
    assert args[1] == 'Sesiune ratată la start'
    assert kwargs['link'] == '/sales/test-drive/11'
    assert kwargs['push_data'] == {'link': '/sales/test-drive/11'}
    repo.mark_late_notified.assert_called_once_with(11)
    repo.archive_missed_sessions.assert_called_once()


def test_skips_push_when_advisor_unresolved_but_still_marks():
    repo = MagicMock()
    repo.get_sessions_pending_late_notify.return_value = [
        {'id': 12, 'advisor_name': 'Ghost', 'client_name': 'X', 'vin': 'V',
         'departure_datetime': datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)},
    ]
    repo.get_advisor_user_id.return_value = None
    repo.archive_missed_sessions.return_value = 0

    with patch.object(job, 'FoiParcursRepository', return_value=repo), \
         patch.object(job, 'notify_with_push') as push:
        job.run_session_lifecycle()

    push.assert_not_called()
    repo.mark_late_notified.assert_called_once_with(12)
