from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shopping.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """Yield one short-lived synchronous session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
