import typer

from rich import print_json
import pandas as pd
from sqlalchemy import select, func, and_
import time

from ...db import DBSession, Session
from ...models.metric import Metric
from ...models.company import Company
from ...models.author import Author
from ...models.authormetric import AuthorMetric
from ...aliases import resolve_alias
from ...metrics import run_metrics, save_metrics
from ...logger import logger
from ...exceptions import AFNoCompany


metrics_app = typer.Typer(help="Metrics commands")


@metrics_app.command(name="top")
def metrics_top(metric: str = typer.Argument(None, help="metric name"),
                city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city"),
                reverse: bool = typer.Option(False, "-r", "--reverse", help="Sort in reverse order", is_flag=True)):
    """ show metrics """

    with DBSession() as dbsession:
        stmt = dbsession.query(Metric).filter(Metric.name == metric)

        if city:
            stmt = stmt.join(Company).filter(Company.city == city)

        if reverse:
            stmt = stmt.order_by(Metric.value)
        else:
            stmt = stmt.order_by(Metric.value.desc())
        stmt = stmt.limit(20)


        c = stmt.count()
        print(f"# total: {c} metrics")

        for m in stmt:
            print(f"{m.company.object_id} {m.company.title!r} ({m.company.nreviews()}) {m.name}={m.value}")


@metrics_app.command(name="list")
def metrics_list(oid: str = typer.Argument(None, help="show only for object_id"),
                city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city")):
    """ show metrics """
    object_id = resolve_alias(oid) if oid and oid.lower() != ':all' else None

    with DBSession() as dbsession:
        stmt = dbsession.query(Metric)
        if object_id:
            stmt = stmt.filter(Metric.company_id == object_id)
        if city:
            stmt = stmt.join(Company).filter(Company.city == city)

        c = stmt.count()
        print(f"# total: {c} metrics")

        for m in stmt:
            print(m)



def countdown(n=10):
    print(f"Countown {n} seconds... (Ctrl+C to cancel)")
    for i in range(1, 10):
        print(i, end=' ', flush=True)
        time.sleep(1)
    print()


@metrics_app.command(name="wipe")
def metrics_wipe(oid: str = typer.Argument(help="show only for object_id")):
    """ wipe metrics """
    object_id = resolve_alias(oid) if oid.lower() != ':all' else None
    print("wipe metrics...", object_id)

    with DBSession() as dbsession:
        if oid.lower() == ':all':
            print("wipe metrics for ALL companies")
            countdown()

            r = dbsession.query(Metric).delete()            
            for c in dbsession.query(Company).filter(Company.metrics_calculated != None):
                print("wipe metrics_calculated/metrics_signature for", c)
                c.metrics_calculated = None
                c.metrics_signature = None
                # c.wipe_metrics(dbsession=dbsession)

            dbsession.commit()

        elif object_id:
            c = Company.get(object_id=object_id, dbsession=dbsession)
            c.wipe_metrics(dbsession=dbsession)
            dbsession.commit()

        #ndeleted = stmt.delete()
        #dbsession.commit()
        #print(f"deleted {ndeleted} metrics") 

# cm 


def metrics_run_code(c: Company):

    with DBSession() as dbsession:
        c = dbsession.merge(c)

        try:
            if c.full_load():
                # if loaded new reviews, refresh
                dbsession.refresh(c)

        except AFNoCompany as e:
            logger.error(e)
            c.error = str(e)
            dbsession.commit()
            return
                
        data = c.data_reviews()
        print_json(data=data)

        logger.debug(f"Load {len(data)} authors...")
        # company df
        cdf = pd.DataFrame(data)
        adf = pd.DataFrame()

        if cdf.empty:
            logger.error(f"Empty reviews for {c.object_id}")
            metrics = {"is_empty": 1}
            save_metrics(c, metrics=metrics, dbsession=dbsession)
            return

        for author_id in cdf['author_id'].dropna().unique():
            with DBSession() as dbsession2:
                # print(author_id)
                a = Author.get_or_fetch(public_id=author_id, dbsession=dbsession2)
                adf = pd.concat([adf, pd.DataFrame(a.data_reviews(dbsession=dbsession2))], ignore_index=True)

        print("ADF:", adf['provider'].value_counts())


        logger.debug("Running metrics...")
        try:
            metrics = run_metrics(c.object_id, cdf, adf)
            save_metrics(c, metrics=metrics, dbsession=dbsession)
        except AFNoCompany as e:
            logger.error(e)
            return

        # total df    
        print_json(data=metrics)





@metrics_app.command(name="run")
def metrics_run(
    oid: str = typer.Argument(..., help="2GIS object_id"),
    city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city")
    ):
    """ run metrics for company or :all companies """

    if oid == ":all":
        started = time.time()
        part_started = time.time()
        part_size = 100

        with DBSession() as dbsession:

            filters = and_(
                        Company.metrics_calculated.is_(None),
                        Company.updated_at.isnot(None),
                        Company.error.is_(None)
                    )


            if city:
                filters = and_(filters, Company.city == city)

            total = dbsession.scalar(
                select(func.count()).select_from(Company).where(filters)
            )

            print(f"Total: {total} companies to do")

            for idx, c in enumerate(dbsession.scalars(select(Company).where(filters)), start=1):                
                if c.object_id.startswith("_test"):
                    print("SKIP test company", c)
                    continue

                print(f"{idx}/{total} uptime: {int(time.time() - started)}s {c}")
                metrics_run_code(c)
                if idx % part_size == 0:
                    print(f"PART ({part_size}) ({idx}/{total}) finished in {int(time.time() - part_started)}s RATE: {(int(time.time() - part_started))/part_size:.1f} seconds per company")
                    part_started = time.time()


    else:
        try:
            object_id = resolve_alias(oid, purpose="metrics")
        except AFNoCompany:
            logger.error(f"Company {oid} not found")
            return

        assert(object_id is not None)
        with DBSession() as dbsession:
            try:
                c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=True)
            except AFNoCompany as e:
                logger.error(e)
                return

        metrics_run_code(c)

