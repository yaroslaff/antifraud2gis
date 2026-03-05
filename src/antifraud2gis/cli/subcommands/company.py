import typer
from rich import print_json
from rich.table import Table
from rich.console import Console
import dateutil
import pandas as pd
import sys
from datetime import datetime, timedelta, timezone
import evalidate
from enum import Enum
import json

from sqlalchemy import select, func, and_

from ...models import Company, Author
from ...metrics.neigh import Neighbors
from ...db import DBSession, count, dump_stmt
from ...aliases import resolve_alias
from ...net.company_reviews import CompanyReviewsIterator
from ...logger import logger
from ...exceptions import AFNoCompany
from ...settings import settings

class SeenLoop(Exception):
    pass


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
    sleep: int = typer.Option(None, "-s", help="Sleep N seconds after each page"),
    datestr: str = typer.Option(
        None,
        "-d",
        "--date",
        help="Optional date (YYYY-MM-DD). Defaults to None.")
    ):

    """ get reviews from network and dump it (crn) """

    object_id = resolve_alias(oid)    
    cr = CompanyReviewsIterator(object_id=object_id, sleep=sleep)
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

def trace_company(object_id: str):
    seen_set = set()

    with DBSession() as dbsession:
        while object_id:
            print("obj:", object_id)
            c = Company.get(object_id=object_id, dbsession=dbsession)

            if c is None:
                print(f"### NULL c {object_id}")
                raise SeenLoop

            print(f"# {c.info()}")
            if c.seen in seen_set:
                print(f"### LOOP: c {c.seen} already seen!")
                raise SeenLoop
            
            seen_set.add(c.seen)

            a = Author.get(public_id=c.seen, dbsession=dbsession)
            if a is None:
                return
            print(f"# {a}")
            if a.seen in seen_set:
                print(f"{a.seen} already seen!")
                print(f"### LOOP: a {a.seen} already seen!")
                raise SeenLoop
            seen_set.add(a.seen)

            print("seen:", a.seen)
            object_id = a.seen

@company_app.command(name="trace")
def сompany_trace(oid: str = typer.Argument(None, help="object_id")):
    
    object_id = resolve_alias(oid) if oid and oid.lower() != ":all" else None

    if object_id:
        try:
            trace_company(object_id=object_id)
        except SeenLoop:
            print(f"### SEENLOOP: {object_id}")

    else:
        with DBSession() as dbsession:
            # loop over all companies
            stmt = select(Company)
            count = dbsession.scalar(select(func.count()).select_from(stmt.subquery()))        
            for idx, c in enumerate(dbsession.scalars(stmt)):
                print(f"# {idx} / {count} {c}")
                try:
                    trace_company(object_id=c.object_id)
                except SeenLoop:
                    print(f"### SEENLOOP: {object_id}")
                print()

