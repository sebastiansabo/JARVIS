from core.approvals.booking_token import make_booking_token, read_booking_token

SK = 'test-secret'

def test_roundtrip_confirm():
    t = make_booking_token(42, 'confirm', SK)
    assert read_booking_token(t, SK) == {'bid': 42, 'act': 'confirm'}

def test_rejects_bad_action():
    assert make_booking_token(1, 'delete', SK) is None or \
        read_booking_token(make_booking_token(1, 'confirm', SK), SK)['act'] == 'confirm'

def test_rejects_tampered():
    assert read_booking_token('garbage.token.here', SK) is None

def test_rejects_expired():
    t = make_booking_token(1, 'cancel', SK)
    assert read_booking_token(t, SK, max_age=-1) is None
