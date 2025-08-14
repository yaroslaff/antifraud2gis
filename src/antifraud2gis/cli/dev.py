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
# , reset_user_pool
from ..models.review import Review
from ..settings import settings
from ..fraud import detect, dump_report
from ..exceptions import AFNoCompany, AFNoTitle, AFCompanyError
from ..aliases import resolve_alias
from .summary import printsummary
from ..tasks import submit_fraud_task, cooldown_queue
from ..const import REDIS_TASK_QUEUE_NAME, REDIS_TRUSTED_LIST, REDIS_UNTRUSTED_LIST, REDIS_WORKER_STATUS, REDIS_WORKER_STATUS_SET, \
                        REDIS_DRAMATIQ_QUEUE, REVIEWS_KEY, \
                        LMDB_MAP_SIZE, REDIS_WORKER_STARTED
from ..logger import logger, loginit
from ..session import http_session
from ..db import DBSession, check_or_create_db
from ..net.company_reviews import CompanyReviewsIterator
from ..net.author_reviews import AuthorReviewsIterator

from .metrics import metrics_app
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
    aa.alias("ca", "company-authors")
    aa.alias("cr", "company-reviews")
    aa.alias("crn", "company-reviews-net")
    aa.alias("crd", "company-reviews-data")
    aa.alias("cf", "company-fetch")

    aa.alias("ar", "author-reviews")
    aa.alias("arn", "author-reviews-net")
    aa.alias("af", "author-fetch")

    aa.alias(["ml", "mls"], ["metrics", "list"])
    aa.alias("mw", ["metrics", "wipe"])


    aa.skip_flags()
    aa.parse()


def byid(object_id: str):
    url = f'https://catalog.api.2gis.ru/3.0/items/byid?id={object_id}&key=c7f1a769-c8a5-4636-b14d-d8c987808a12&locale=ru_RU&fields=items.locale,items.flags,items.search_attributes.detection_type,search_attributes,items.adm_div,items.city_alias,items.region_id,items.segment_id,items.reviews,items.point,request_type,context_rubrics,query_context,items.links,items.name_ex,items.name_back,items.org,items.group,items.dates,items.external_content,items.contact_groups,items.comment,items.ads.options,items.email_for_sending.allowed,items.stat,items.stop_factors,items.description,items.geometry.centroid,items.geometry.selection,items.geometry.style,items.timezone_offset,items.context,items.level_count,items.address,items.is_paid,items.access,items.access_comment,items.for_trucks,items.is_incentive,items.paving_type,items.capacity,items.schedule,items.schedule_special,items.floors,items.floor_id,items.floor_plans,ad,items.rubrics,items.routes,items.platforms,items.directions,items.barrier,items.reply_rate,items.purpose,items.purpose_code,items.attribute_groups,items.route_logo,items.has_goods,items.has_apartments_info,items.has_pinned_goods,items.has_realty,items.has_otello_stories,items.has_exchange,items.has_payments,items.has_dynamic_congestion,items.is_promoted,items.congestion,items.delivery,items.order_with_cart,search_type,items.has_discount,items.metarubrics,items.detailed_subtype,items.temporary_unavailable_atm_services,items.poi_category,items.has_ads_model,items.vacancies,items.structure_info.material,items.structure_info.floor_type,items.structure_info.gas_type,items.structure_info.year_of_construction,items.structure_info.elevators_count,items.structure_info.is_in_emergency_state,items.structure_info.project_type&viewpoint1=82.883354,54.994857&viewpoint2=82.935058,54.976885&stat[sid]=cb3394ef-f643-4c01-9418-53c364bf6999&stat[user]=d3cc083e-94f0-43eb-8dff-92568e2b53f7&shv=2025-07-22-13&r=390184698'


app = typer.Typer(add_completion=False,     context_settings={"help_option_names": ["-h", "--help"]})
verbose_option = typer.Option(False, "--verbose", "-v", help="Enable verbose output")

app.add_typer(metrics_app, name="metrics")


