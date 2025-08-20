import typer

from rich import print_json

from ..db import DBSession
from ..models.metric import Metric
from ..models.company import Company
from ..aliases import resolve_alias
from ..metrics import run_metrics

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

    metrics = dict()

    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=True)
        data = c.data_reviews()

    print_json(data=data)
    cdf = pd.DataFrame(data)

    cdf["author_created"] = pd.to_datetime(cdf["author_created"])
    cdf["created"] = pd.to_datetime(cdf["created"])
    cdf["age"] = (cdf["created"] - cdf["author_created"]).dt.days

    run_metrics(object_id, cdf)
    print(cdf)
    print("LEN:", len(cdf))
    print("mean/median age:", cdf["age"].mean(), cdf["age"].median())

    metrics['mean_age'] = int(cdf.loc[cdf["provider"] == "2gis", "age"].mean())
    metrics['median_age'] = int(cdf.loc[cdf["provider"] == "2gis", "age"].mean())
    
    
    df_2gis = cdf.loc[(cdf["provider"] == "2gis") & (cdf["object_id"] == object_id)]
    # print(df_2gis)

    print("OBJECT_ID:")
    print(cdf.groupby("object_id"))

    print_json(data=metrics)
