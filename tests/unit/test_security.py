import pytest

from app.core.exceptions import UnauthorizedException
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

pytestmark = pytest.mark.unit


def test_password_hash_round_trip() -> None:
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_round_trip() -> None:
    token = create_access_token("user-123")
    payload = decode_token(token, expected_type=TokenType.ACCESS)
    assert payload["sub"] == "user-123"
    assert payload["type"] == TokenType.ACCESS.value


def test_refresh_token_round_trip() -> None:
    token = create_refresh_token("user-123")
    payload = decode_token(token, expected_type=TokenType.REFRESH)
    assert payload["sub"] == "user-123"
    assert payload["type"] == TokenType.REFRESH.value


def test_decode_rejects_wrong_token_type() -> None:
    token = create_refresh_token("user-123")
    with pytest.raises(UnauthorizedException):
        decode_token(token, expected_type=TokenType.ACCESS)


def test_decode_rejects_garbage_token() -> None:
    with pytest.raises(UnauthorizedException):
        decode_token("not-a-real-token")