@app.callback()
def app_callback(verbose: bool = verbose_option):
    """ Antifraud for 2GIS (dev tool) """    
    loginit(verbose)


@app.command(name="shell")
# @click.pass_context
def cmd_shell():
    ns = {
        # "m": __import__("mymodule"),
        "Company": Company,
        "resolve_alias": resolve_alias
    }
    start_ipython(argv=[], user_ns=ns)



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
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        # create record in db if needed (to ensure company exists)
        _c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=False)

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



@app.command(name="company-reviews")
def сompany_reviews(oid: str,
        id_only: bool = typer.Option(False, "--id", "-i", help="Only this review")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        c = Company.get(object_id=object_id, dbsession=dbsession)
        for r in c.reviews:
            if id_only:
                print(r.id)
            else:
                print(r)



# crd
@app.command(name="company-reviews-data")
def сompany_reviews_data(oid: str = typer.Argument(..., help="2GIS object_id")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=True)
        data = c.data_reviews()

    print_json(data=data)
    cdf = pd.DataFrame(data)
    print(cdf)
    print("LEN:", len(cdf))


    df = pd.DataFrame()
    for author_id in cdf['author_id'].dropna().unique():
        with DBSession() as dbsession:
            # print(author_id)
            a = Author.get_or_fetch(public_id=author_id, dbsession=dbsession)
            df = pd.concat([df, pd.DataFrame(a.data_reviews())], ignore_index=True)
            print(len(df))

    print(df.to_string())

        # print(len(cdf['author_id'].dropna().unique()))
        # print(cdf['author_id'].nunique())



@app.command(name="company-reviews-net")
def сompany_reviews_net(
    oid: str,
    public_id: str = typer.Argument(None, help="Dump only this review"),
    datestr: str = typer.Option(
        None,
        "-d",
        "--date",
        help="Optional date (YYYY-MM-DD). Defaults to None.")
    ):

    """ get reviews from network and dump it (crn) """

    object_id = resolve_alias(oid)    
    cr = CompanyReviewsIterator(object_id=object_id)
    needle_date = None

    if datestr:
        needle_date = dateutil.parser.parse(datestr).date()

    for r in cr:
        if public_id and r['user']['public_id'] != public_id:
            continue
        if needle_date:
            review_date = dateutil.parser.parse(r['date_created']).date()
            if review_date != needle_date:
                continue
        print_json(data=r)



@app.command(name="company-authors")
def сompany_authors(oid: str):
    with DBSession() as dbsession:
        object_id = resolve_alias(oid)

        c = Company.get(object_id=object_id, dbsession=dbsession)
        print(f"# {c.info(dbsession=dbsession)}")
        for r in c.authors():
            print(r)

@app.command(name="company-fetch")
def сompany_fetch(oid: str, full: bool = typer.Option(False, "--full", help="Fetch full company data")):
    object_id = resolve_alias(oid)
    with DBSession() as dbsession:
        try:
            c = Company.fetch(object_id=object_id, full=full, dbsession=dbsession)
        except AFNoCompany as e:
            logger.error(e)


@app.command(name="author-reviews")
def author_reviews(public_id: str):
    """ show reviews for user """
    with DBSession() as dbsession:
        a = Author.get_or_fetch(public_id=public_id,dbsession=dbsession)
        for r in a.reviews:
            print(r)

@app.command(name="author-reviews-net")
def author_reviews_net(public_id: str, brief: bool = typer.Option(False, "--brief", "-b", help="brief")):
    """ show reviews for user """
    ar = AuthorReviewsIterator(public_id=public_id)
    for r in ar:
        if brief:
            print(f"{dateutil.parser.parse(r['date_created']).date()} {r['object']['id']} ({r['object']['address'].split(',')[0]}) {r['object']['name']} {r['rating']}")  
        else:
            print_json(data=r)

def main():
    # args = get_args()
    arg_aliases()
    # cl = CompanyList()
    stopfile = Path('~/.af2gis-stop').expanduser()

    app()



