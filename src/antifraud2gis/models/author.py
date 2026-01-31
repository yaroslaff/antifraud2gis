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
from datetime import datetime, timezone, timedelta
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
from ..db import DBSession
from ..exceptions import AFAuthorPrivate, AFAuthorUnavailable
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
    
    seen: Mapped[str] = mapped_column(String, nullable=True)

    reviews: Mapped[list["Review"]] = relationship(
        back_populates="author",
        cascade="all, delete-orphan",
        order_by="Review.created.desc()"
        )

    # metrics: Mapped[list["AuthorMetric"]] = relationship(back_populates="author", cascade="all, delete-orphan")


    @reconstructor
    def reconstructor(self):
        # print("user reconstructor", self)
        pass

    @classmethod
    def get_or_fetch(cls, public_id: str, dbsession: Session) -> "Author":        
        # Try to load from DB
        # user = dbsession.get(cls, public_id)
        user = cls.get(public_id, dbsession=dbsession)
        if user:
            return user
        
        user = cls.fetch(public_id)
        if user:
            user = dbsession.merge(user)

        return user

    @classmethod
    def get(cls, public_id: str, dbsession: Session) -> "Author":
        # Try to load from DB
        user = dbsession.get(cls, public_id)
        return user

    @classmethod
    def is_private_net(cls, public_id: str) -> bool:
        """ True if user is private """
        base_url = f'https://api.auth.2gis.com/public-profile/user/{public_id}?with_friend_info=false'
        r = http_session.get(base_url)
        r.raise_for_status()

        data = r.json()

        return data['public_user']['privacy'] == 'CLOSE'


    @classmethod
    def fetch_base(cls, public_id: str) -> dict:
        base_url = f'https://api.auth.2gis.com/public-profile/user/{public_id}?with_friend_info=false'
        r = http_session.get(base_url)
        r.raise_for_status()

        data = r.json()
        return data


    @classmethod
    def fetch_save_base(cls, public_id: str, seen: str, dbsession) -> 'Author':

        data = cls.fetch_base(public_id=public_id)

        private = data['public_user']['privacy'] == 'CLOSE'

        _user = Author(
            public_id=public_id, 
            name=data['public_user']['name'], 
            private=private,
            seen=seen,
            created = datetime.fromtimestamp(int(data['public_user']['created_at']), tz=timezone.utc),
            updated = datetime.now(tz=timezone.utc).replace(microsecond=0))
        dbsession.add(_user)        
        dbsession.commit()
        return _user

    def update_reviews(self, dbsession: Session) -> int:
        """ fetch reviews from network and update self.reviews | NO COMMIT INSIDE"""

        from .company import Company
        from .review import Review

        reviews_added = 0

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

        # fetch reviews from network and update self.reviews
        ar = AuthorReviewsIterator(public_id=self.public_id, timeout=60)

        try:
            for review_data in ar:            
                # save company (if needed)
                obj = review_data['object']

                if obj['type'] != 'branch':
                    # we process only companies type=branch
                    # skip types: attraction adm_div
                    continue

                _company = dbsession.get(Company, obj['id'])
                if _company is None:
                    city, address = split_addr(obj['address'])

                    if True:
                        # normal company may have no address, e.g. 70000001083275091
                        _company = Company(
                            object_id=obj['id'], 
                            region_id=review_data['region_id'], 
                            title=obj['name'], 
                            city=city, 
                            address=address,
                            seen = self.public_id)
                        _company.update_search_str()
                        dbsession.add(_company)
                        dbsession.commit()

                # check if review already exists
                _review = dbsession.get(Review, review_data['id'])
                if _review is not None:
                    continue

                if not Review.exists_in_db(review_data['id'], dbsession):
                    # save review
                    _review = Review(
                        id=review_data['id'],
                        author=self,
                        _name=None, # name will be takes from _user.name
                        company=_company,
                        provider=review_data['provider'],
                        rating=review_data['rating'],
                        created=datetime.fromisoformat(review_data['date_created'].replace("Z", "+00:00")).replace(microsecond=0)
                    )
                    dbsession.add(_review)
                    reviews_added += 1
                else:
                    print("Review already in DB:", review_data['id'])
        except AFAuthorPrivate as e:
            data = Author.fetch_base(self.public_id)
            private = data['public_user']['privacy'] == 'CLOSE'
            if private:
                print("set private for", self.public_id)
                self.private = True

        return reviews_added

            # dbsession.commit()


    @classmethod
    def fetch(cls, public_id: str, seen: str) -> 'Author':

        with DBSession() as dbsession:

            _author = None

            # get base info for user
            _author = cls.fetch_save_base(public_id=public_id, seen=seen, dbsession=dbsession)

            if _author.private:
                # do not fetch reviews if user has private profile
                # print(f"Private profile {_author.public_id}, no reviews fetched")
                return _author
            
            try:
                df = _author.update_reviews(dbsession=dbsession)
            except requests.HTTPError as e:
                print(f"HTTP error fetching author {public_id}: {e}")
                raise AFAuthorUnavailable(f"HTTP error fetching author {public_id}: {e}")
            
            dbsession.commit()
            
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

    def data_reviews(self, dbsession: Session | None = None, days=None) -> list:
        from .review import Review
        data = list()
        

        days = days or settings.max_review_age
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.max_review_age)

        with dbsession or DBSession() as dbsession:
            recent_reviews = dbsession.query(Review).filter(
                Review.author_id == self.public_id,
                Review.created >= cutoff
            ).all()

            data = [r.as_dict() for r in recent_reviews]
            return data


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


    def UNUSED_get_reviews(self):
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


    def run_metrics(self) -> dict[str, float]:
        from .authormetric import AuthorMetric
        
        # for all reviews from this author, count number of reviews per each company.city
        city_counts = dict()
        total = 0
        # run for ALL reviews. maybe we should limit by days?
        for r in self.reviews:            
            if r.company.city not in city_counts:
                city_counts[r.company.city] = 0
            city_counts[r.company.city] += 1
            total += 1
        
        # calculate ratio of reviews in top city
        if total == 0:
            top_city_ratio = 0.0
        else:
            top_city_ratio = round(100 * max(city_counts.values()) / total)

        metrics = dict(
            top_city_ratio = top_city_ratio
        )
        return metrics

    def last_review(self) -> datetime | None:
        """ return datetime of last review or None """
        if not self.reviews:
            return None
        return max(r.created for r in self.reviews)

    def first_review(self) -> datetime | None:
        """ return datetime of first review or None """
        if not self.reviews:
            return None
        return min(r.created for r in self.reviews)

    def __repr__(self):
        tags=""
        if self.private:
            tags += "[PRIVATE]"
        return f'Author({self.name!r} {self.public_id} {self.url} {tags} {self.created.date()})'

