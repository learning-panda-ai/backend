import datetime

import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.security import verify_access_token

from app.core.config import settings  # noqa: E402  (conftest sets env vars first)

# Always use the same secret as the running settings object so tokens created
# here are verifiable by verify_access_token().
_SECRET = settings.JWT_SECRET_KEY
_ALGORITHM = settings.JWT_ALGORITHM


def _make_token(payload: dict, secret: str = _SECRET) -> str:
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def _future_exp() -> datetime.datetime:
    return datetime.datetime.utcnow() + datetime.timedelta(hours=1)


def _past_exp() -> datetime.datetime:
    return datetime.datetime.utcnow() - datetime.timedelta(seconds=1)


# ---------------------------------------------------------------------------
# Valid tokens
# ---------------------------------------------------------------------------

class TestVerifyAccessTokenValid:
    def test_valid_token_returns_payload(self):
        token = _make_token({"sub": "user42", "exp": _future_exp()})
        result = verify_access_token(token)
        assert result["sub"] == "user42"

    def test_valid_token_returns_full_payload(self):
        token = _make_token({"sub": "user42", "exp": _future_exp(), "role": "admin"})
        result = verify_access_token(token)
        assert result["role"] == "admin"

    def test_valid_token_sub_preserved(self):
        token = _make_token({"sub": "abc-123", "exp": _future_exp()})
        assert verify_access_token(token)["sub"] == "abc-123"


# ---------------------------------------------------------------------------
# Expired tokens
# ---------------------------------------------------------------------------

class TestVerifyAccessTokenExpired:
    def test_expired_token_raises_401(self):
        token = _make_token({"sub": "user42", "exp": _past_exp()})
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token(token)
        assert exc_info.value.status_code == 401

    def test_expired_token_detail_mentions_expired(self):
        token = _make_token({"sub": "user42", "exp": _past_exp()})
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token(token)
        assert "expired" in exc_info.value.detail.lower()

    def test_expired_token_has_www_authenticate_header(self):
        token = _make_token({"sub": "user42", "exp": _past_exp()})
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token(token)
        assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"


# ---------------------------------------------------------------------------
# Invalid / tampered tokens
# ---------------------------------------------------------------------------

class TestVerifyAccessTokenInvalid:
    def test_garbage_string_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token("not.a.jwt")
        assert exc_info.value.status_code == 401

    def test_wrong_signature_raises_401(self):
        token = _make_token({"sub": "user42", "exp": _future_exp()}, secret="wrong-secret")
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token(token)
        assert exc_info.value.status_code == 401

    def test_empty_string_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token("")
        assert exc_info.value.status_code == 401

    def test_token_missing_sub_raises_401(self):
        token = _make_token({"exp": _future_exp()})
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token(token)
        assert exc_info.value.status_code == 401

    def test_token_with_empty_sub_raises_401(self):
        token = _make_token({"sub": "", "exp": _future_exp()})
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token(token)
        assert exc_info.value.status_code == 401

    def test_token_with_none_sub_raises_401(self):
        token = _make_token({"sub": None, "exp": _future_exp()})
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token(token)
        assert exc_info.value.status_code == 401

    def test_invalid_token_has_www_authenticate_header(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_access_token("garbage")
        assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"
