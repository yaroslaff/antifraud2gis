import typer
import numpy as np
from sqlalchemy import select, func, case
import time
from rich import print_json

from ...db import DBSession, Session
from ...models.metric import Metric
from ...models.metricperc import MetricPerc
from ...models.company import Company
from ...models.author import Author
from ...models.review import Review
from ...aliases import resolve_alias
from ...metrics import run_metrics, save_metrics
from ...logger import logger
from ...exceptions import AFNoCompany, AFAuthorUnavailable
from ...net.author_reviews import AuthorReviewsIterator
from ...net.company_reviews import CompanyReviewsIterator

extra_app = typer.Typer(help="misc eXtra commands")

@extra_app.command(name="top-author")
def top_author(limit: int = typer.Option(5, "--limit", "-l", help="Number of top authors to show")):
    """ show most active authors """

    with DBSession() as dbsession:

        
        #top_authors_stmt = (
        #    select(
        #            Author,
        #            func.count().label("review_count")
        #        )
        #        .join(Review, Review.author_id == Author.public_id)
        #        .group_by(Author.public_id)
        #        .order_by(func.count(Review.id).desc())
        #        .limit(limit)
        #    )

        top_authors_stmt = (
            select(
                Review.author_id,
                func.count(Review.id).label("review_count")
            )
            .where(Review.author_id.isnot(None))
            .group_by(Review.author_id)
            .order_by(func.count(Review.id).desc())
            .limit(limit)
        )



        # print(top_authors_stmt)

        started = time.time()

        top_authors = dbsession.execute(top_authors_stmt).all()
        author_ids = [aid for aid, _ in top_authors]

        authors = dbsession.scalars(
            select(Author).where(Author.public_id.in_(author_ids))
        ).all()

        authors_map = {author.public_id: author for author in authors}

        for aid, count in top_authors:
            author = authors_map[aid]
            print(author.public_id, author.name, count)



        #for author, num in dbsession.execute(top_authors_stmt):
        #    print(f"{author}: {num} reviews")

        print(f"# elapsed: {time.time() - started:.2f} sec")

def fix_region_id_author(public_id: str, dbsession: Session):    
    ar = AuthorReviewsIterator(public_id=public_id, timeout=10)
    miss = 0
    hit = 0

    review_ids = list()

    for ard in ar:
        review_ids.append(ard['id'])
        region_id = ard['region_id']
        print(f"Obj: {ard['object']['id']}")
        try:
            c = Company.get(object_id=ard['object']['id'], dbsession=dbsession)
        except AFNoCompany:
            print(f"AFNoCompany {ard['object']['id']}")
            continue

        if c is None:
            print(f"No company: {ard['object']['id']}")
            continue

        if c.region_id == region_id:
            print(f"{c} already has r{region_id}")
            miss += 1
        else:
            print(f"  Set r{region_id} to {c}")
            c.region_id = region_id
            hit += 1
    
    print(f"hit: {hit} miss: {miss}...")
    return review_ids


@extra_app.command(name="fix-seen1")
def fix_seen1(
    limit: int = typer.Option(100, "--limit", "-l", help="Number of authors to process"),
    ):
    """ Fix region ID """
    
    started = time.time()
    fixed = 0

    print("Pass 1: See Authors from Company")
    # find unseens authors which we can see
    stmt = (select(Company, Review, Author).
            join(Company.reviews).
            join(Review.author).
            where(Company.seen.isnot(None), Author.seen.is_(None)).
            limit(limit))

    while True:
        iter_fixed = 0
        iter_started = time.time()
        with DBSession() as dbsession:
            res = dbsession.execute(stmt).all()
            select_time = int(time.time() - iter_started)
            print(f"SELECT took {select_time}s")
            for c,r,a in res:
                print(f"{r.created.date()} {c.object_id} {c.title} {a.public_id} {a.name} [seen:{a.seen}]")
                if a.seen is None:
                    a.seen = c.object_id
                    iter_fixed += 1
                    fixed += 1

            dbsession.commit()

        elapsed = int(time.time()-started)
        iter_elapsed = int(time.time() - iter_started)
        print(f"Fixed {iter_fixed}/{fixed} records in {elapsed}/{iter_elapsed} seconds (select: {select_time} limit: {limit })")
        if iter_fixed == 0:
            return


@extra_app.command(name="fix-seen2")
def fix_seen2(
    limit: int = typer.Option(100, "--limit", "-l", help="Number of authors to process"),
    ):
    """ Fix region ID """
    
    started = time.time()
    fixed = 0

    print("Pass 2: See Companies from Authors")
    # find unseens companies which we can see
    stmt = (select(Author, Review, Company).
            join(Author.reviews).
            join(Review.company).
            where(Company.seen.is_(None), Author.seen.isnot(None)).
            limit(limit))

    while True:

        iter_started = time.time()
        iter_fixed=0


        with DBSession() as dbsession:
            res = dbsession.execute(stmt).all()
            select_time = int(time.time() - iter_started)
            print(f"SELECT took {select_time}s")
            for a,r,c in res:
                print(f"{r.created.date()} {a.public_id} ({a.name}) {a.seen}: {c.object_id} {c.title} [seen:{c.seen}]")
                if c.seen is None:
                    c.seen = a.public_id
                    iter_fixed += 1
                    fixed +=1

            dbsession.commit()
        elapsed = int(time.time()-started)
        iter_elapsed = int(time.time() - iter_started)
        print(f"Fixed {iter_fixed}/{fixed} records in {elapsed}/{iter_elapsed} seconds (select: {select_time} limit: {limit})")

        if iter_fixed == 0:
            return



