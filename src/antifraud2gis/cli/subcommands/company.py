import typer
from rich import print_json
import dateutil
import pandas as pd

from ...models import Company, Author
from ...db import DBSession
from ...aliases import resolve_alias
from ...net.company_reviews import CompanyReviewsIterator
from ...logger import logger
from ...exceptions import AFNoCompany

company_app = typer.Typer(help="Company commands")

@company_app.command(name="reviews")
def сompany_reviews(oid: str,
        id_only: bool = typer.Option(False, "--id", "-i", help="Only this review")):
    object_id = resolve_alias(oid)
    assert object_id is not None
    with DBSession() as dbsession:
        c = Company.get(object_id=object_id)
        c = dbsession.merge(c) # ZZZZZZZZZZZZZZZZZz
        for r in c.reviews:
            if id_only:
                print(r.id)
            else:
                print(r)

# crd
@company_app.command(name="reviews-data")
def сompany_reviews_data(oid: str = typer.Argument(..., help="2GIS object_id")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=True)
        data = c.data_reviews()

    print_json(data=data)
    cdf = pd.DataFrame(data)
    print(cdf)
    print("LEN:", len(cdf))


    df = pd.DataFrame()
    for author_id in cdf['author_id'].dropna().unique():
        with DBSession() as dbsession:
            # print(author_id)
            a = Author.get_or_fetch(public_id=author_id, dbsession=dbsession)
            df = pd.concat([df, pd.DataFrame(a.data_reviews())], ignore_index=True)
            print(len(df))

    print(df)
    # print("Mem:", df.memory_usage(deep=True).sum() / 1024**2)
    print(df['object_id'].value_counts().sort_values(ascending=False))


        # print(len(cdf['author_id'].dropna().unique()))
        # print(cdf['author_id'].nunique())



@company_app.command(name="reviews-net")
def сompany_reviews_net(
    oid: str,
    public_id: str = typer.Argument(None, help="Dump only this review"),
    datestr: str = typer.Option(
        None,
        "-d",
        "--date",
        help="Optional date (YYYY-MM-DD). Defaults to None.")
    ):

    """ get reviews from network and dump it (crn) """

    object_id = resolve_alias(oid)    
    cr = CompanyReviewsIterator(object_id=object_id)
    needle_date = None

    if datestr:
        needle_date = dateutil.parser.parse(datestr).date()

    for r in cr:
        if public_id and r['user']['public_id'] != public_id:
            continue
        if needle_date:
            review_date = dateutil.parser.parse(r['date_created']).date()
            if review_date != needle_date:
                continue
        print_json(data=r)



@company_app.command(name="authors")
def сompany_authors(oid: str):
    with DBSession() as dbsession:
        object_id = resolve_alias(oid)

        c = Company.get(object_id=object_id, dbsession=dbsession)
        print(f"# {c.info(dbsession=dbsession)}")
        for r in c.authors():
            print(r)

@company_app.command(name="fetch")
def сompany_fetch(oid: str, full: bool = typer.Option(False, "--full", help="Fetch full company data")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        try:
            Company.fetch(object_id=object_id, full=full)
            c = Company.get(object_id=object_id)
            print("fetched:", c)
        except AFNoCompany as e:
            logger.error(e)

@company_app.command(name="wipe")
def сompany_wipe(oid: str, full: bool = typer.Option(False, "--full", help="Wipe full company data")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        try:
            c = Company.get(object_id=object_id, dbsession=dbsession)
            print("WIPE", c)
            dbsession.delete(c)
        except AFNoCompany as e:
            logger.error(e)
        dbsession.commit()
