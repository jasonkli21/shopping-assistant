from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shopping.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """Yield one short-lived synchronous session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
