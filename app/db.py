from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _normalise_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


settings = get_settings()
database_url = _normalise_database_url(settings.database_url)

if database_url.startswith("sqlite"):
    sqlite_path = database_url.replace("sqlite:///", "", 1)
    if sqlite_path and sqlite_path != ":memory:":
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_member_application_columns()


def _ensure_member_application_columns() -> None:
    expected_columns = {
        "applicant_mode": "VARCHAR(16) DEFAULT 'self'",
        "applicant_last_name": "VARCHAR(128)",
        "applicant_first_name": "VARCHAR(128)",
        "applicant_middle_name": "VARCHAR(128)",
        "member_last_name": "VARCHAR(128)",
        "member_first_name": "VARCHAR(128)",
        "member_middle_name": "VARCHAR(128)",
        "region": "VARCHAR(128)",
        "phone_home": "VARCHAR(64)",
        "phone_mobile": "VARCHAR(64)",
        "street": "VARCHAR(255)",
        "house": "VARCHAR(64)",
        "apartment": "VARCHAR(64)",
        "workplace": "VARCHAR(255)",
    }

    inspector = inspect(engine)
    try:
        existing = {column["name"] for column in inspector.get_columns("member_applications")}
    except Exception:
        return

    missing = {name: ddl for name, ddl in expected_columns.items() if name not in existing}
    if not missing:
        return

    with engine.begin() as connection:
        for name, ddl in missing.items():
            connection.execute(text(f"ALTER TABLE member_applications ADD COLUMN {name} {ddl}"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
