# alembic/env.py
from __future__ import annotations
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from app.core.config import settings
from app.db.session import Base

# Import model modules so Alembic sees table metadata during autogenerate
from app.models import hardware as hardware_model  # noqa: F401
from app.models import inventory as inventory_model  # noqa: F401
from app.models import known_items as known_items_model  # noqa: F401
from app.models import sku_alias as sku_alias_model  # noqa: F401
from app.models import ticket as ticket_model  # noqa: F401
from app.models import catalog as catalog_model  # noqa: F401
from app.models import work as work_model  # noqa: F401
from app.models import billing as billing_model  # noqa: F401

# this is the Alembic Config object, which provides access to values
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Provide target metadata for 'autogenerate' to work
target_metadata = Base.metadata

# Prefer environment configuration but fall back to the app defaults so Alembic
# works even when DB_URL/DATABASE_URL are not explicitly set.
db_url = (
    os.getenv("DB_URL")
    or os.getenv("DATABASE_URL")
    or settings.DB_URL
)

if not db_url:
    raise RuntimeError("Database URL not configured for Alembic migrations.")

config.set_main_option("sqlalchemy.url", db_url)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("DATABASE_URL (or sqlalchemy.url) not set for Alembic offline mode.")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,  # important for SQLite
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,  # important for SQLite
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
