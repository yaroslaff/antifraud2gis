import typer

from ..db import DBSession
from ..models.metric import Metric
from ..models.company import Company
from ..aliases import resolve_alias

metrics_app = typer.Typer()

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
