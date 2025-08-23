from datetime import datetime, timezone

from .models.company import Company
from .models.author import Author
from .models.review import Review
from .db import DBSession


def create_test_records():
    print("create test records")
    with DBSession() as dbsession:
        _company = Company(object_id='_test1', title='Test company #1', city='Нарния', address='ул. Джона Леннона, 1')
        _company.update_search_str()
        dbsession.add(_company)


        _a1 = Author(
            public_id='_testa:1', 
            name='Гарри Поттер', 
            private=False,
            created = datetime(2020, 1, 15, tzinfo=timezone.utc),
            updated = datetime.now(tz=timezone.utc).replace(microsecond=0)
        )
        dbsession.add(_a1)

        _r_a1_1 = Review(
            id='_testr:1',
            author=_a1,
            _name=None, # name will be takes from _user.name
            company=_company,
            provider='2gis',
            rating=5,
            created=datetime(2025, 2, 15, tzinfo=timezone.utc)
        )
        dbsession.add(_r_a1_1)

        print("commit")
        dbsession.commit()

