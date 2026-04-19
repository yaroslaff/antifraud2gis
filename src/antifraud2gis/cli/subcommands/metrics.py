import typer

from rich import print_json
import pandas as pd
from sqlalchemy import select, exists, func, and_
import time
import sys
import plotly.express as px

from ...db import DBSession, Session
from ...models.metric import Metric
from ...models.metricperc import MetricPerc
from ...models.company import Company
from ...models.author import Author
from ...models.authormetric import AuthorMetric
from ...aliases import resolve_alias
from ...metrics import run_metrics, save_metrics, metrics_all, metrics_high, metrics_low, percentiles_values
from ...logger import logger
from ...exceptions import AFNoCompany
from ...companymetric import CompanyMetric


metrics_app = typer.Typer(help="Metrics commands")


@metrics_app.command(name="top")
def metrics_top(metric: str = typer.Argument(None, help="metric name"),
                region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)"),
                city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city"),
                asc: bool = typer.Option(False, "--asc", help="ascending order"),
                desc: bool = typer.Option(False, "--desc", help="descending order"),
                ):
    """ show metrics """

    with DBSession() as dbsession:
        stmt = dbsession.query(Metric).filter(Metric.name == metric)

        if region_id:
            stmt = stmt.where(Metric.region_id == region_id)

        if city:
            stmt = stmt.join(Company).filter(Company.city == city)



        if asc:
            ascending = True
        elif desc:
            ascending = False
        else:
            if metric in metrics_low :
                ascending = True
            else:
                ascending = False

        if ascending:
            stmt = stmt.order_by(Metric.value)
        else:
            stmt = stmt.order_by(Metric.value.desc())
        
        stmt = stmt.limit(20)


        c = stmt.count()
        print(f"# total: {c} metrics")

        for m in stmt:
            print(f"{m.company.object_id} {m.company.title!r} r{m.company.region_id} (nr:{m.company.nreviews()}) {m.name}={m.value}")


@metrics_app.command(name="list")
def metrics_list(oid: str = typer.Argument(None, help="show only for object_id"),
            region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)"),
            metric: str = typer.Option(None, "-m", "--metric", help="Metric name"),
            city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city")):
    """ show metrics """
    object_id = resolve_alias(oid) if oid and oid.lower() != ':all' else None

    with DBSession() as dbsession:


        if metric and metric.startswith('-'):
            # search companies which has no metric
            metricname = metric[1:]
            print(f"# look for companies which has NO {metricname!r} metric")

            filters = [
                ~exists().where(
                    (Metric.company_id == Company.object_id) &
                    (Metric.name == metricname)
                )
            ]

            if region_id is not None:
                filters.append(Company.region_id == region_id)

            for c in dbsession.query(Company).filter(*filters).all():
                print(c)

            return


        stmt = dbsession.query(Metric)
        if object_id:
            stmt = stmt.filter(Metric.company_id == object_id)
        if region_id:
            stmt = stmt.filter(Metric.region_id == region_id)
        if metric:
            stmt = stmt.filter(Metric.name == metric)
        if city:
            stmt = stmt.join(Company).filter(Company.city == city)

        if metric:
            if metric in metrics_low:
                print("LOW")
                stmt = stmt.order_by(Metric.value.desc())
            else:
                print("HIGH")
                stmt = stmt.order_by(Metric.value)

        c = stmt.count()
        print(f"# total: {c} metrics")


        percentiles_tags = dict()

        if metric:
            for p in percentiles_values:
                pos = c * p // 100
                print(f"p{p}: {pos}/{c}")
                percentiles_tags[pos] = p
        

        for idx,m in enumerate(stmt):
            if idx in percentiles_tags:
                tag = f"<<< p{percentiles_tags[idx]}"
            else:
                tag = ""
            print(f'{idx+1:3d} {m} {tag}')