@company_app.command(name="list")
def сompany_list(
                needle: str = typer.Argument(None, help="search needle in object_id/title/address"),
                fmt: str = typer.Option("full", "--fmt", "-f", help="Output format: (full*/brief/json"),
                quiet: bool = typer.Option(False, "--quiet", "-q", help="Quiet mode, no output (only summary)"),
                filter_expr: str = typer.Option(None, "--expr", help="company filter expression"),
                region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)"),
                limit: int = typer.Option(None, "-l", "--limit", help="Limit to N companies"),
                error: bool = typer.Option(None, "-e", "--error", help="Process only error companies"),
                ok: bool = typer.Option(None, "-k", "--ok", help="Process only ok companies"),
                nr: bool = typer.Option(False, "--nr", help="count nreviews"),
                updated: int | None = typer.Option(None, "-u", "--updated", help=">0: updated within N days, <0: updated older then N days, 0: never updated"),
                sum_: bool = typer.Option(None, "--sum", help="Process only ok companies")                
                ):
    """ list company's object_ids """


    if quiet:
        sum_ = True

    stmt = select(Company)

    if region_id is not None:
        stmt = stmt.where(Company.region_id == region_id)

    if ok:
        stmt = stmt.where(Company.error.is_(None))
    
    if error:
        stmt = stmt.where(Company.error.isnot(None))

    if needle:
        needle_like = f"%{needle.lower()}%"
        stmt = stmt.where(
                func.lower(Company.search_str).like(needle_like),
        )

    if updated is not None:
        if updated > 0:
            stmt = stmt.where(
                Company.updated_at.isnot(None),
                Company.updated_at >= (datetime.now(timezone.utc) - timedelta(days=updated)).date()
            )
        elif updated < 0:
            stmt = stmt.where(                
                    Company.updated_at.isnot(None),
                    Company.updated_at < (datetime.now(timezone.utc) - timedelta(days=abs(updated))).date()
                )
        else:
            stmt = stmt.where(Company.updated_at.is_(None))

    if limit:
        stmt = stmt.limit(limit)

    total = 0
    printed = 0
    skipped = 0
    cnt = None
    expr: evalidate.Expr | None = None
    filtered = list()

    model = evalidate.mult_eval_model.clone()
    model.nodes.extend(['Call', 'Attribute'])    
    model.attributes.extend(['lower', 'upper'])

    if filter_expr:
        try:
            expr = evalidate.Expr(expr=filter_expr, model=model)
        except (evalidate.ValidationException, evalidate.CompilationException)  as e:
            print(e)
            return 1

    with DBSession() as dbsession:

        if sum_ and quiet and expr is None:            
            cnt = count(stmt, dbsession)
            print(f"# SQL count: {cnt}")
            return

        if sum_:
            #cnt = dbsession.scalar(select(func.count()).select_from(stmt.subquery()))
            cnt = count(stmt, dbsession)

        for c in dbsession.scalars(stmt):

            total+=1

            if expr:
                # filter
                try:
                    if not expr.eval(c.to_dict(nreviews=nr)):
                        skipped += 1
                        continue
                except evalidate.ExecutionException as e:
                    print(e, file=sys.stderr)
                    sys.exit(1)

            printed += 1

            if fmt == "brief":
                print(c.object_id)
            elif fmt == "full":
                nrstr = f'NR:{c.nreviews()}' if nr else ''
                print(f'{c.object_id} ({c.rating_2gis}) r{c.region_id} {c.title} {nrstr}')
            elif quiet:
                pass
            elif fmt == "json":
                # json
                filtered.append(c.to_dict(nreviews=nr))
            else:
                # template
                tpl = fmt.format(**c.to_dict(nreviews=nr))
                print(tpl)

        if fmt == "json":
            print(json.dumps(filtered, indent=4))

        if sum_:
            print(f"# SQL count: {cnt} (printed:{printed} + skipped:{skipped} = {total})")



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
            if c:

                if c.updated_at:
                    verb = "Refresh"
                else:
                    verb = "Fetch"
                
                old_updated = c.updated_at

                old_nr = c.nreviews()
                print(f"{verb} data for existing company {c.object_id}: {c.title}  reviews:{old_nr}")
                c.update_reviews(dbsession=dbsession, full=full)

                errstr = f"ERR: {c.error}" if c.error else ''

                print(f"nreviews: {old_nr} => {c.nreviews()} update: {old_updated} => {c.updated_at}  {errstr} after fetch (update)")
                dbsession.commit()
                return

            # missing company
            else:                
                try:
                    Company.fetch(object_id=object_id, full=full, notolder=cutoff)
                    c = Company.get(object_id=object_id, dbsession=dbsession)
                except AFNoCompany as e:
                    print(e)
                    logger.error(e)
                    if c:
                        c.error = str(e)
                    else:
                        print("set emptyerr record")
                        Company.emptyerr(object_id=object_id, err=str(e))
                        
        else:
            # no object_id, (:all). process region
            if region_id is None:
                print("Need either object_id or region_id")
                return 1
            
            stmt = select(Company).where(Company.region_id == region_id, Company.error.is_(None))

            if not update:
                stmt = stmt.where(Company.updated_at.is_(None))

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

@company_app.command(name="update")
def company_update(
                oid: str = typer.Argument(None, help="2GIS object_id"),
                region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)"),
                days: int = typer.Option(30, "-d", "--days", help="Process only companies updated older then N days"),
                limit: int = typer.Option(10, "-l", "--limit", help="Limit to N companies"),
                ):
    print(f"refresh {oid} r{region_id} days={days}")

    stmt = select(Company).where(Company.updated_at.isnot(None), Company.error.is_(None))

    if region_id is not None:
        stmt = stmt.where(Company.region_id == region_id)

    if oid is not None:
        object_id = resolve_alias(oid)
        stmt = stmt.where(Company.object_id == object_id) 
    
    if oid is None:
        # this filter only makes sense for bulk update
        stmt = stmt.where(Company.updated_at < datetime.now(timezone.utc) - timedelta(days=days))
    
    
    stmt = stmt.order_by(Company.updated_at.asc())
    stmt = stmt.limit(limit)

    total = 0

    with DBSession() as dbsession:

        for c in dbsession.scalars(stmt):
            total+=1
            old_nr = c.nreviews()
            print(f"{total}: {c.object_id} r:{c.region_id} nr: {c.nreviews()} {c.updated_at} {(datetime.now() - c.updated_at).days} days ({c.title})")
            try:
                Company.fetch(object_id=c.object_id, full=True, notolder=c.updated_at)
            except AFNoCompany as e:
                c.error = str(e)

            print(f"UPDATED {c.object_id} nr: {old_nr} --> {c.nreviews()}\n")
        dbsession.commit()

