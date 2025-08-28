from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from .base import Base

from .settings import settings


_engine = None
ScopedDBSession = None
DBSession = None

class DebugSession(Session):
    def commit(self):
        import traceback
        print("=== COMMIT CALLED ===")
        traceback.print_stack(limit=5)  # покажет, кто вызвал
        super().commit()


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
        DBSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return DBSession()


def dbsession_init():
    scoped_db_session()
    db_session()


def createdb():
    print("CREATE db", settings.dburl)

    engine = create_engine(settings.dburl)
    Base.metadata.create_all(engine)
    print("Database initialized.")
    return

def check_or_create_db():
    from .models import Author, Metric

    with DBSession() as dbsession:
        try:
            # n_users = dbsession.query(User).count()
            n_users = Author.nusers(dbsession=dbsession)
            n_metrics = dbsession.query(Metric).count()

        except OperationalError as e:
            print("No db file? Create it")
            createdb()
            n_users = dbsession.query(Author).count()


dbsession_init()
