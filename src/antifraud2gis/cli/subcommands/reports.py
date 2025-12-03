import typer

from sqlalchemy import select, func, case, desc

from rich.console import Console
from rich.table import Table


from ...db import DBSession, Session
from ...models.metric import Metric
from ...models.metricperc import MetricPerc
from ...models.company import Company
from ...models.author import Author
from ...aliases import resolve_alias
from ...metrics import run_metrics, save_metrics
from ...logger import logger
from ...exceptions import AFNoCompany

reports_app = typer.Typer(help="Reports commands")



@reports_app.command(name="fraud")
def reports_fraud(oid: str = typer.Argument(None, help="object_id"),):
    """ analyse fraud metrics """

    metric_list = [ 'rpa:mean', 'rpa:median']

    object_id = resolve_alias(oid) if oid and oid.lower() != ':all' else None
    if object_id:
        print("Object ID:", object_id)
    else:
        print("All companies")
    with DBSession() as dbsession:
        c = Company.get(object_id, dbsession=dbsession)
        if not c:
            raise AFNoCompany(f"Company {object_id} not found")
        
        print("Report for company:", c)

        print("analyse fraud metrics...")
        for metric in metric_list:
            stars_hit = 0
            stars_total = 0

            m = c.get_metric(metric)
            if not m or m.value is None:
                print(f"  Metric {metric} not found or has no value")
                continue
            print(f"  Metric {metric} = {m.value}")

            # get percentiles for city
            for mp in dbsession.query(MetricPerc).filter(
                MetricPerc.city == c.city,
                MetricPerc.name == metric,
            ).all():
                stars_total += 1

                if m.value > mp.value:
                    print(f"    [bold red]FRAUD ALERT![/bold red] Metric {metric}={m.value} > {mp.p}% percentile {mp.value}")
                    stars_hit += 1
                else:
                    # print(f"    OK. Metric {metric}={m.value} <= {mp.p}% percentile {mp.value}")
                    pass

            print(f"  {metric} ({m.value}): {stars_hit}/{stars_total} stars hit")


@reports_app.command(name="metriclist")
def reports_metriclist():
    """ show metrics """
    with DBSession() as dbsession:        
        stmt = (
            select(
                Metric.name,
                func.count().label("total"),
                # max and min
                func.max(Metric.value).label("max"),
                func.min(Metric.value).label("min"),
            )
            .group_by(Metric.name)
        )

        rows = dbsession.execute(stmt).mappings().all()
        for r in rows:
            print(f"{r['name']}: {r['total']} (min={r['min']} max={r['max']})")



@reports_app.command(name="city")
def reports_city(city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city"),
                 num: int = typer.Option(None, "-n", help="Only cities with at least N companies"),
                 sort: str = typer.Option("total", "-s", help="Sort by (total, ok, error, loaded)")
                 ):
    """ show companies per city """

    if city:
        print("City:", city)

        with DBSession() as dbsession:
            c = dbsession.query(Company).filter(Company.city == city).count()

            print(f"# total: {c} companies in {city}")
    else:
        # global statistics
        with DBSession() as dbsession:        
            stmt = (
                select(
                    Company.city,
                    func.count().label("total"),
                    func.sum(case((Company.error.is_(None), 1), else_=0)).label("ok_count"),
                    func.sum(case((Company.error.is_not(None), 1), else_=0)).label("error_count"),
                    func.sum(case((Company.updated_at.is_not(None), 1), else_=0)).label("updated"),
                )
                .group_by(Company.city)
            )

            if num:
                stmt = stmt.having(func.count() >= num)

            if sort == "ok":
                stmt = stmt.order_by(func.sum(case((Company.error.is_(None), 1), else_=0)).desc())
            elif sort == "error":
                stmt = stmt.order_by(func.sum(case((Company.error.is_not(None), 1), else_=0)).desc())
            elif sort == "loaded":
                stmt = stmt.order_by(func.sum(case((Company.updated_at.is_not(None), 1), else_=0)).desc())
            else:
                stmt = stmt.order_by(func.count().desc())

            rows = dbsession.execute(stmt).all()

            table = Table(title="Companies per City")

            table.add_column("City", style="cyan", no_wrap=True)
            table.add_column("Total", justify="right", style="bold")
            table.add_column("OK", justify="right", style="green")
            table.add_column("Error", justify="right", style="red")
            table.add_column("Loaded", justify="right")

            for city, total, ok_count, error_count, loaded_count in rows:
                table.add_row(city, str(total), str(ok_count), str(error_count), str(loaded_count))
            
            console = Console()
            console.print(table)
    

@reports_app.command(name="region")
def reports_region(region_id: int | None = typer.Argument(None, help="region_id or nothing"),
                   limit: int | None = typer.Option(None, "-l", help="limit to top N records")):
    """ show companies per region """
    if region_id is None:
        with DBSession() as dbsession:
            stmt = (
                dbsession.query(
                    Company.region_id,
                    func.count().label("company_count")
                )
                .group_by(Company.region_id)
                .order_by(desc("company_count"))
            )

            if limit:
                stmt = stmt.limit(limit)

            for region_id, cnt in dbsession.execute(stmt):
                print(f"region {region_id} : {cnt}")
        return

    # region_id given
    with DBSession() as dbsession:
        stmt = (
            dbsession.query(
                Company.city,
                func.count().label("company_count")
            )
            .filter(Company.region_id == region_id)
            .group_by(Company.city)
            .order_by(desc("company_count"))
        )

        if limit:
            stmt = stmt.limit(limit)

        for city, cnt in dbsession.execute(stmt):
            print(f"{city:20} {cnt}")
