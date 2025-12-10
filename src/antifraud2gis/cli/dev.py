import argparse
import time
import random
import importlib.util
import dateutil.parser
import redis
import random
from rich import print_json
from rich.text import Text
from rich.progress import Progress
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from pathlib import Path
from argalias import ArgAlias
import os
import sys
import requests
from collections import defaultdict
import numpy as np
import json
import gzip
import typer
from datetime import datetime, date
import dateutil
from IPython import start_ipython
import numpy as np
import pandas as pd

# import lmdb

from ..models.company import Company
from ..models.author import Author
from ..models.metric import Metric
from ..models.metricperc import MetricPerc
from ..models.review import Review
from ..models.authormetric import AuthorMetric

from ..settings import settings
from ..fraud import detect, dump_report
from ..exceptions import AFNoCompany, AFNoTitle, AFCompanyError
from ..aliases import resolve_alias
from .status import print_full_status
from ..tasks import submit_fraud_task, cooldown_queue
from ..const import REDIS_TASK_QUEUE_NAME, REDIS_TRUSTED_LIST, REDIS_UNTRUSTED_LIST, REDIS_WORKER_STATUS, REDIS_WORKER_STATUS_SET, \
                        REDIS_DRAMATIQ_QUEUE, REVIEWS_KEY, \
                        LMDB_MAP_SIZE, REDIS_WORKER_STARTED
from ..logger import logger, loginit
from ..session import http_session
from ..db import DBSession, check_or_create_db
from ..net.company_reviews import CompanyReviewsIterator
from ..net.author_reviews import AuthorReviewsIterator
from ..testdata import create_test_records, wipe_test_records

from .subcommands.metrics import metrics_app
from .subcommands.author import author_app
from .subcommands.company import company_app
from .subcommands.percentiles import percentiles_app
from .subcommands.reports import reports_app
from .subcommands.extra import extra_app

import pandas as pd

def countdown(n=5):
    for i in range(n, 0, -1):
        print(f'\rCountdown: {i}', end=" ", flush=True)
        time.sleep(1)
    print()


def reinit():
    raise NotImplementedError


def handle_dev(args: argparse.Namespace):
    cmd = args.cmd

    print("args:", args)
    raise NotImplementedError


def arg_aliases():
    aa = ArgAlias()
    aa.alias("q" , "queue")

    aa.alias("c" , "company")
    aa.alias("cl", ["company", "list"])
    aa.alias("ca", ["company", "authors"])
    aa.alias("cr", ["company", "reviews"])
    aa.alias("crn", ["company", "reviews-net"])
    aa.alias("crd", ["company", "reviews-data"])
    aa.alias("cf", ["company", "fetch"])
    aa.alias("cw", ["company", "wipe"])
    aa.alias("ct", ["company", "trace"])


    aa.alias("a", "author")
    aa.alias("af", ["author", "fetch"])
    aa.alias("ar", ["author", "reviews"])
    aa.alias("arn", ["author", "reviews-net"])
    aa.alias("ard", ["author", "reviews-data"])
    aa.alias("arw", ["author", "reviews-wipe"])
    aa.alias("af", ["author", "fetch"])
    aa.alias("aw", ["author", "wipe"])


    aa.alias("m", "metrics")
    aa.alias(["ml", "mls"], ["metrics", "list"])
    aa.alias("mw", ["metrics", "wipe"])
    aa.alias("mr", ["metrics", "run"])
    aa.alias("mt", ["metrics", "top"])
    
    aa.alias("mar", ["metrics", "arun"])
    aa.alias("maw", ["metrics", "awipe"])
    aa.alias(["mal", "mals"], ["metrics", "alist"])



    aa.alias("p", "percentiles")
    aa.alias("pl", ["percentiles", "list"])
    aa.alias("pr", ["percentiles", "run"])
    aa.alias("pw", ["percentiles", "wipe"])

    aa.alias("r", "reports")
    aa.alias("rc", ["reports", "city"])
    aa.alias("rml", ["reports", "metriclist"])
    aa.alias("rf", ["reports", "fraud"])
    aa.alias("rr", ["reports", "region"])

    aa.alias("x", "extra")
    aa.alias("xta", ["extra", "top-author"])

    aa.skip_flags()
    aa.parse()


