"""Alembic migration entry points used by startup and reset commands."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from .database import current_database_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def run_migrations(database_url: str | None = None) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url or current_database_url())
    command.upgrade(config, "head")
