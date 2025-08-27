from datetime import datetime, timezone, timedelta

from random import randint

from .models.company import Company
from .models.author import Author
from .models.review import Review
from .db import DBSession


def rnd_review_id() -> str:
    return f'_testr:{randint(1, 100000)}'

def create_test_records():
    print("create test records")
    with DBSession() as dbsession:

        # check if we already have something

        test_c1 = Company.get('_test1', dbsession)
        test_a1 = Author.get('testa:harry', dbsession)

        if test_c1:
            print(f"Test record is already in db: {test_c1}" )
            print(f"Run: af2dev rmtest")
            return

        if test_a1:
            print(f"Test record is already in db: {test_a1}" )
            print(f"Run: af2dev rmtest")
            return




        _company1 = Company(
            object_id='_test1', 
            title='Под яблоком Ньютона', 
            city='Нарния', 
            address='ул. Джона Леннона, 1',
            updated_at = datetime.now(tz=timezone.utc).replace(microsecond=0)
            )
        _company1.update_search_str()
        dbsession.add(_company1)


        _company2 = Company(
            object_id='_test2', 
            title='Кластер', 
            city='Нарния', 
            address='ул. Кобейна, 1',
            updated_at = datetime.now(tz=timezone.utc).replace(microsecond=0)
            )
        _company2.update_search_str()
        dbsession.add(_company2)

        _company3 = Company(
            object_id='_test3', 
            title='Джаз-клуб Труба', 
            city='Нарния', 
            address='ул. Кобейна, 1',
            updated_at = datetime.now(tz=timezone.utc).replace(microsecond=0)
            )
        _company3.update_search_str()
        dbsession.add(_company3)


        _a1 = Author(
            public_id='_testa:harry', 
            name='Гарри Поттер', 
            private=False,
            created = datetime.now(tz=timezone.utc).replace(microsecond=0) - timedelta(days=100),
            updated = datetime.now(tz=timezone.utc).replace(microsecond=0)
        )
        dbsession.add(_a1)

        _a2 = Author(
            public_id='_testa:hermiona', 
            name='Гермиона Молочная', 
            private=False,
            created = datetime.now(tz=timezone.utc).replace(microsecond=0) - timedelta(days=100),
            updated = datetime.now(tz=timezone.utc).replace(microsecond=0)
        )
        dbsession.add(_a2)



        _r_a1_1 = Review(
            id=rnd_review_id(),
            author=_a1,
            _name=None, # name will be takes from _user.name
            company=_company1,
            provider='2gis',
            rating=5,
            created=datetime.now(tz=timezone.utc).replace(microsecond=0) - timedelta(days=100)
        )
        dbsession.add(_r_a1_1)

        _r_a1_2 = Review(
            id=rnd_review_id(),
            author=_a1,
            _name=None, # name will be takes from _user.name
            company=_company2,
            provider='2gis',
            rating=4,
            created=datetime.now(tz=timezone.utc).replace(microsecond=0) - timedelta(days=100)
        )
        dbsession.add(_r_a1_2)

        _r_a1_3 = Review(
            id=rnd_review_id(),
            author=_a1,
            _name=None, # name will be takes from _user.name
            company=_company3,
            provider='2gis',
            rating=4,
            created=datetime.now(tz=timezone.utc).replace(microsecond=0) - timedelta(days=100)
        )
        dbsession.add(_r_a1_3)

        _r_a2_1 = Review(
            id=rnd_review_id(),
            author=_a2,
            _name=None, # name will be takes from _user.name
            company=_company1,
            provider='2gis',
            rating=4,
            created=datetime.now(tz=timezone.utc).replace(microsecond=0) - timedelta(days=100)
        )
        dbsession.add(_r_a2_1)

        _r_a2_2 = Review(
            id=rnd_review_id(),
            author=_a2,
            _name=None, # name will be takes from _user.name
            company=_company2,
            provider='2gis',
            rating=3,
            created=datetime.now(tz=timezone.utc).replace(microsecond=0) - timedelta(days=100)
        )
        dbsession.add(_r_a2_2)




        print("commit")
        dbsession.commit()

def wipe_test_records():
    print("wipe test records")

    test_companies = ['_test1', '_test2', '_test3']
    test_authors = ['_testa:harry', '_testa:hermiona']

    with DBSession() as dbsession:

        for c in test_companies:
            _company = Company.get(c, dbsession)
            if _company:
                print("delete company:", _company)
                dbsession.delete(_company)


        for a in test_authors:
            _author = Author.get(a, dbsession)
            if _author:
                print("delete author:", _author)
                dbsession.delete(_author)

        dbsession.commit()
