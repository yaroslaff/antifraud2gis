from typing import Optional

import json
from loguru import logger
import time
import fnmatch
import sys
import gzip
import zlib
import traceback
import numpy as np
# import lmdb
import redis
import io

from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console

from rich import print_json
from rich.pretty import pretty_repr
from requests.exceptions import RequestException
from typing import Generator, Iterator
from random import randint

from datetime import datetime, timezone, timedelta
import dateutil

from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, func, select, or_, and_, inspect
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column, reconstructor, Session, noload

from ..settings import settings
from ..const import DATAFORMAT_VERSION, SLEEPTIME, WSS_THRESHOLD, LOAD_NREVIEWS, REVIEWS_KEY, LMDB_MAP_SIZE
from .author import Author
# from .review import Review
from ..session import http_session
from ..exceptions import AFNoCompany, AFAuthorUnavailable
from ..statistics import statistics
from ..base import Base
from ..db import scoped_db_session, DBSession
from ..utils import caller
from ..net.company_reviews import CompanyReviewsIterator
from ..logger import logger_verbose

# to avoid circular import
#class RelationDict:
#    pass

"""  Add region_id (can take from company reviews) """

class Company(Base):

    __tablename__ = "company"
    # __allow_unmapped__ = True  # for nreviews

    # relations: 'RelationDict'

    object_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str | None] = mapped_column(String, nullable=True)  # Null only for error companies, e.g. geo
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    search_str: Mapped[str] = mapped_column(String, nullable=False)

    # datetime of full load (or last update)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=None, nullable=True)

    count_2gis: Mapped[int] = mapped_column(Integer, nullable=True)
    branch_count_2gis: Mapped[int] = mapped_column(Integer, nullable=True)
    rating_2gis: Mapped[float] = mapped_column(Float, nullable=True)

    region_id: Mapped[int] = mapped_column(Integer, nullable=False)

    metrics_calculated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    reviews: Mapped[list["Review"]] = relationship(back_populates="company", cascade="all, delete-orphan",
        order_by="Review.created.desc()")

    metrics: Mapped[list["Metric"]] = relationship(back_populates="company", cascade="all, delete-orphan")

    metrics_calculated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None, nullable=True)
    metrics_signature: Mapped[str | None] = mapped_column(String, nullable=True)


    @reconstructor
    def reconstructor(self):
        self.report_path = settings.company_storage / (self.object_id + '-report.json.gz')
        self.explain_path = settings.company_storage / (self.object_id + '-explain.txt.gz')

    def update_search_str(self):
        self.search_str = f"{self.title or ''} {self.city or ''}".lower().strip()

    #def __init__(self):
    #    print("zzz company init")

    @classmethod
    def get(cls, object_id: str, dbsession: Session) -> "Company":
        # resolve alias
        # object_id = resolve_alias(object_id)
        company = dbsession.get(cls, object_id)
        return company


    @classmethod
    def get_or_fetch(cls, object_id: str, dbsession, full=True) -> "Company":        
        # Try to load from DB

        assert object_id is not None

        company = dbsession.get(cls, object_id)
        if company:
            # we have record but maybe incomplete
            if full:
                if company.updated_at:
                    return company
            else:
                return company

        cls.fetch(object_id, full=full)
        c = dbsession.get(cls, object_id)
        
        # Try to load from DB AGAIN
        # c = dbsession.get(cls, object_id)
        return c

    @classmethod
    def count(cls, dbsession: Session) -> int | None:
        return dbsession.scalar(select(func.count()).select_from(cls))


    @classmethod
    def random_company(cls, dbsession: Session) -> str | None:
        count = dbsession.scalar(select(func.count()).select_from(cls))
        if not count:
            return None
        offset = randint(0, count - 1)
        stmt = select(cls.object_id).offset(offset).limit(1)
        return dbsession.scalar(stmt)


    @classmethod
    def random_next_company(cls, dbsession: Session, city = None):
        base_query = select(cls).where(
            cls.updated_at.is_(None),
            cls.error.is_(None)
        )

        if city:
            base_query = base_query.where(cls.city == city)

        cnt_stmt = base_query.with_only_columns(func.count()).order_by(None)
        cnt = dbsession.scalar(cnt_stmt)        

        offset = randint(0, min(cnt, 10000))
        stmt = base_query.order_by(cls.object_id).offset(offset).limit(1)
        result = dbsession.scalar(stmt)
        return result

    @classmethod
    def search(cls, dbsession, query: str, limit: Optional[int] = None  ):
        words = [w.strip().lower() for w in query.split() if w.strip()]
        conditions = [cls.search_str.like(f"%{w}%") for w in words]

        stmt = select(cls).where(
            and_(*conditions),
            cls.error.is_(None)
        )
        if limit:
            stmt = stmt.limit(limit)

        return dbsession.scalars(stmt)

    def is_loaded(self) -> bool:
        # partially loaded: when record created (few (often 1) review(s) for it, no meta info)
        # fully loaded: all users loaded and metainfo

        return self.rating_2gis is not None

    def full_load(self) -> bool:
        if self.is_loaded():
            return False
        
        print("full_load: not loaded yet, loading", self)
        Company.fetch(object_id=self.object_id, full=True)
        return True

    @classmethod
    def fetch(cls, object_id: str, full=False, notolder: datetime | None = None) -> None:

        from .review import Review
        # dbsession = dbsession or DBSession()
        # print(f"FETCH {object_id} full: {full} caller: {caller()}")

        with DBSession() as dbsession:

            cr = CompanyReviewsIterator(object_id=object_id)

            progress_total = None
            current_review_idx = 1

            ext_reviews = list()

            # fetch statistics
            stats_reviews = 0
            stats_2gis = 0
            stats_private = 0
            stats_public_2gis = 0 

            meta = None

            with Progress(
                SpinnerColumn(),
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.0f}%",
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                TextColumn("[green]{task.description}")
            ) as progress:
                task = progress.add_task("[cyan]Loading users...", total=None)            

                for r in cr:
                    if meta is None:
                        meta = cr.meta
                        progress_total = meta['total_count']
                        progress.update(task, total=progress_total)

                    public_id = r['user']['public_id']

                    if notolder is not None:
                        review_date = dateutil.parser.parse(r['date_created'])
                        if review_date <= notolder:
                            print("skipping review date", review_date, "older than", notolder)
                            break
                        else:
                            print("processing review date", review_date, "newer than", notolder)

                    stats_reviews += 1
                    if r['provider'] == '2gis':
                        stats_2gis += 1

                    current_review_idx += 1 
                    progress.update(task, advance=1, description=f"[white]{object_id} [green]User {r['user']['public_id']}: {r['user']['name']}")

                    if r['provider'] == '2gis' and public_id is not None and public_id != '':
                        # public_id '' on https://2gis.ru/novosibirsk/firm/70000001099934045/

                        try:
                            #u = Author.get_or_fetch(public_id=public_id, dbsession=dbsession)
                            with DBSession() as author_dbsession:
                                u = Author.get(public_id=public_id, dbsession=author_dbsession)
                                if u is None:
                                    u = Author.fetch(public_id=public_id)
                                    u = author_dbsession.merge(u)
                                    if u.private:
                                        print(f"private profile: {public_id}, no reviews fetched in Author.fetch")
                                else:
                                    print(f"existing author: {public_id} pvt: {u.private} (update)")
                                    if not u.private:
                                        u.update_reviews(dbsession=author_dbsession)
                                
                                if u.private:
                                    # save review anyway
                                    if not Review.exists_in_db(r['id'], author_dbsession):
                                        print("save private review anyway")
                                        _review = Review(
                                            id=r['id'],
                                            author=u,
                                            _name=None, # name will be takes from _user.name
                                            object_id=object_id,
                                            provider=r['provider'],
                                            rating=r['rating'],
                                            created=datetime.fromisoformat(r['date_created'].replace("Z", "+00:00")).replace(microsecond=0)
                                        )
                                        author_dbsession.add(_review)
                                    else:
                                        print("Private review already in DB:", r['id'])


                                author_dbsession.commit()
                        
                        except AFAuthorUnavailable as e:
                            logger.error(f"Author {public_id} unavailable: {e}")
                            continue

                        u = dbsession.merge(u)

                        if u.private:
                            stats_private += 1
                        else:
                            stats_public_2gis += 1

                        if not full:
                            # maybe we can skip here?
                            company = dbsession.get(cls, object_id)
                            if company:
                                print(f"Short-loaded {object_id}")
                                return company
                    else:
                        ext_reviews.append(r)

            if cr.pages_loaded == 0:
                cls.check_company_alive(object_id=object_id)

            # loaded all pages
            company = dbsession.get(cls, object_id)
            if company is None:           
                raise AFNoCompany(f"Total: {stats_reviews}, pub 2gis profiles: {stats_public_2gis} private profiles: {stats_private}")

            if ext_reviews:
                saved_ext_reviews = 0
                for _r in ext_reviews:

                    if not Review.exists(_r['id'], dbsession=dbsession):
                        _review = Review(
                            id=_r['id'],
                            author=None,
                            company=company,
                            _name = _r['user']['name'],
                            provider=_r['provider'],
                            rating=_r['rating'],
                            created = datetime.fromisoformat(_r['date_created'])
                        )
                        dbsession.add(_review)
                        saved_ext_reviews += 1

                print(f"Saved {saved_ext_reviews}/{len(ext_reviews)} external review(s)")

                # dbsession.commit()

            # if company.rating_2gis is None:
            company.count_2gis = cr.meta['total_count']
            company.branch_count_2gis = cr.meta['branch_reviews_count']
            company.rating_2gis = cr.meta['branch_rating']
            company.updated_at = datetime.now(tz=timezone.utc).replace(microsecond=0)

            dbsession.add(company)
            dbsession.commit()


            logger.info(f"Company {object_id}: loaded from network {company.nreviews()} reviews")
            # why we were called?
            # print("----------")
            # print("".join(traceback.format_stack(limit=10)))         

            statistics.total_companies_loaded+=1
            statistics.total_companies_loaded_network+=1


    @classmethod
    def check_company_alive(self, object_id: str):
        start_town = 'moscow'
        r = http_session.head(f'https://2gis.ru/{start_town}/firm/{object_id}', allow_redirects=True)
        if False and r.history:
            print("Redirected")
            print("Final URL:", r.url)
            print("Redirect chain:")
            for resp in r.history:
                print(resp.status_code, "->", resp.headers.get("Location"))
        
        if r.status_code == 410:
            raise AFNoCompany(f'Company deleted: 2gis returned 410 for {r.url}')


    def count_rate(self):
        raise NotImplementedError

    def authors(self):
        for r in self.reviews:            
            yield r.author


    def info(self):
        return f'{self} updated_at: {self.updated_at} reviews: {self.nreviews()}'

    def __repr__(self):

        if self.error:
            return f'Company({self.object_id} {self.title!r} ERR: {self.error!r})'
           
        tags = " "

        return f'Company({self.object_id} {self.title} ({self.rating_2gis}) r{self.region_id} addr: {self.city}, {self.address} {tags})'

    def get_title(self):
        return self.title
        # return self.title or self.object_id

    def nreviews(self, provider = None):
        from .review import Review

        with DBSession() as dbsession:
            if provider is None:
                return dbsession.query(func.count(Review.id))\
                            .filter(Review.object_id == self.object_id)\
                            .scalar() or 0

    def data_reviews(self, provider = None, dbsession = None, days = None):
        from .review import Review

        # dbsession = dbsession or DBSession()

        days = days or settings.max_review_age


        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with dbsession or DBSession() as dbsession:
            recent_reviews = dbsession.query(Review).filter(
                Review.object_id == self.object_id,
                Review.created >= cutoff
            ).all()

            data = [r.as_dict() for r in recent_reviews]
            return data


    def wipe_metrics(self, dbsession: Session):
        for m in self.metrics:
            print("delete metric:", m)
            dbsession.delete(m)
        self.metrics_signature = None
        self.metrics_calculated = None


    def culture(self):

        whitelisted = [
            '70000001063840471' # Дом книги, СПб
        ]

        if self.object_id in whitelisted:
            return True

        culture_titles = ['храм', 'музей', 'парк']
        title = self.get_title().lower()
        return any(sub in title for sub in culture_titles)

    def report_reliable(self, report: dict):
        if 'detections' in report['score']:
            for detection in report['score']['detections']:
                if detection.startswith('risk_users') and self.culture():
                    return False
                
        return True

    def get_metric(self, name: str) -> Optional["Metric"]:
        return next((m for m in self.metrics if m.name == name), None)


    def newest_review_db(self, dbsession: Session) -> Optional[datetime]:
        from .review import Review

        stmt = select(func.max(Review.created)).where(Review.object_id == self.object_id)
        dt: datetime | None = dbsession.scalar(stmt)
        if dt:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    
    def newest_review_net(self) -> Optional[datetime]:
        cr = CompanyReviewsIterator(object_id=self.object_id)
        newest_date = None

        for r in cr:
            review_date = dateutil.parser.parse(r['date_created'])
            if newest_date is None or review_date > newest_date:
                newest_date = review_date

        return newest_date

    def update_reviews(self, dbsession: Session, full: bool = False) -> None:
        """ load new reviews from network """
        print(f"Update reviews for company {self.object_id}")
        if full:
            newest = None
        else:
            newest = self.newest_review_db(dbsession=dbsession)
            print("NEWEST:",newest, "tz:", newest.tzinfo)

        Company.fetch(object_id=self.object_id, full=True, notolder=newest)