def byid(object_id: str):
    url = f'https://catalog.api.2gis.ru/3.0/items/byid?id={object_id}&key=c7f1a769-c8a5-4636-b14d-d8c987808a12&locale=ru_RU&fields=items.locale,items.flags,items.search_attributes.detection_type,search_attributes,items.adm_div,items.city_alias,items.region_id,items.segment_id,items.reviews,items.point,request_type,context_rubrics,query_context,items.links,items.name_ex,items.name_back,items.org,items.group,items.dates,items.external_content,items.contact_groups,items.comment,items.ads.options,items.email_for_sending.allowed,items.stat,items.stop_factors,items.description,items.geometry.centroid,items.geometry.selection,items.geometry.style,items.timezone_offset,items.context,items.level_count,items.address,items.is_paid,items.access,items.access_comment,items.for_trucks,items.is_incentive,items.paving_type,items.capacity,items.schedule,items.schedule_special,items.floors,items.floor_id,items.floor_plans,ad,items.rubrics,items.routes,items.platforms,items.directions,items.barrier,items.reply_rate,items.purpose,items.purpose_code,items.attribute_groups,items.route_logo,items.has_goods,items.has_apartments_info,items.has_pinned_goods,items.has_realty,items.has_otello_stories,items.has_exchange,items.has_payments,items.has_dynamic_congestion,items.is_promoted,items.congestion,items.delivery,items.order_with_cart,search_type,items.has_discount,items.metarubrics,items.detailed_subtype,items.temporary_unavailable_atm_services,items.poi_category,items.has_ads_model,items.vacancies,items.structure_info.material,items.structure_info.floor_type,items.structure_info.gas_type,items.structure_info.year_of_construction,items.structure_info.elevators_count,items.structure_info.is_in_emergency_state,items.structure_info.project_type&viewpoint1=82.883354,54.994857&viewpoint2=82.935058,54.976885&stat[sid]=cb3394ef-f643-4c01-9418-53c364bf6999&stat[user]=d3cc083e-94f0-43eb-8dff-92568e2b53f7&shv=2025-07-22-13&r=390184698'


app = typer.Typer(add_completion=False,     context_settings={"help_option_names": ["-h", "--help"]})
verbose_option = typer.Option(False, "--verbose", "-v", help="Enable verbose output")

app.add_typer(metrics_app, name="metrics")
app.add_typer(author_app, name="author")
app.add_typer(company_app, name="company")
app.add_typer(percentiles_app, name="percentiles")
app.add_typer(reports_app, name="reports")
app.add_typer(extra_app, name="extra")

@app.callback()
def app_callback(verbose: bool = verbose_option):
    """ Antifraud for 2GIS (dev tool) """    
    loginit(verbose)
    sys.stdout.reconfigure(line_buffering=True)



@app.command(name="shell")
# @click.pass_context
def cmd_shell():

    from sqlalchemy import select, func, text
    from traitlets.config import Config

    cheatsheet = """\
users = dbsession.scalars(select(Author).order_by(Author.public_id).limit(6)).all()
    
for user in dbsession.scalars(select(Author).order_by(Author.public_id).limit(6)): print(user)

res = dbsession.execute(select(Author, Review).join(Author.reviews).where(Author.public_id=='afa4a64202d84389965bb0ee6101844d'))
for author, review in res: print(author, review)

dbsession.scalar(select(func.count()).select_from(Review).where(Review.author_id=='cba00db5672a47b3b1aaca15e9310f75'))    
"""

    cfg = Config()
    cfg.TerminalInteractiveShell.simple_prompt = False  # enable full prompt_toolkit features
    # cfg.TerminalInteractiveShell.editing_mode = 'vi'     # 'vi' or 'emacs'
    cfg.TerminalInteractiveShell.autoindent = True
    cfg.TerminalInteractiveShell.confirm_exit = False


    ns = {

        "select": select,
        "func": func,
        "text": text,

        # "m": __import__("mymodule"),
        "Company": Company,
        "Author": Author,
        "Review": Review,
        "Metric": Metric,
        "MetricPerc": MetricPerc,                
        "resolve_alias": resolve_alias,        
    }


    console = Console()
    syntax = Syntax(cheatsheet, "python", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title="[bold cyan]SQLAlchemy cheatsheet[/]", border_style="cyan"))

    with DBSession() as dbsession:
        ns['dbsession'] = dbsession
        start_ipython(argv=[], user_ns=ns, config=cfg)



