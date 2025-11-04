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
from ...metrics import run_metrics, save_metrics
from ...logger import logger
from ...exceptions import AFNoCompany

percentiles_app = typer.Typer(help="Metrics commands")

@percentiles_app.command(name="list")
def percentiles_list(city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city")):
    """ show percentiles """

    with DBSession() as dbsession:
        stmt = dbsession.query(MetricPerc)
        if city:
            stmt = stmt.filter(MetricPerc.city == city)

        c = stmt.count()
        print(f"# total: {c} metrics")

        for m in stmt:
            print(m)


@percentiles_app.command(name="run")
def percentiles_run(city: str = typer.Argument(help="Process only companies from this city")):
    """ calculate percentiles """

    metrics = ['rpa:mean', 'rpa:median']
    p_values = [50, 75, 90, 95, 99]
    

    with DBSession() as dbsession:
        for metric in metrics:
            for percentile in p_values:
                
                values = dbsession.scalars(
                    select(Metric.value)
                    .join(Metric.company)
                    .where(Metric.name == metric, Company.city == city, Metric.value.isnot(None))
                ).all()

                p = float(np.percentile(values, percentile)) if values else None
                if p is None:
                    print(f"  {metric} {percentile}% percentile = N/A (no values)")
                    continue
                print(f"  {metric} {percentile}% percentile = {p} from {len(values)} values")

                # try fetch existing percentile
                mp = MetricPerc.get(city=city, name=metric, p=percentile, dbsession=dbsession)               
                if mp:
                    mp.value = p
                    mp.calculated = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
                else:
                    # or make new
                    mp = MetricPerc(
                        city=city,
                        name=metric,
                        p=percentile,
                        value=p,
                        calculated=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
                    )
                    dbsession.add(mp)
        dbsession.commit()

@percentiles_app.command(name="wipe")
def percentiles_wipe(city: str = typer.Argument(None, help="Process only records from this city")):
    """ wipe percentiles """
    with DBSession() as dbsession:
        stmt = dbsession.query(MetricPerc)
        if city:
            stmt = stmt.filter(MetricPerc.city == city)

        c = stmt.count()
        print(f"# total: {c} percentiles to delete")

        if c > 0:
            stmt.delete(synchronize_session=False)
            dbsession.commit()
            print("Deleted")
        else:
            print("Nothing to delete")