@extra_app.command(name="fix-seen-authors")
def fix_seen_authors():

    stmt = select(Author).where(Author.seen.is_(None), Author.private==False)

    with DBSession() as dbsession:
        for a in dbsession.scalars(stmt):
            print(f"seen: {a.seen} pvt: {a.private} {a.public_id} {a.name}")
            for r in a.reviews:
                print(f"  {r}")

@extra_app.command(name="x")
def x(object_id: str = typer.Argument(help="object_id")):
    with DBSession() as dbsession:
        company = Company.get(object_id=resolve_alias(object_id), dbsession=dbsession)
        if company is None:
            print("miss company", object_id)
            return
        print(company)        
        company.has_public_reviews(dbsession=dbsession)



@extra_app.command(name="fix-region-id")
def fix_region_id(
    limit: int = typer.Option(5, "--limit", "-l", help="Number of authors to process"),
    object_id: str = typer.Option(None, "--company", "-c", help="object_id"),
    sleep: int = typer.Option(5, "--sleep", "-s", help="Min time to process (sleep to get this time, rate-limiting)")
    ):
    """ Fix region ID """
    
    started = time.time()

    with DBSession() as dbsession:
        #? Company.error.is_(None)
        if object_id:
            company = Company.get(object_id=object_id, dbsession=dbsession)
        else:
            # we should skip company.error because some companies are deleted
            stmt = select(Company).where(Company.region_id == -1, Company.error.is_(None)).limit(1)
            company = dbsession.scalars(stmt).first()
        print("Fix company:", company)

        if company is None:
            return

        if company.region_id != -1:
            time.sleep(30)
            raise AssertionError(f"{company.object_id} has r:{company.region_id}")

        try:
            Company.check_company_alive(company.object_id)
        except AFNoCompany as e:
            print(e)
            company.error = str(e)
            dbsession.commit()
            return

        started = time.time()

        stmt = (
            select(Review.author_id, func.count().label("cnt"))
                .join(Author, Review.author_id == Author.public_id)
                .where(Review.object_id == company.object_id, Review.deleted == 0, Review.author_id.is_not(None), Author.private.is_(False))
                .group_by(Review.author_id)
                .order_by(func.count().desc())
                .limit(1)
            )
        
        res = dbsession.execute(stmt).first()
        if res is None:
            print("No good review for this, fix via company reviews")
            cri = CompanyReviewsIterator(object_id=company.object_id)
            for r in cri:
                company.region_id = r['region_id']
                print(f"set r{company.region_id} for {company}")
                dbsession.commit()                
                return

        public_id, cnt = res

        if public_id is None:
            if company.nreviews() == 0:
                print("Company has no reviews, ok...")
                company.region_id = -2
                dbsession.commit()
                return
            else:
                # no reviews but we have company in db??
                raise NotImplementedError

        try:
            print(f"Use author {public_id} ({cnt})")
            review_ids = fix_region_id_author(public_id=public_id, dbsession=dbsession)
            print(f"Processed {len(review_ids)} reviews: {' '.join(review_ids)}")
        except AFAuthorUnavailable as e:
            print(f"Unavailale author {public_id} {e}")
            if Author.is_private_net(public_id=public_id):
                print("Profile is private! Update in db")
                a = Author.get(public_id=public_id, dbsession=dbsession)
                a.private = True
                dbsession.commit()
                return

        dbsession.commit()

        if company.region_id == -1:
            print(f"NOT FIXED company: {company}")
            stmt = select(Review).where(Review.object_id == company.object_id, Review.author_id == public_id, Review.deleted == False)
            r = dbsession.scalar(stmt)
            print("Problem is in revew:", r)
            if r.id not in review_ids:
                print(f"DELETE review {r.id}")
                r.deleted = True
                dbsession.commit()

    elapsed = time.time() - started

    print(f"Elapsed: {int(elapsed)} seconds")

    if elapsed < sleep:
        sleeptime = sleep-elapsed
        print(f"Sleep {sleeptime:.1f}")
        time.sleep(sleeptime)



@extra_app.command(name="fix-region-id-net")
def fix_region_id_net(
    limit: int = typer.Option(5, "--limit", "-l", help="Number of authors to process"),
    object_id: str = typer.Option(None, "--company", "-c", help="object_id"),
    sleep: int = typer.Option(5, "--sleep", "-s", help="Min time to process (sleep to get this time, rate-limiting)")
    ):
    """ Fix region ID """
    
    started = time.time()

    with DBSession() as dbsession:
        #? Company.error.is_(None)
        if object_id:
            company = Company.get(object_id=object_id, dbsession=dbsession)
        else:
            # we should skip company.error because some companies are deleted
            stmt = select(Company).where(Company.region_id == -1, Company.error.is_(None)).limit(1)
            company = dbsession.scalars(stmt).first()
        print("Fix company:", company)

        if company is None:
            return

        if company.region_id != -1:
            time.sleep(30)
            raise AssertionError(f"{company.object_id} has r:{company.region_id}")


        cri = CompanyReviewsIterator(object_id=object_id)