@app.command(name="sys")
# @click.pass_context
def cmd_sys():
    """ system diagnostic """
    print("System information\n---")

    print(f"Python: {sys.version}")

    spec = importlib.util.find_spec('antifraud2gis')
    if spec and spec.origin:
        print("Package location:", spec.origin)
    else:
        print("Package not found")

    print(f"HTTPS_PROXY env variable: {os.getenv('HTTPS_PROXY', None)}")
    r = requests.get("https://ipinfo.io/ip", proxies={"https": None, "http": None})
    print(f"Direct IP: {r.text}")

    r = http_session.get("https://ipinfo.io/ip")
    print(f"Session IP: {r.text}")


    with DBSession() as dbsession:
        oid = Company.random_company(dbsession=dbsession) or '4504127908538375'

    print("Random test OID:", oid)
    testurl = f'https://public-api.reviews.2gis.com/2.0/branches/{oid}/reviews?limit=50&fields=meta.providers,meta.branch_rating,meta.branch_reviews_count,meta.total_count,reviews.hiding_reason,reviews.is_verified&without_my_first_review=false&rated=true&sort_by=friends&key={REVIEWS_KEY}&locale=ru_RU'


    try:
        r = requests.get(testurl, proxies={"https": None, "http": None}, timeout=3)
        print(f"Direct HTTP reviews request: {r.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Direct HTTP reviews request error: {e}")
    
    try:
        r = http_session.get(testurl, timeout=3)
        print(f"Session HTTP response code: {r.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Direct HTTP reviews request error: {e}")

    data = r.json()
    print(f"Meta code: {data['meta']['code']}, rating:{data['meta']['branch_rating']} count: {data['meta']['branch_reviews_count']}/{data['meta']['total_count']}")
    print(f"Reviews: {len(data['reviews'])}")


@app.command()
def init():
    check_or_create_db()
    create_test_records()

@app.command()
def rmtest():
    wipe_test_records()


@app.command()
def dump():
    with DBSession() as dbsession:
        limit = 10

        print(f"Users (up to {limit}/{dbsession.query(Author).count()}):")
        print("Nusers:", Author.nusers(dbsession=dbsession))
        for idx, user in enumerate(dbsession.query(Author).limit(limit).all()):
            print(f"{idx}: {user} updated: {user.updated}")
        print()

        print(f"Companies (up to {limit}/{dbsession.query(Company).count()}):")
        for idx, company in enumerate(dbsession.query(Company).limit(limit).all()):
            print(idx, company)
        print()

        print(f"Reviews (up to {limit}/{dbsession.query(Review).count()}):")
        for idx, review in enumerate(dbsession.query(Review).limit(limit).all()):
            print(idx, review)
        print()

        print(f"Metrics (up to {limit}/{dbsession.query(Metric).count()}):")
        for idx, metric in enumerate(dbsession.query(Metric).limit(limit).all()):
            print(idx, metric)
        print()

        print(f"MetricsPerc (up to {limit}/{dbsession.query(Metric).count()}):")
        for idx, metricperc in enumerate(dbsession.query(MetricPerc).limit(limit).all()):
            print(idx, metricperc)
        print()


@app.command()
def submit(
    oid: str = typer.Argument(help="2GIS object_id"),
    force: bool = typer.Option(False, "--force", "-f", help="Force recalculation")):
    """ submit task for worker """

    r = redis.Redis(decode_responses=True)
    tasks = r.lrange(REDIS_TASK_QUEUE_NAME, 0, -1)  # возвращает list of bytes    
    if len(tasks) >= settings.max_queue:
        print(f"Queue is full ({len(tasks)}). Try again later.")
        time.sleep(settings.sleep)
        return

    object_id = resolve_alias(oid)

    if object_id is None:
        print(f"No object_id for {oid}")
        return

    with DBSession() as dbsession:
        # create record in db if needed (to ensure company exists)
        # this is SHORT request
        try:
            _c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=False)
        except AFNoCompany as e:
            print(f"Company {object_id} not found")
            _c = Company.get(object_id=object_id, dbsession=dbsession)
            if _c is None:
                return
            _c.error = str(e)
            dbsession.commit()
            return

    submit_fraud_task(object_id, force=force)
    print(f"Submitted task for {_c} (force: {force})")



