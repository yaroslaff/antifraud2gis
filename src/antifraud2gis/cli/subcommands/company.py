import typer
from rich import print_json
from rich.table import Table
from rich.console import Console
import dateutil
import pandas as pd
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_

from ...models import Company, Author
from ...db import DBSession
from ...aliases import resolve_alias
from ...net.company_reviews import CompanyReviewsIterator
from ...logger import logger
from ...exceptions import AFNoCompany
from ...settings import settings

company_app = typer.Typer(help="Company commands")

@company_app.command(name="reviews")
def сompany_reviews(oid: str,
        id_only: bool = typer.Option(False, "--id", "-i", help="Only this review"),
        table: bool = typer.Option(False, "-t", "--table", help="Show as table")):
    object_id = resolve_alias(oid)
    assert object_id is not None
    with DBSession() as dbsession:
        c = Company.get(object_id=object_id, dbsession=dbsession)

        if table:
            console = Console()

            # summary
            rev_table = Table(show_header=False, title=f"{c.object_id} {c.title} ({c.address})")
            rev_table.add_column("Created", style="bold cyan")
            rev_table.add_column("Provider", style="bold white")
            rev_table.add_column("AuthorID", style="bold white")
            rev_table.add_column("Pvt", style="bold white")
            rev_table.add_column("Author", style="bold white")
            rev_table.add_column("Rating", style="bold white")


        for r in c.reviews:
            if id_only:
                print(r.id)
                continue

            if table:
                rev_table.add_row(r.created.strftime("%Y-%m-%d"),
                                    r.provider,r.author_id,
                                    "P" if r.author and r.author.private else " ",
                                    r.author.name if r.author else r._name or "",
                                    str(r.rating))

            else:
                # not table
                if r.provider == "2gis":
                    pvt_tag = "P" if r.author.private else " "
                    print(r.created, r.provider, r.author_id, pvt_tag, r.author.name, r.rating)
                else:
                    pvt_tag = "?"
                    print(r.created, r.provider, r._name, r.rating)

        if table:
            console.print(rev_table)

# crd
@company_app.command(name="reviews-data")
def сompany_reviews_data(oid: str = typer.Argument(..., help="2GIS object_id")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=True)
        data = c.data_reviews()

    print_json(data=data)
    cdf = pd.DataFrame(data)

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

@company_app.command(name="trace")
def сompany_trace(oid: str = typer.Argument(None, help="object_id")):
    with DBSession() as dbsession:
        object_id = resolve_alias(oid)

        while object_id:
            print("obj:", object_id)
            c = Company.get(object_id=object_id, dbsession=dbsession)
            print(f"# {c.info()}")
            a = Author.get(public_id=c.seen, dbsession=dbsession)
            print(f"# {a}")
            if a is None:
                return
            print("seen:", a.seen)
            object_id = a.seen




@company_app.command(name="fetch")
def сompany_fetch(oid: str = typer.Argument(None, help="object_id"), 
                full: bool = typer.Option(False, "--full", "-f", help="Fetch full company data"),
                update: bool = typer.Option(False, "--update", "-u", help="Update companies (even companies which has updated_at)"),
                region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)")):

    object_id = resolve_alias(oid) if oid and oid.lower() != ':all' else None

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.max_review_age)


    with DBSession() as dbsession:

        if object_id:
            c = Company.get(object_id=object_id, dbsession=dbsession)
            if oid:
                print("Refresh data for existing company:", c)
                c.update_reviews(dbsession=dbsession, full=full)
                dbsession.commit()
                return

            # missing company
            else:                
                try:
                    Company.fetch(object_id=object_id, full=full, notolder=cutoff)
                    c = Company.get(object_id=object_id, dbsession=dbsession)
                    print("fetched:", c)
                except AFNoCompany as e:
                    logger.error(e)
                    c.error = str(e)                    
        else:
            # no object_id, (:all). process region
            if region_id is None:
                print("Need either object_id or region_id")
                return 1
            
            stmt = select(Company).where(Company.region_id == region_id, Company.error.is_(None))

            if not update:
                stmt = stmt.where(Company.updated_at.is_(None))

            print(stmt)

            count = dbsession.scalar(select(func.count()).select_from(stmt.subquery()))
            
            for idx,c in enumerate(dbsession.scalars(stmt)):
                print(f"fetch {idx}/{count} {c}")
                with DBSession() as dbsession2:
                    try:
                        Company.fetch(c.object_id, full=full, notolder=cutoff)
                    except AFNoCompany as e:
                        logger.error(e)
                        c = dbsession2.merge(c)
                        c.error = str(e)
                    except KeyboardInterrupt as e:
                        print("KeyboardInterrupt", e)
                        sys.exit(1)
                    
                    dbsession2.commit()
    

        print("commit")
        dbsession.commit()




@company_app.command(name="wipe")
def сompany_wipe(oid: str, full: bool = typer.Option(False, "--full", help="Wipe full company data")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        try:
            c = Company.get(object_id=object_id, dbsession=dbsession)
            if c is None:
                print("no such company:", object_id, file=sys.stderr)
                return
            print("WIPE", c)
            dbsession.delete(c)
        except AFNoCompany as e:
            logger.error(e)
        dbsession.commit()

@company_app.command(name="error")
def сompany_error(oid: str, error: str = typer.Argument(help="Error message or - to reset")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        try:
            c = Company.get(object_id=object_id, dbsession=dbsession)
            if error == '-':
                c.error = None
            else:
                c.error = error
        except AFNoCompany as e:
            logger.error(e)
        dbsession.commit()
