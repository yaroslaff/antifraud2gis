import typer
import numpy as np
from sqlalchemy import select, func, case
import datetime


from ...db import DBSession, Session
from ...models.metric import Metric
from ...models.metricperc import MetricPerc
from ...models.company import Company
from ...models.author import Author
from ...aliases import resolve_alias
from ...metrics import run_metrics, save_metrics, metrics_low, metrics_high, metrics_all, percentiles_values
from ...logger import logger
from ...exceptions import AFNoCompany

percentiles_app = typer.Typer(help="Metrics commands")

@percentiles_app.command(name="list")
def percentiles_list(
        # city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city"),
        region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)"),
        metric: str = typer.Option(None, "-m", "--metric", help="Metric name"),
        ):
    """ show percentiles """

    with DBSession() as dbsession:
        stmt = dbsession.query(MetricPerc)

        #if city:
        #    stmt = stmt.filter(MetricPerc.city == city)

        if region_id:
            stmt = stmt.filter(MetricPerc.region_id == region_id)
        if metric:
            stmt = stmt.filter(MetricPerc.name == metric)

        c = stmt.count()
        print(f"# total: {c} metrics")

        for m in stmt:
            print(m)


@percentiles_app.command(name="run")
def percentiles_run(
        region_id: int = typer.Argument(help="region id")
    ):
    """ calculate percentiles """        

    with DBSession() as dbsession:
        MetricPerc.recalculate(region_id, dbsession)
        dbsession.commit()

@percentiles_app.command(name="wipe")
def percentiles_wipe(
        region_id: int = typer.Argument(help="region id"),
        # city: str = typer.Argument(None, help="Process only records from this city")
    ):

    city = None

    """ wipe percentiles """
    with DBSession() as dbsession:
        stmt = dbsession.query(MetricPerc)
        if city:
            stmt = stmt.filter(MetricPerc.city == city)

        if region_id:
            stmt = stmt.filter(MetricPerc.region_id == region_id)


        c = stmt.count()
        print(f"# total: {c} percentiles to delete")

        if c > 0:
            stmt.delete(synchronize_session=False)
            dbsession.commit()
            print("Deleted")
        else:
            print("Nothing to delete")

