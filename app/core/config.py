from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str
    DEBUG: bool = False
    CORS_ORIGINS: str

    # ── JWT ──────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Database ─────────────────────────────────────────────────────────────
    # postgresql+asyncpg://user:pass@host/dbname
    DATABASE_URL: str

    # ── AWS ──────────────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    S3_BUCKET_NAME: str
    S3_KEY_PREFIX: str
    MAX_UPLOAD_SIZE_MB: int

    # AWS SES — sender address must be verified in SES
    SES_FROM_EMAIL: str
    SES_FROM_NAME: str = "Learning Panda"

    # ── Google OAuth ──────────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    # Full callback URL that Google redirects to after consent
    GOOGLE_REDIRECT_URI: str

    # ── Frontend ──────────────────────────────────────────────────────────────
    # After OAuth / magic-link the backend redirects here
    FRONTEND_URL: str

    # ── Cookie security ───────────────────────────────────────────────────────
    # Set COOKIE_SECURE=False only for local dev (HTTP). Must be True in production.
    COOKIE_SECURE: bool

    # ── Cloudflare Turnstile ──────────────────────────────────────────────────
    TURNSTILE_SECRET_KEY: str

    # ── OTP ───────────────────────────────────────────────────────────────────
    OTP_EXPIRY_MINUTES: int = 10
    # Max OTP send requests per email per window
    OTP_RATE_LIMIT_COUNT: int = 3
    OTP_RATE_LIMIT_WINDOW_MINUTES: int = 15

    # ── Milvus ───────────────────────────────────────────────────────────────
    MILVUS_URI: str

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str

    # ── Gemini ────────────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str
    GOOGLE_AGENT: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return settings
