import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

DB_USER = os.getenv("DB_USER", "app")
DB_PASS = os.getenv("DB_PASS", "app")
DB_NAME = os.getenv("DB_NAME", "appdb")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_SCHEMA = os.getenv("DB_SCHEMA", "orders")
CATALOG_SCHEMA = os.getenv("CATALOG_SCHEMA", "catalog")

# search_path: orders first, then catalog, then public
options = f"-csearch_path={DB_SCHEMA},{CATALOG_SCHEMA},public"
DATABASE_URL = (
    f"postgresql+psycopg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?options={options}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_session() -> Session:
    """
    FastAPI dependency that yields a SQLAlchemy Session.
    Ensures the service schema exists (idempotent), commits on success,
    rolls back on error, and always closes the session.
    """
    s: Session = SessionLocal()
    try:
        s.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
