import datetime
import os

import pytest

# Force-set test env vars BEFORE any app import.
# Direct assignment (not setdefault) ensures these values take priority over
# any real OS environment variables, while pydantic-settings env-var priority
# ensures they also override the values in .env on disk.
os.environ["APP_NAME"] = "TestApp"
os.environ["DEBUG"] = "true"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"
os.environ["AWS_SECRET_ACCESS_KEY"] = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["S3_BUCKET_NAME"] = "test-bucket"
os.environ["S3_KEY_PREFIX"] = "uploads"
os.environ["MAX_UPLOAD_SIZE_MB"] = "10"
os.environ["MILVUS_URI"] = "http://localhost:19530"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["GOOGLE_API_KEY"] = "test-google-api-key"
os.environ["GOOGLE_AGENT"] = "gemini-2.5-flash"

# JWT_SECRET_KEY: keep the real value from .env so security tests stay valid,
# but fall back to a safe test default if it's not set.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")

# DATABASE_URL is optional; leave unset so auth routes return 503 in unit tests
# (no real DB required). Integration tests can override this fixture.
os.environ.setdefault("DATABASE_URL", "")

from jose import jwt  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture
def valid_token():
    payload = {
        "sub": "user123",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def expired_token():
    payload = {
        "sub": "user123",
        "exp": datetime.datetime.utcnow() - datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def invalid_token():
    return "this.is.definitely.not.a.valid.jwt"
