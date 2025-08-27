import typer

from rich import print_json

from ...db import DBSession
from ...models.metric import Metric
from ...models.company import Company
from ...models.author import Author
from ...aliases import resolve_alias
from ...metrics import run_metrics, save_metrics
from ...logger import logger

import pandas as pd

metrics_app = typer.Typer(help="Metrics commands")

@metrics_app.command(name="list")
def metrics_list(oid: str = typer.Argument(None, help="show only for object_id")):
    """ show metrics """


    object_id = resolve_alias(oid) if oid else None

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
    object_id = resolve_alias(oid) if oid.lower() != 'all' else None
    print("wipe metrics...", object_id)

    with DBSession() as dbsession:
        if oid.lower() == 'all':
            print("wipe metrics for ALL companies")
            for c in dbsession.query(Company).filter(Company.metrics_calculated != None):
                print("..", c)
                c.wipe_metrics(dbsession=dbsession)

            dbsession.commit()

        elif object_id:
            c = Company.get(object_id=object_id, dbsession=dbsession)
            c.wipe_metrics(dbsession=dbsession)
            dbsession.commit()

        #ndeleted = stmt.delete()
        #dbsession.commit()
        #print(f"deleted {ndeleted} metrics") 

# cm 
@metrics_app.command(name="run")
def metrics_run(oid: str = typer.Argument(..., help="2GIS object_id")):
    """ run metrics for company """

    object_id = resolve_alias(oid)
    assert(object_id is not None)
    with DBSession() as dbsession:
        c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=True)
        print(f"Process {c}")
        data = c.data_reviews()

    logger.debug(f"Load {len(data)} authors...")
    # company df
    cdf = pd.DataFrame(data)

    adf = pd.DataFrame()
    for author_id in cdf['author_id'].dropna().unique():
        with DBSession() as dbsession:
            # print(author_id)
            a = Author.get_or_fetch(public_id=author_id, dbsession=dbsession)
            adf = pd.concat([adf, pd.DataFrame(a.data_reviews())], ignore_index=True)

    logger.debug("Running metrics...")
    metrics = run_metrics(c.object_id, cdf, adf)
    save_metrics(c, metrics=metrics, dbsession=dbsession)

    # total df
    print_json(data=metrics)
