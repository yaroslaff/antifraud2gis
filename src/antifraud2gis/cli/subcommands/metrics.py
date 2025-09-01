import typer

from rich import print_json
import pandas as pd
from sqlalchemy import select, func, and_
import time

from ...db import DBSession, Session
from ...models.metric import Metric
from ...models.company import Company
from ...models.author import Author
from ...aliases import resolve_alias
from ...metrics import run_metrics, save_metrics
from ...logger import logger
from ...exceptions import AFNoCompany


metrics_app = typer.Typer(help="Metrics commands")

@metrics_app.command(name="list")
def metrics_list(oid: str = typer.Argument(None, help="show only for object_id")):
    """ show metrics """


    object_id = resolve_alias(oid) if oid.lower() != ':all' else None

    with DBSession() as dbsession:
        stmt = dbsession.query(Metric)
        if object_id:
            stmt = stmt.filter(Metric.company_id == object_id)

        c = stmt.count()
        print(f"# total: {c} metrics")

        for m in stmt:
            print(m)



@metrics_app.command(name="wipe")
def metrics_wipe(oid: str = typer.Argument(help="show only for object_id")):
    """ wipe metrics """
    object_id = resolve_alias(oid) if oid.lower() != ':all' else None
    print("wipe metrics...", object_id)

    with DBSession() as dbsession:
        if oid.lower() == ':all':
            print("wipe metrics for ALL companies")
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

        logger.debug(f"Load {len(data)} authors...")
        # company df
        cdf = pd.DataFrame(data)

        adf = pd.DataFrame()
        
        if cdf.empty:
            logger.error(f"Empty reviews for {c.object_id}")
            return

        for author_id in cdf['author_id'].dropna().unique():
            with DBSession() as dbsession2:
                # print(author_id)
                a = Author.get_or_fetch(public_id=author_id, dbsession=dbsession2)
                adf = pd.concat([adf, pd.DataFrame(a.data_reviews(dbsession=dbsession2))], ignore_index=True)


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
def metrics_run(oid: str = typer.Argument(..., help="2GIS object_id")):
    """ run metrics for company """


    if oid == ":all":

        started = time.time()
        part_started = time.time()
        part_size = 100

        with DBSession() as dbsession:

            total = dbsession.scalar(
                select(func.count()).select_from(Company).where(
                    and_(
                        Company.metrics_calculated.is_(None),
                        Company.updated_at.isnot(None)
                    ))
            )
            print(f"Total: {total} companies to do")

            for idx, c in enumerate(dbsession.scalars(
                select(Company).where(
                    Company.metrics_calculated.is_(None),
                    Company.updated_at.isnot(None),
                    Company.error.is_(None)
            )), start=1):
                print(f"{idx}/{total} uptime: {int(time.time() - started)}s {c}")
                metrics_run_code(c)
                if idx % part_size == 0:
                    print(f"PART ({part_size}) finished in {int(time.time() - part_started)}s RATE: {(int(time.time() - part_started))/part_size:.1f} seconds per company")
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


