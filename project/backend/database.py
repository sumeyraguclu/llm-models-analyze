import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Yerel .env — mevcut ortam değişkenlerinin üzerine yazmaz (pytest conftest güvenli).
load_dotenv(Path(__file__).resolve().parent / ".env")


def _normalize_database_url(url: str) -> str:
    """
    Neon / Render / Railway bazen postgres:// veya postgresql:// (sürücüsüz) verir;
    SQLAlchemy + psycopg2 için postgresql+psycopg2:// gerekir. SQLite test URL'lerine dokunmaz.
    """
    u = url.strip()
    head = u.split(":", 1)[0].lower() if ":" in u else ""
    if "sqlite" in head:
        return u
    if u.startswith("postgresql+psycopg2://"):
        return u
    if u.startswith("postgres://"):
        return "postgresql+psycopg2://" + u[len("postgres://") :]
    if u.startswith("postgresql://"):
        return "postgresql+psycopg2://" + u[len("postgresql://") :]
    return u


DATABASE_URL = _normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
    )
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
