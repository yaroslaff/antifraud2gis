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
    print(f"Use author {public_id}")

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
        public_id = dbsession.scalar(stmt)

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
            review_ids = fix_region_id_author(public_id=public_id, dbsession=dbsession)
            print(f"Processed reviews: {' '.join(review_ids)}")
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
            stmt = select(Review).where(Review.object_id == company.object_id, Review.author_id == public_id)
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