@app.command()
def queue(action: str = typer.Argument("show", help="Action: show (default) or reset")):

    print("queue. action:", action)
    r = redis.Redis(decode_responses=True)

    

    if action == "reset":
        print("RESET queue")
        r.delete(REDIS_TASK_QUEUE_NAME)
        r.delete(REDIS_TRUSTED_LIST)
        r.delete(REDIS_UNTRUSTED_LIST)
        for key in r.scan_iter("dramatiq:*"):
            print("  delete", key)
            r.delete(key)            

    wstatus = r.get(REDIS_WORKER_STATUS)
    wstatus_set = r.get(REDIS_WORKER_STATUS_SET)
    if wstatus_set:         
        wstatus_age = int( time.time() - float(wstatus_set))
    else:
        wstatus_age = None
        
    wstarted = r.get(REDIS_WORKER_STARTED)

    if wstarted:
        wuptime = int(time.time() - float(wstarted))
    else:
        wuptime = None
    
    tasks = r.lrange(REDIS_TASK_QUEUE_NAME, 0, -1)  # возвращает list of bytes    
    trusted_len = r.llen(REDIS_TRUSTED_LIST)
    untrusted_len = r.llen(REDIS_UNTRUSTED_LIST)
    dqlen = r.llen(REDIS_DRAMATIQ_QUEUE)

    last_trusted = [json.loads(item) for item in r.lrange(REDIS_TRUSTED_LIST, 0, -1)]
    last_untrusted = [json.loads(item) for item in r.lrange(REDIS_UNTRUSTED_LIST, 0, -1)]

    lastn = 5

    print("Queue report")
    print(f"Worker status: {wstatus} ({wstatus_age} sec ago)")
    print(f"Worker uptime: {wuptime} sec.")
    print(f"Dramatiq queue: {dqlen}")
    tasks_suffix = '...' if len(tasks) > lastn else ''
        
    print(f"Tasks ({len(tasks)}): {' '.join(tasks[:lastn])} {tasks_suffix}")
    print(f"Trusted ({lastn}/{trusted_len}):")
    for c in last_trusted[:lastn]:
        # print_json(data=c)
        print(f"  {c['oid']} {c['title']} ({c['rating']}) {c['score'].get('reason')}")


    print(f"Untrusted ({lastn}/{untrusted_len})")
    for c in last_untrusted[:lastn]:
        # print_json(data=c)
        print(f"  {c['oid']} {c['title']} ({c['rating']}) {c['score'].get('detections')}")





@app.command()
def recreate(table: str = typer.Argument(None, help="Table (class) to recreate")):
    """ re-create table in database (drops data!)"""
    if table is None:
        print("Specify table to recreate (Metric, MetricPerc, Author, Review, Company)")
        return
    # get cls based on table
    cls = globals().get(table, None)
    if cls is None:
        print("No such table/class")
        return
    print("Re-create table:", table, cls)
    countdown(5)
    with DBSession() as dbsession:
        print("Drop...")
        cls.__table__.drop(dbsession.bind, checkfirst=True)
        print("Create...")
        cls.__table__.create(dbsession.bind, checkfirst=True)
        print("Done.")
    

@app.command(name="cust")
# @click.pass_context
def cmd_cust(
    object_id: str = typer.Argument(..., help="2GIS object_id")
):
    """ custom command """

    from ..net.company_reviews import CompanyReviewsIterator
    
    object_id = resolve_alias(object_id)

    cri = CompanyReviewsIterator(object_id=object_id)
    last_dt = None    
    for review in cri:
        # "date_created": "2025-08-26T17:26:19.136724+07:00",
        # created = dateutil.parser.isoparse(review['date_created']).replace(microsecond=0, tzinfo=None)
        # edited = dateutil.parser.isoparse(review['date_edited']).replace(microsecond=0, tzinfo=None) if review.get('date_edited') else None

        date_field = "date_edited" if review.get('date_edited') else "date_created"

        dt = dateutil.parser.isoparse(review[date_field]).replace(microsecond=0, tzinfo=None)

        # print_json(data=review)
        if last_dt:
            print(dt, dt < last_dt)
            if dt > last_dt < dt:
                print("!!! DATE DECREASED !!!")
                raise ValueError("Date decreased")
                # print_json(data=review)

        last_dt = dt


@app.command(name="cust2")
# @click.pass_context
def cmd_cust2(
    public_id: str = typer.Argument(..., help="public_id of author")
):
    """ custom command """

    from ..net.author_reviews import AuthorReviewsIterator
    

    ri = AuthorReviewsIterator(public_id=public_id)
    last_dt = None    
    for review in ri:
        # "date_created": "2025-08-26T17:26:19.136724+07:00",
        # created = dateutil.parser.isoparse(review['date_created']).replace(microsecond=0, tzinfo=None)
        # edited = dateutil.parser.isoparse(review['date_edited']).replace(microsecond=0, tzinfo=None) if review.get('date_edited') else None

        # print_json(data=review)

        # date_field = "date_edited" if review.get('date_edited') else "date_created"
        date_field = "date_edited"

        dt = dateutil.parser.isoparse(review[date_field]).replace(microsecond=0, tzinfo=None)
        dtedited = dateutil.parser.isoparse(review["date_edited"]).replace(microsecond=0, tzinfo=None)

        # print_json(data=review)
        if last_dt:            
            print(dt, dtedited, dt < last_dt)
            if dt > last_dt < dt:
                print("!!! DATE DECREASED !!!")                
                raise ValueError("Date decreased")
                # print_json(data=review)

        last_dt = dt




def main():
    # args = get_args()
    arg_aliases()
    # cl = CompanyList()
    stopfile = Path('~/.af2gis-stop').expanduser()

    app()



