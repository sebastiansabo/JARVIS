"""Signed one-tap approval-action token for email decide links.

A token encodes (request_id, approver_id, action) signed with the app SECRET_KEY,
so an emailed Approve/Reject link authenticates the decision without a login. It is
per-approver, time-limited, and tamper-evident."""
from core.approvals.action_token import make_action_token, read_action_token

SECRET = 'test-secret-key-abc'


def test_roundtrip_returns_same_payload():
    tok = make_action_token(28, 1, 'approve', SECRET)
    assert read_action_token(tok, SECRET) == {'rid': 28, 'uid': 1, 'act': 'approve'}


def test_reject_action_roundtrips():
    tok = make_action_token(28, 1, 'reject', SECRET)
    assert read_action_token(tok, SECRET)['act'] == 'reject'


def test_wrong_secret_is_rejected():
    tok = make_action_token(28, 1, 'approve', SECRET)
    assert read_action_token(tok, 'a-different-secret') is None


def test_tampered_token_is_rejected():
    tok = make_action_token(28, 1, 'approve', SECRET)
    tampered = tok[:-3] + ('AAA' if tok[-3:] != 'AAA' else 'BBB')
    assert read_action_token(tampered, SECRET) is None


def test_expired_token_is_rejected():
    tok = make_action_token(28, 1, 'approve', SECRET)
    # max_age in the past forces the embedded timestamp to read as expired,
    # deterministically (no sleeping).
    assert read_action_token(tok, SECRET, max_age=-1) is None


def test_unknown_action_in_payload_is_rejected():
    # A token minted with a bogus action (same secret/salt) must not validate —
    # read guards the action enum, not just the signature.
    bogus = make_action_token(28, 1, 'delete', SECRET)
    assert read_action_token(bogus, SECRET) is None
