import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.v1.router import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    On startup: create all database tables (idempotent — safe to run on every
    start during development). In production, replace this with Alembic migrations.
    On shutdown: dispose the connection pool.
    """
    if settings.DATABASE_URL:
        from app.core.database import Base, _engine
        # Import all models so SQLAlchemy knows about them before create_all
        import app.models  # noqa: F401

        try:
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables verified / created.")
        except Exception as exc:
            logger.warning(
                "Could not connect to the database on startup (%s). "
                "Auth endpoints will return errors until the database is reachable.",
                exc,
            )
    else:
        logger.warning(
            "DATABASE_URL is not set — skipping table creation. "
            "Auth endpoints will return 503."
        )

    yield

    if settings.DATABASE_URL:
        from app.core.database import _engine
        await _engine.dispose()
        logger.info("Database connection pool closed.")


# Disable Swagger UI and ReDoc in production to avoid API enumeration by attackers.
_docs_url = "/docs" if settings.DEBUG else None
_redoc_url = "/redoc" if settings.DEBUG else None

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security-hardening HTTP response headers on every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if not settings.DEBUG:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
