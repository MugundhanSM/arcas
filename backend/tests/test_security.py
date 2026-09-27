import pytest

from app.core import security

pytestmark = pytest.mark.unit


def test_password_hash_round_trip():
    hashed = security.hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert security.verify_password("s3cret-pass", hashed) is True
    assert security.verify_password("wrong-pass", hashed) is False


def test_jwt_round_trip_returns_subject():
    token = security.create_access_token("alice")
    payload = security.decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "alice"


def test_tampered_jwt_is_rejected():
    token = security.create_access_token("alice")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    assert security.decode_access_token(tampered) is None


def test_expired_jwt_is_rejected():
    token = security.create_access_token("bob", expires_minutes=-1)
    # Token already expired (exp in the past).
    assert security.decode_access_token(token) is None


def test_empty_token_is_rejected():
    assert security.decode_access_token("") is None
    assert security.decode_access_token("not-a-jwt") is None