@company_app.command(name="compare")
def сompany_compare(
                oid: str = typer.Argument(None, help="2GIS object_id"),
                oid2: str = typer.Argument(None, help="2GIS object_id 2")
                ):
    object_id = resolve_alias(oid)
    object_id2 = resolve_alias(oid2)

    with DBSession() as dbsession:
        c1 = Company.get(object_id=object_id, dbsession=dbsession)
        c2 = Company.get(object_id=object_id2, dbsession=dbsession)

        revs1 = c1.data_reviews()
        revs2 = c2.data_reviews()

        df1 = pd.DataFrame(revs1)
        df2 = pd.DataFrame(revs2)

        authors1 = set(df1['author_id'].dropna().unique())
        authors2 = set(df2['author_id'].dropna().unique())

        only1 = authors1 - authors2
        only2 = authors2 - authors1
        both = authors1 & authors2

        print(f"A: {c1.object_id} {c1.title} reviews:{len(df1)} unique authors:{len(authors1)}")
        print(f"B: {c2.object_id} {c2.title} reviews:{len(df2)} unique authors:{len(authors2)}")
        print(f"In both: {len(both)}")

        for author in both:
            a = Author.get(public_id=author, dbsession=dbsession)
            # a_date = datetime! date of review to company1
            a_date = df1[df1['author_id'] == author]['created'].max().split(' ')[0]
            b_date = df2[df2['author_id'] == author]['created'].max().split(' ')[0]

            a_rate = df1[df1['author_id'] == author]['rating'].mean()
            b_rate = df2[df2['author_id'] == author]['rating'].mean()
            print(f"{a.public_id} {a.created.date()} {a.name} {a_date} {b_date} {a_rate}/{b_rate}")

        



@company_app.command(name="neigh", hidden=True)
@company_app.command(name="neighbors")

def сompany_neighbors(
                oid: str = typer.Argument(None, help="2GIS object_id"),
                minhits: int = typer.Option(10, "--minhits", "-m", help="Minimum common authors to be a neighbor")
                ):
    object_id = resolve_alias(oid)

    print("Calculating neighbors for company:", object_id)

    nbrs = Neighbors(a_oid=oid)

    nbrs.process()

    with DBSession() as dbsession:
        for n in nbrs.topneighbors(minhits=minhits):
            print(n.dumps(dbsession=dbsession))
            #_c = Company.get_or_fetch(object_id=n.oid, dbsession=dbsession, full=False)   
            #print(f"{n.hits} ({n.rating:.2f}) hits: {_c}")



def OLD_сompany_neighbors(
                oid: str = typer.Argument(None, help="2GIS object_id"),
                minhits: int = typer.Option(10, "--minhits", "-m", help="Minimum common authors to be a neighbor")
                ):
    object_id = resolve_alias(oid)

    print("Calculating neighbors for company:", object_id)

    nbrs = Neighbors()

    with DBSession() as dbsession:
        c = Company.get(object_id=object_id, dbsession=dbsession)
        reviews = c.data_reviews()
        authors = set()
        for r in reviews:
            if r['provider'] != '2gis' or r['private']:
                continue
            authors.add(r['author_id'])

        for a in authors:
            aobj = Author.get(public_id=a, dbsession=dbsession)
            if aobj is None:
                continue
            arevs = aobj.data_reviews()
            for ar in arevs:
                if ar['object_id'] == object_id:
                    continue
                print(ar)
                nbrs.b_hit(public_id=a, oid=ar['object_id'], rate=ar['rating'])
        
    with DBSession() as dbsession:
        for n in nbrs.topneighbors(minhits=minhits):
            _c = Company.get_or_fetch(object_id=n.b_oid, dbsession=dbsession, full=False)   
            print(f"{n.bhits} ({n.brating:.2f}) hits: {_c}")
