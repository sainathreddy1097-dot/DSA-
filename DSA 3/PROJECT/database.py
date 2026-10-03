"""SQLAlchemy engine and session configuration."""

from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / "data" / "contracts.db"
_database_url = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE.as_posix()}")
engine = None
SessionLocal = None


def configure_database(database_url: str | None = None) -> None:
    global engine, SessionLocal, _database_url
    if engine is not None:
        engine.dispose()
    _database_url = database_url or os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE.as_posix()}")
    if _database_url.startswith("sqlite:///"):
        database_path = Path(_database_url.removeprefix("sqlite:///"))
        if str(database_path) != ":memory:":
            database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        _database_url,
        connect_args={"check_same_thread": False} if _database_url.startswith("sqlite") else {},
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def current_database_url() -> str:
    return _database_url


configure_database(_database_url)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
