from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .settings import settings


_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.dburl, future=True, echo=False)
    return _engine

def get_db_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionLocal()

