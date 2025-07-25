from pathlib import Path
import requests
import json
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import time
import functools
from rich.pretty import Pretty
from rich import print_json
import traceback
import sys
from datetime import datetime, timezone
import gzip
# import lmdb
import tempfile
import os

from sqlalchemy import Column, String, Text, ForeignKey, Boolean, DateTime, func, select
from sqlalchemy.orm import Session, declarative_base, relationship, Mapped, mapped_column, reconstructor

from ..const import WSS_THRESHOLD, LOAD_NREVIEWS, SLEEPTIME, LMDB_MAP_SIZE
from ..settings import settings
from ..statistics import statistics
from ..session import http_session
# from .review import Review
from ..logger import logger
from ..base import Base
from ..db import DBSession, ScopedDBSession
from ..exceptions import AFAuthorPrivate
from ..net.author_reviews import AuthorReviewsIterator


THRESHOLD_NR=3
THRESHOLD_TS=1.5

user_pool = dict()

def retry(max_attempts=3, delay=1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    time.sleep(delay)
            raise RuntimeError(f"Function {func.__name__} failed after {max_attempts} attempts")
        return wrapper
    return decorator

class Author(Base):
    __tablename__ = "author"
    
    public_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # created: when created on 2gis (based on their API)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # created: when af2gis last updated it
    updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="author",
        cascade="all, delete-orphan"
        )



    @reconstructor
    def reconstructor(self):
        # print("user reconstructor", self)
        pass

    @classmethod
    def get_or_fetch(cls, public_id: str, dbsession: Session) -> "Author":        
        # Try to load from DB
        user = dbsession.get(cls, public_id)
        if user:
            return user
        
        user = cls.fetch(public_id, dbsession=dbsession)

        return user


    @classmethod
    def fetch_base(cls, public_id: str, dbsession = None) -> 'Author':
        dbsession = dbsession or scoped_db_session()

        base_url = f'https://api.auth.2gis.com/public-profile/user/{public_id}?with_friend_info=false'
        r = http_session.get(base_url)
        r.raise_for_status()

        data = r.json()

        private = data['public_user']['privacy'] == 'CLOSE'

        _user = Author(
            public_id=public_id, 
            name=data['public_user']['name'], 
            private=private,
            created = datetime.fromtimestamp(int(data['public_user']['created_at']), tz=timezone.utc),
            updated = datetime.now(tz=timezone.utc).replace(microsecond=0))
        dbsession.add(_user)
        dbsession.commit()
        return _user

    @classmethod
    def fetch(cls, public_id: str, dbsession = None) -> 'Author':
        from .company import Company
        from .review import Review

        def split_addr(addr: str): 
            if ',' in obj['address']:
                city, address = obj['address'].split(',', 1)
            else:
                city = obj['address']
                address = None
            
            city = city.strip()
            if address:
                address = address.strip()
            
            return city.replace(u'\xa0', u' '), address

        dbsession = dbsession or DBSession()

        _author = None

        # get base info for user
        _author = cls.fetch_base(public_id=public_id, dbsession=dbsession)

        if _author.private:
            # do not fetch reviews if user has private profile
            return _author

        ar = AuthorReviewsIterator(public_id=public_id)

        for review_data in ar:            
            # save company (if needed)
            obj = review_data['object']
            _company = dbsession.get(Company, obj['id'])
            if _company is None:
                city, address = split_addr(obj['address'])

                if True:
                    # normal company may have no address, e.g. 70000001083275091
                    _company = Company(object_id=obj['id'], title=obj['name'], city=city, address=address)
                    _company.update_search_str()
                    dbsession.add(_company)
                    dbsession.commit()

            # save review
            _review = Review(
                id=review_data['id'],
                author=_author,
                _name=None, # name will be takes from _user.name
                company=_company,
                provider=review_data['provider'],
                rating=review_data['rating'],
                created=datetime.fromisoformat(review_data['date_created'].replace("Z", "+00:00")).replace(microsecond=0)
            )
            dbsession.add(_review)
            dbsession.commit()
           
        statistics.total_users_loaded_network += 1
        statistics.total_users_loaded += 1
        return _author


    @classmethod
    def OLD_fetch(cls, public_id: str, dbsession = None) -> 'Author':
        from .company import Company
        from .review import Review

        def split_addr(addr: str): 
            if ',' in obj['address']:
                city, address = obj['address'].split(',', 1)
            else:
                city = obj['address']
                address = None
            
            city = city.strip()
            if address:
                address = address.strip()
            
            return city.replace(u'\xa0', u' '), address

        url = f'https://api.auth.2gis.com/public-profile/1.1/user/{public_id}/content/feed?page_size=20'

        dbsession = dbsession or scoped_db_session()

        page = 0

        _author = None

        _reviews = list()

        # get base info for user
        _author = cls.fetch_base(public_id=public_id, dbsession=dbsession)

        if _author.private:
            # do not fetch reviews if user has private profile
            return _author

        

        while True:
            logger.debug(f"Loading reviews p{page} for author {public_id} from {url}")
            time.sleep(SLEEPTIME)
            r = http_session.get(url)

            if r.status_code == 403:
                logger.debug(f"404 but profile {public_id} is private. We should not get here.") 
                # it's possible sometimes
                raise NotImplementedError

            elif r.status_code in [400, 500]:
                logger.warning(f"user {public_id} reviews error {r.status_code} url: {url}")
                break
            else:
                r.raise_for_status()
          
            data = r.json()

            for el in data['content_feed']:

                try:
                    review_data = el['review']

                    # save company (if needed)
                    obj = review_data['object']
                    _company = dbsession.get(Company, obj['id'])
                    if _company is None:
                        city, address = split_addr(obj['address'])

                        if True:
                            # normal company may have no address, e.g. 70000001083275091
                            _company = Company(object_id=obj['id'], title=obj['name'], city=city, address=address)
                            _company.update_search_str()
                            dbsession.add(_company)
                            dbsession.commit()
                        else:
                            pass
                            # no address, maybe geo object
                            # _company = Company(object_id=obj['id'], title=obj['name'], city=city, address=None, error='No address (maybe geo object)')
                            # dbsession.add(_company)
                            # dbsession.commit()
                    

                    # save review
                    _review = Review(
                        id=review_data['id'],
                        author=_author,
                        _name=None, # name will be takes from _user.name
                        company=_company,
                        provider=review_data['provider'],
                        rating=review_data['rating'],
                        created=datetime.fromisoformat(review_data['date_created'].replace("Z", "+00:00")).replace(microsecond=0)
                    )
                    dbsession.add(_review)
                    dbsession.commit()

                except KeyError:
                    continue
                _reviews.append(review_data)

            try:
                token = data['next_page_token']                
            except KeyError:
                # logger.debug("no token in response")
                break

            # logger.debug(f"token: {token}")
            

            # Next Page
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            query_params['page_token'] = token
            new_query = urlencode(query_params, doseq=True)
            url = urlunparse(parsed_url._replace(query=new_query))
            page+=1

        statistics.total_users_loaded_network += 1
        statistics.total_users_loaded += 1
        return _author


    def nreviews(self):
        from .review import Review

        with DBSession() as dbsession:
            return dbsession.query(func.count(Review.id))\
                        .filter(Review.author_id == self.public_id)\
                        .scalar() or 0

    def first_review(self):

        from .review import Review

        with DBSession() as dbsession:
            _r = (
                dbsession.query(Review)
                .filter(Review.author_id == self.public_id)
                .order_by(Review.created.asc())
                .first()
            )

            return _r.created

    def towns(self):
        self.load()
        towns = set()
        for r in self.reviews():
            # print_json(data=r)
            towns.add(r.oid)
        return towns

    @property
    def birthday_str(self):
        return self.first_review().strftime("%Y-%m-%d")

    def get_company_info(self, oid):
        self.load()
        for r in self.reviews():
            if r.oid == oid:
                print_json(data = r._data)
                if 'object' in r._data:
                    return r._data['object']


    def get_reviews(self):
        self.load()
        from .review import Review
        # reviews are sorted by date_edited desc, not by date_created, we need to re-sort
        for r in sorted(self._reviews, key=lambda r: r['created']):
            if r['oid'] in settings.skip_oids:
                continue            
            yield Review(r, user=self)

    def review_for(self, oid: str) -> 'Review':
        for r in self.reviews():
            if r.oid == oid:
                return r

    @property
    def url(self):
        return f"https://2gis.ru/af2gis/user/{self.public_id}"


    @classmethod
    def nusers(cls, dbsession: Session) -> int:
        return dbsession.execute(select(func.count()).select_from(cls)).scalar_one()


    def __repr__(self):
        tags=""
        if self.private:
            tags += "[PRIVATE]"
        return f'Author({self.name!r} {self.public_id} {self.url} {tags} {self.created.date()})'