#
# Author metrics
#


def update_author_metrics(public_id: str, metrics: dict[str, float], dbsession: Session):
    a = dbsession.query(Author).filter(Author.public_id == public_id).first()
    if not a:
        print("Author not found", public_id)
        return

    for metric_name, value in metrics.items():

        metric = dbsession.query(AuthorMetric).filter_by(author=a, name=metric_name).first()
        if metric:
            metric.value = value
        else:
            metric = AuthorMetric(author=a, name=metric_name, value=value)
            dbsession.add(metric)
    # we do not commit here, caller should do it

@metrics_app.command(name="arun")
def metrics_author_run(
    public_id: str = typer.Argument(..., help="User public_id or :all"),
    ):
    """ run metrics for authro or :all companies """

    print("metrics_author_run", public_id)
    
    # load author reviews, count number of reviews per each company.city
    if public_id == ":all":
        with DBSession() as dbsession:
            total = dbsession.scalar(select(func.count()).select_from(Author)) or 0
            print(f"Total: {total} authors to do")

            started = time.time()
            part_started = time.time()
            part_size = 100

            for idx, a in enumerate(dbsession.scalars(select(Author)), start=1):
                if a.public_id.startswith("_test"):
                    print("SKIP test author", a)
                    continue

                if a.private:
                    # print(f"Author {a.public_id} {a.name} is private, cannot run metrics")
                    continue

                metrics = a.run_metrics()
                update_author_metrics(public_id=a.public_id, metrics=metrics, dbsession=dbsession)

                if idx % part_size == 0:
                    dbsession.commit()

                    eta = int((time.time() - started) / idx * (total - idx))                
                    print(f"PART {idx}/{total} {int(idx/total)}% finished in {int(time.time() - part_started)}s RATE: {(int(time.time() - part_started))/part_size:.2f} seconds per author. ETA: {eta//3600}h {(eta%3600)//60}m")
                    part_started = time.time()
            dbsession.commit()  
            print(f"ALL finished in {int(time.time() - started)}s RATE: {(int(time.time() - started))/total:.1f} seconds per author")

    else:
        with DBSession() as dbsession:
            a = Author.get_or_fetch(public_id=public_id, dbsession=dbsession)
            if a.private:
                print(f"Author {a.public_id} {a.name} is private, cannot run metrics")
                return
            metrics = a.run_metrics()
            for k, v in metrics.items():
                print(f"{k} = {v}")
            update_author_metrics(public_id=a.public_id, metrics=metrics, dbsession=dbsession)
            dbsession.commit()
                


@metrics_app.command(name="alist")
def metrics_alist(public_id: str = typer.Argument(None, help="show only for author_id")):
    """ show metrics for author(s)"""

    with DBSession() as dbsession:
        stmt = dbsession.query(AuthorMetric)
        if public_id:
            stmt = stmt.filter(AuthorMetric.author_id == public_id)

        c = stmt.count()
        print(f"# total: {c} metrics")

        for m in stmt:
            print(m)

@metrics_app.command(name="awipe")
def metrics_awipe(public_id: str = typer.Argument(None, help="wipeonly for author_id")):
    """ wipe metrics for author(s)"""


    if public_id is None or public_id == ":all":
        with DBSession() as dbsession:
            n = dbsession.query(AuthorMetric).delete()
            print(f"deleted {n} metrics for all authors")
            dbsession.commit()
            return
    
    else:
        with DBSession() as dbsession:
            stmt = dbsession.query(AuthorMetric)
            stmt = stmt.filter(AuthorMetric.author_id == public_id)
            # delete this author metrics
            n = stmt.delete()
            print(f"deleted {n} metrics for author {public_id}")
            dbsession.commit()
            return
        