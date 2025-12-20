import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_USER = os.getenv("DB_USER", "app")
DB_PASS = os.getenv("DB_PASS", "app")
DB_NAME = os.getenv("DB_NAME", "appdb")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_SCHEMA = os.getenv("DB_SCHEMA", "catalog")

# Use psycopg3; set search_path so unqualified tables use our schema
options = f"-csearch_path={DB_SCHEMA},public"
DATABASE_URL = (
    f"postgresql+psycopg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?options={options}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db():
    """
    Ensure the schema exists, then create tables (idempotent).
    Called once at application startup.
    """
    with engine.begin() as conn:
        # Quote the schema to avoid edge cases with names
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"'))
    # Import here to avoid circulars
    from .models import Base  # noqa
    Base.metadata.create_all(bind=engine)

def get_session():
    """
    FastAPI dependency: yields a DB session, commits on success, rolls back on error.
    """
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
