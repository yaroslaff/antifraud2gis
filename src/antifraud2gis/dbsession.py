from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session

from .settings import settings


_engine = None
ScopedDBSession = None
DBSession = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.dburl, future=True, echo=False)
    return _engine

def scoped_db_session() -> Session:
    global ScopedDBSession
    if ScopedDBSession is None:
        engine = get_engine()
        ScopedDBSession = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
    return ScopedDBSession()

def db_session() -> Session:
    global DBSession
    if DBSession is None:
        engine = get_engine()
        DBSession = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
    return DBSession()


def dbsession_init():
    print("DBSESSION INIT")
    scoped_db_session()
    db_session()

dbsession_init()
