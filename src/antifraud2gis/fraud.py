from collections import defaultdict
import json
import os
from rich import print_json
from rich.console import Console
from rich.table import Table
from rich.text import Text
import time
import sys
import datetime
import numpy as np
import gzip
from rich.progress import Progress

from typing import Optional

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .const import MAX_USER_REVIEWS
from .logger import logger
from .models.company import Company
from .models.metric import Metric

from .models.author import Author
from .relation import RelationDict
from .settings import settings
from .exceptions import AFReportNotReady, AFNoCompany, AFReportAlreadyExists
# from .usernotes import Usernotes
from .fd.master import MasterFD
from .db import DBSession

def detect(c: Company, dbsession: Session, explain: bool = False, force=False):

    debug_oids = os.getenv("DEBUG_OIDS", "").split(" ")
    debug_uids = os.getenv("DEBUG_UIDS", "").split(" ")


    # notes = Usernotes()

    logger.debug(f"Run fraud detection for {c}")



    # check metrics
    for m in c.metrics:
        print("METRIC:", m)

    # if c.report_path.exists() and not force and not explain:    
    if len(c.metrics) and not force and not explain:
        logger.debug(f"Metrics already exist")
        raise AFReportAlreadyExists(f"Metrics already exists")

    

    c.relations = RelationDict(c)

    start = time.time()

    if c.error:
        print("error")
        print(c)
        print(c.error)
        return

    c.full_load()

    c = dbsession.merge(c)

    """ skip too small targets """
    if c.nreviews() <= settings.min_reviews:
        # bypass
        score = {
            'trusted': True,
            'total_users': c.nreviews(),
            'reason': f'Too few reviews ({c.nreviews()}) to be fraudulent',
            'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        report = dict()        
        report['score'] = score
        report['relations'] = list()

        c.trusted = True
        c.detections = list()

        with gzip.open(c.report_path, "wt") as fh:
            json.dump(report, fh)
        
        return score
            # print("saved")

    logger.info(f"Run fraud detect for {c.title} ({c.address}) {c.object_id} {c.nreviews()} reviews")

    master_detector = MasterFD(c, explain=True)

    with Progress() as progress:
        task = progress.add_task("[cyan]Analyzing user's reviews...", total=c.nreviews())

        for idx, cr in enumerate(c.reviews, start=1):
            # cr = dbsession.merge(cr)

            # insp = inspect(cr)


            # notes.counter('total_reviews')
            progress.update(task, advance=1, description=f"[green]User {idx}")

            master_detector.feed(cr)    

    score = master_detector.get_score()

    # logger.info(f"SCORE: {score} for {c.object_id}")

    report = dict()
    report['score'] = score
    report['relations'] = c.relations.export()

    metrics = master_detector.metrics()
    print_json(data=metrics, indent=4)

    # Save metrics

    for metric_name, value in metrics.items():

        metric = dbsession.query(Metric).filter_by(company=c, name=metric_name).first()
        if metric:
            metric.value = value
        else:
            metric = Metric(company=c, name=metric_name, value=value)
            dbsession.add(metric)

    c.metrics_calculated = datetime.datetime.now()
    c.metrics_signature = settings.param_fp()
    dbsession.add(c)
    dbsession.commit()


    with gzip.open(c.report_path, "wt") as fh:
        json.dump(report, fh)

    if not score['trusted']:
        print(f"save explain to {c.explain_path}")    
        with gzip.open(c.explain_path, "wt") as fh:            
            master_detector.explain(fh=fh)

    logger.info(f"DETECTION RESULT {c}")
    return score


def dump_report(object_id: str, dbsession: Optional[Session] = None):
    dbsession = dbsession or DBSession()

    c = Company.get_or_fetch(object_id, dbsession=dbsession)
    if c.error:
        print(f"ERROR for {c.get_title()} ({c.address}): {c.error}")
        return

    try:
        print("read report from", c.report_path)
        with gzip.open(c.report_path, "rt") as fh:
            report = json.load(fh)
    except FileNotFoundError:
        raise AFReportNotReady(f"Report not ready for {object_id}")



    table_title = f"{c.get_title()} ({c.address}) {c.object_id}"

    if not c.report_reliable(report=report):
        table_title += " [NOT RELIABLE]"

    console = Console()
    table = Table(show_header=True, header_style="bold magenta", title=table_title)
    # table.add_column("T", style='red')
    table.add_column("Company name")
    table.add_column("Town")
    table.add_column("ID/Alias")
    table.add_column("Hits")
    #table.add_column("Mean")
    table.add_column("Median")
    table.add_column("Rating")

    for rel in report['relations']:
        _c = Company.get_or_fetch(object_id=rel['oid'], full=False, dbsession=dbsession)

        if rel['hits'] >= settings.risk_hit_th:
            hits_cell = Text(f"{rel['hits']}", style='red')
        else:
            hits_cell = Text(str(rel['hits']), style="green")

        if rel['median'] < settings.risk_median_th:
            median_cell = Text(str(rel['median']), style='red')
        else:
            median_cell = Text(str(rel['median']), style='green')

        if rel['arating'] >= settings.risk_highrate_th and rel['brating'] >= settings.risk_highrate_th:
            rating_cell = Text(f"{rel['arating']:.1f} {rel['brating']:.1f}", style='red')
        else:
            rating_cell = Text(f"{rel['arating']:.1f} {rel['brating']:.1f}")

        table.add_row( str(_c.get_title()), str(_c.city), Text(_c.object_id, style='grey30'), hits_cell,
                        # f"{rel.mean:.1f}", 
                        median_cell, rating_cell)
    print()
    console.print(table)
    print_json(data=report['score'])



    # rprint(self)
