"""Pure-logic tests for per-day event-hour intervals on event bonuses."""
import pytest

from hr.events.presence import total_event_hours, validate_day_hours


class TestTotalEventHours:
    def test_none_or_empty_is_zero(self):
        assert total_event_hours(None) == 0
        assert total_event_hours({}) == 0

    def test_sums_whole_hour_intervals_across_days(self):
        day_hours = {
            '2026-08-28': {'start': 10, 'end': 18},  # 8h
            '2026-08-29': {'start': 9, 'end': 17},   # 8h
        }
        assert total_event_hours(day_hours) == 16

    def test_days_without_a_full_interval_contribute_zero(self):
        day_hours = {
            '2026-08-28': {'start': 10, 'end': 18},   # 8h
            '2026-08-29': {'start': None, 'end': None},
            '2026-08-30': {'start': 12},              # end missing
        }
        assert total_event_hours(day_hours) == 8


class TestValidateDayHours:
    PRESENCE = ['2026-08-28', '2026-08-29']

    def test_returns_only_days_with_a_full_valid_interval(self):
        day_hours = {
            '2026-08-28': {'start': 10, 'end': 18},
            '2026-08-29': {'start': None, 'end': None},  # empty -> dropped
        }
        assert validate_day_hours(day_hours, self.PRESENCE) == {
            '2026-08-28': {'start': 10, 'end': 18},
        }

    def test_none_day_hours_is_empty(self):
        assert validate_day_hours(None, self.PRESENCE) == {}

    def test_rejects_day_not_in_presence_days(self):
        with pytest.raises(ValueError, match='not an attended day'):
            validate_day_hours({'2026-08-30': {'start': 10, 'end': 18}}, self.PRESENCE)

    def test_rejects_end_not_after_start(self):
        with pytest.raises(ValueError, match='after'):
            validate_day_hours({'2026-08-28': {'start': 18, 'end': 10}}, self.PRESENCE)
        with pytest.raises(ValueError, match='after'):
            validate_day_hours({'2026-08-28': {'start': 10, 'end': 10}}, self.PRESENCE)

    def test_rejects_out_of_range_hours(self):
        with pytest.raises(ValueError, match='between 0 and 24'):
            validate_day_hours({'2026-08-28': {'start': -1, 'end': 8}}, self.PRESENCE)
        with pytest.raises(ValueError, match='between 0 and 24'):
            validate_day_hours({'2026-08-28': {'start': 10, 'end': 25}}, self.PRESENCE)

    def test_rejects_non_whole_hours(self):
        with pytest.raises(ValueError, match='whole hours'):
            validate_day_hours({'2026-08-28': {'start': 10.5, 'end': 18}}, self.PRESENCE)

    def test_rejects_only_one_bound_set(self):
        with pytest.raises(ValueError, match='both a start and end'):
            validate_day_hours({'2026-08-28': {'start': 10, 'end': None}}, self.PRESENCE)
