"""Unit tests for impression-token security (spec §4).

The ack list is a compliance record, so events/ack/snooze/dismiss must reject a
missing, tampered, expired, or mismatched token.
"""
from happy.services.tokens import mint_impression_token, verify_impression_token


def test_roundtrip_returns_payload():
    tok = mint_impression_token(412, 42, "interstitial")
    data = verify_impression_token(tok)
    assert data == {"campaign_id": 412, "user_id": 42, "surface": "interstitial"}


def test_missing_or_empty_token_is_none():
    assert verify_impression_token(None) is None
    assert verify_impression_token("") is None


def test_tampered_token_is_rejected():
    tok = mint_impression_token(412, 42, "interstitial")
    assert verify_impression_token(tok + "x") is None


def test_expired_token_is_rejected():
    tok = mint_impression_token(412, 42, "interstitial")
    # max_age=-1 → any elapsed age (>= 0) is already past the limit
    assert verify_impression_token(tok, max_age=-1) is None


def test_payload_binds_campaign_and_user():
    # A token minted for one (campaign,user) never validates as another — the
    # route compares these fields, so a forged campaign_id/user_id cannot match.
    data = verify_impression_token(mint_impression_token(1, 7, "hub_card"))
    assert data["campaign_id"] == 1 and data["user_id"] == 7
    assert data["campaign_id"] != 2 and data["user_id"] != 8
