import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from alembic import context

# ── Make sure 'app' package is importable ─────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── Load .env so DATABASE_URL is available ────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from environment — keeps secrets out of alembic.ini.
# asyncpg is async-only; Alembic's sync runner needs a psycopg2 URL.
database_url = os.environ["DATABASE_URL"].replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)
config.set_main_option("sqlalchemy.url", database_url)

# ── Import all models so autogenerate sees them ───────────────────────────────
from app.core.database import Base  # noqa: E402
import app.models  # noqa: F401  — registers User, Account, OtpToken, etc.

target_metadata = Base.metadata

# Tables managed by other tools (e.g. Prisma / NextAuth) that Alembic should
# not touch during autogenerate.
_UNMANAGED_TABLES = {
    "User", "Account", "Session", "OtpToken", "_prisma_migrations",
}


def include_object(object, name, type_, reflected, compare_to):
    """Skip tables not owned by this Alembic setup."""
    if type_ == "table" and name in _UNMANAGED_TABLES:
        return False
    return True


# ── Offline mode ──────────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
