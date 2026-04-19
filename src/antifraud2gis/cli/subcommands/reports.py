import typer

from sqlalchemy import select, func, case, desc

from rich.console import Console
from rich.table import Table
from rich import print
import click

from ...db import DBSession, Session
from ...models.metric import Metric
from ...models.metricperc import MetricPerc
from ...models.company import Company
from ...models.author import Author
from ...aliases import resolve_alias
from ...metrics import run_metrics, save_metrics, metrics_all, metrics_high, metrics_low
from ...metrics.fraudreport import FraudReport
from ...companymetric import CompanyMetric
from ...logger import logger
from ...exceptions import AFNoCompany

reports_app = typer.Typer(help="Reports commands")



@reports_app.command(name="fraud")
def reports_fraud(
    oid: str = typer.Argument(None, help="object_id"),
    ):
    """ analyse fraud metrics """
   
    object_id = resolve_alias(oid) if oid and oid.lower() != ':all' else None
    if object_id is None:
        return
    
    with DBSession() as dbsession:
        c = Company.get(object_id, dbsession=dbsession)
        cm = CompanyMetric(company=c, dbsession=dbsession)
        
        if cm.nmetrics() == 0:
            cm.calculate()
        fr = FraudReport(c, control_region_id=1, dbsession=dbsession)
        fr.dump()


def old_reports_fraud(
    oid: str = typer.Argument(None, help="object_id"),
    region_id: int | None = typer.Option(None, "-r", help="region_id or nothing"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose mode")
    ):
    """ analyse fraud metrics """
    

    object_id = resolve_alias(oid) if oid and oid.lower() != ':all' else None
    if object_id:
        print("Object ID:", object_id)
    else:
        print("All companies")
    
    with DBSession() as dbsession:
        c = Company.get(object_id, dbsession=dbsession)

        if region_id is None:            
            region_id = c.region_id 
        else:
            print(f"Force use of region_id: {region_id}")

        
        if not c:
            raise AFNoCompany(f"Company {object_id} not found")
        
        print("Report for company:", c)

        if MetricPerc.need_recalculate(c.region_id, dbsession):
                print("Recalculating percentiles...")
                with DBSession() as dbsession2:
                    MetricPerc.recalculate(c.region_id, dbsession2)
                    dbsession2.commit()
        

        print("analyse fraud metrics...")
        for metric in metrics_all:
            stars_hit = 0
            stars_total = 0

            m = c.get_metric(metric)
            if not m or m.value is None:
                print(f"  Metric {metric} not found or has no value")
                continue
            # print(f"  Metric {metric} = {m.value}")

            # get percentiles for city
            for mp in dbsession.query(MetricPerc).filter(
                MetricPerc.region_id == region_id,
                MetricPerc.name == metric,
            ).all():
                stars_total += 1
                if verbose:
                    print(f"... {mp}")

                if metric in metrics_high:
                    # normal, high metric
                    if m.value > mp.value:
                        if verbose:
                            print(f"    [bold red]FRAUD ALERT![/bold red] Metric {metric}={m.value} > {mp.p}% percentile {mp.value}")
                        stars_hit += 1
                else:
                    # low metric
                    # normal, high metric
                    if m.value < mp.value:
                        if verbose:
                            print(f"    [bold red]FRAUD ALERT![/bold red] Metric {metric}={m.value} < {mp.p}% percentile {mp.value}")
                        stars_hit += 1

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
    



def companies_per_region():
    """ show companies per region """
    with DBSession() as dbsession:
        stmt = (
            dbsession.query(
                Company.region_id,
                func.count().label("company_count")
            )
            .group_by(Company.region_id)
            .order_by(desc("company_count"))
        )

        for region_id, cnt in dbsession.execute(stmt):
            print(f"region {region_id} : {cnt}")
    return


def region_summary(region_id: int):
    with DBSession() as dbsession:

        total_companies = dbsession.query(Company).filter(Company.region_id == region_id).count()
        print(f"Total companies in region {region_id}: {total_companies}")
        error_companies = dbsession.query(Company).filter(Company.region_id == region_id, Company.error.is_not(None)).count()
        print(f"Companies with errors in region {region_id}: {error_companies}")
        noerror_companies = dbsession.query(Company).filter(Company.region_id == region_id, Company.error.is_(None)).count()
        print(f"Companies without errors in region {region_id}: {noerror_companies}")
        updated_companies = dbsession.query(Company).filter(Company.region_id == region_id, Company.error.is_(None), Company.updated_at.is_not(None)).count()
        print(f"Companies with updated data in region {region_id}: {updated_companies}")

def companies_in_region(region_id: int):
    with DBSession() as dbsession:
        stmt = (
            dbsession.query(
                Company.city,
                func.count().label("company_count"),
                func.sum(case((Company.error.is_(None), 1), else_=0)).label("ok_count"),
                func.sum(case((Company.error.is_not(None), 1), else_=0)).label("error_count"),
                func.sum(case((Company.updated_at.is_not(None), 1), else_=0)).label("updated"),
            )
            .filter(Company.region_id == region_id)
            .group_by(Company.city)
            .order_by(func.count().desc())
        )

        table = Table(title=f"Region {region_id} Summary")

        table.add_column("City", style="cyan", no_wrap=True)
        table.add_column("Total", justify="right", style="bold")
        table.add_column("OK", justify="right", style="green")
        table.add_column("Error", justify="right", style="red")
        table.add_column("Loaded", justify="right")

        for city, total, ok_count, error_count, loaded_count in dbsession.execute(stmt):
            table.add_row(city, str(total), str(ok_count), str(error_count), str(loaded_count))
        
        console = Console()
        console.print(table)

@reports_app.command(name="global")
def reports_global(report: str | None = typer.Argument("region", 
                        click_type=click.Choice(["region"]),
                        help="report type: city or region"),
                    limit: int | None = typer.Option(None, "-l", help="limit to top N records")):
    """ show companies per region """

    companies_per_region()



@reports_app.command(name="region")
def reports_region(region_id: int = typer.Argument(1, help="region_id"),
                    report: str | None = typer.Argument("sum", 
                        click_type=click.Choice(["sum", "summary", "percity"]),
                        help="report type: city or region"),
                    limit: int | None = typer.Option(None, "-l", help="limit to top N records")):
    """ show companies per region """


    print("REPORT:", report)

    if report == "percity":
        companies_in_region(region_id)
    elif report in ["sum", "summary"]:
        region_summary(region_id)