@metrics_app.command(name="graph")
def metrics_graph(metric: str = typer.Argument(None, help="Metric name"),
            region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)"),            
            city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city"),
            write: str = typer.Option(None, "-w", "--write", help="Write chart to file (html/png)"),
            size: int = typer.Option(10, "-s", "--size", help="Marker size"),
            object_id: str = typer.Option(None, "-o", help="Highlight this object_id")):
    """ show metrics """
    
    with DBSession() as dbsession:

        stmt = dbsession.query(Metric)
        if metric:
            stmt = stmt.filter(Metric.name == metric)
        if region_id:
            stmt = stmt.filter(Metric.region_id == region_id)
        if city:
            stmt = stmt.join(Company).filter(Company.city == city)


        c = stmt.count()
        print(f"# total: {c} metrics")

        points = list()


        for idx, m in enumerate(stmt):
            highlight = "normal" if m.company.object_id != object_id else "highlight"

            if highlight == "highlight":
                print(f"HIGHLIGHT: {m.company.object_id} {m.company.title}")

            points.append({
                "name": f'{m.company.object_id} {m.company.title}',
                "reviews": m.company.nreviews(fresh=True, provider="2gis"),
                "metric": m.value,
                "highlight": highlight
            })

        print(f"Draw {len(points)} points")

        if not len(points):
            print("No points to draw!")
            sys.exit(1)

        fig = px.scatter(points, x="reviews", y="metric", hover_name="name", 
                        color="highlight",
                        color_discrete_map={"normal": "steelblue", "highlight": "red"},
                        title=f"{metric} r{region_id}")

        print("load percentiles...")
        stmtp = dbsession.query(MetricPerc).filter(MetricPerc.name == metric)
        if region_id:
            stmtp = stmtp.filter(MetricPerc.region_id == region_id)
        percentiles = {mp.p: mp.value for mp in stmtp}
        print("percentiles:", percentiles)


        # dash: "solid", "dot", "dash", "longdash", "dashdot", or "longdashdot"

        hline_param = dict(dash="dot", color="black", width=1)

        for p, v in percentiles.items():
            fig.add_hline(y=v, line=hline_param,   annotation_text=f"p{p}")

        fig.update_traces(marker_size=size)

        if not write:
            fig.show()                
        else:
            if write.endswith(".html"):
                fig.write_html(write)
            elif write.endswith(".png") or write.endswith(".jpg"):
                fig.write_image(write)


def countdown(n=10):
    print(f"Countown {n} seconds... (Ctrl+C to cancel)")
    for i in range(1, 10):
        print(i, end=' ', flush=True)
        time.sleep(1)
    print()

@metrics_app.command(name="wipe")
def metrics_wipe(
    oid: str = typer.Argument(None, help="show only for object_id"),
    region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)")
    ):
    """ wipe metrics """
    object_id = resolve_alias(oid) if oid is not None else None
    print("wipe metrics...", object_id)

    with DBSession() as dbsession:        
        if oid is None  and region_id is None:
            # WHOLE DATABASE
            print("wipe metrics for ALL companies")
            countdown()

            r = dbsession.query(Metric).delete()            
            for c in dbsession.query(Company).filter(Company.metrics_calculated != None):
                print("wipe metrics_calculated/metrics_signature for", c)
                c.metrics_calculated = None
                c.metrics_signature = None
                # c.wipe_metrics(dbsession=dbsession)

            dbsession.commit()

        else:
            if object_id:
                c = Company.get(object_id=object_id, dbsession=dbsession)
                c.wipe_metrics(dbsession=dbsession)
                dbsession.commit()
            else:


                stmt = select(Company).where(Company.region_id == region_id, Company.metrics_calculated.isnot(None))

                count_stmt = select(func.count()).select_from(stmt.subquery())
                count = dbsession.scalar(count_stmt)
                print(f"Total: {count} records")


                for c in dbsession.scalars(stmt):
                    print(f"delete metrics for {c}")
                    c.metrics_calculated = None
                    c.metrics.clear()
                print("commit")
                dbsession.commit()

        #ndeleted = stmt.delete()
        #dbsession.commit()
        #print(f"deleted {ndeleted} metrics") 

# cm 


@metrics_app.command(name="run")
def metrics_run(
    oid: str = typer.Argument(None, help="2GIS object_id or :all"),
    city: str = typer.Option(None, "-c", "--city", help="Process only companies from this city"),
    region_id: int = typer.Option(None, "-r", "--region_id", help="Process only companies from this region)")
    ):
    """ run metrics for company or :all companies """

    if oid is None:
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

            if region_id:
                filters = and_(filters, Company.region_id == region_id)

            total = dbsession.scalar(
                select(func.count()).select_from(Company).where(filters)
            )

            print(f"Total: {total} companies to do")

            for idx, c in enumerate(dbsession.scalars(select(Company).where(filters)), start=1):                
                if c.object_id.startswith("_test"):
                    print("SKIP test company", c)
                    continue

                cm = CompanyMetric(c, dbsession=dbsession)

                print(c.object_id, c.title, "mc:",c.metrics_calculated, c.updated_at, c.error)

                print(f"{idx}/{total} uptime: {int(time.time() - started)}s {c}")
                try:
                    print("# metrics_run_code", c)
                    # metrics_run_code(c)
                    cm.calculate()

                except Exception as e:
                    print("EXCEPTION IN metrics_run_code!", type(e), e)
                    sys.exit(1)

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

        cm = CompanyMetric(c, dbsession=dbsession)
        cm.calculate()
        cm.dump()

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
        