import argparse
import time
import random
import importlib.util
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
# import lmdb

from ..models.company import CompanyList, Company
from ..models.author import Author
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
from ..utils import random_company
from ..companydb import update_company, check_by_oid, get_by_oid, dbsearch, dbtruncate, make_connection
from ..db import db
from ..dbsession import DBSession

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


def get_args():


    aa = ArgAlias()
    aa.alias(["queue"], "q")
    aa.alias(["company-authors"], "ca")
    aa.alias(["company-reviews"], "cr")
    aa.alias(["company-fetch"], "cf")

    aa.alias(["author-reviews"], "ar")
    aa.alias(["author-fetch"], "af")
    
    aa.skip_flags()
    aa.parse()


    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=['company-authors', 'authors', 'author-reviews', 'company-reviews', 'company-fetch', 'author-fetch', 'queue', 'sys', 'dev', 'dump'])
    parser.add_argument("-v", "--verbose", default=False, action='store_true')
    parser.add_argument("--full", default=False, action='store_true')
    parser.add_argument("args", nargs='*', help='extra args')

    g = parser.add_argument_group('Company selection')
    g.add_argument("-t", "--town", default=None, help="Filter by town")
    g.add_argument("-n", "--name", default=None, help="Filter by name (fnmatch)")
    g.add_argument("-l", "--limit", metavar='N', type=int, help="Limit to N companies")
    g.add_argument("-c", "--company", metavar='OID', help="Company ID")
    g.add_argument("--report", default=None, action='store_true', help="Company has antifraud report")
    g.add_argument("--noreport", default=None, action='store_true', help="Company has NO antifraud report")
    g.add_argument("--really", default=None, action='store_true', help="Really. (flag for dangerous commands like wipe)")
    
    g = parser.add_argument_group('Fraud options')
    g.add_argument("-s", "--show", metavar='N', type=int, help="Show links with N hits")
    g.add_argument("--overwrite", default=None, action='store_true', help="Recalculate even if fraud report exists")

    return parser.parse_args()

def db_dump():
    dbsession = DBSession()
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

def main():
    args = get_args()
    cl = CompanyList()
    stopfile = Path('~/.af2gis-stop').expanduser()

    loginit("DEBUG" if args.verbose else "INFO")

    cmd = args.cmd

    if cmd == "company-authors":
        with DBSession() as dbsession:
            object_id = resolve_alias(args.args[0])

            c = Company.get(object_id=object_id, dbsession=dbsession)
            print(f"# {c.info(dbsession=dbsession)}")
            for r in c.authors():
                print(r)

    elif cmd == "author-reviews":
        public_id = args.args[0]
        with DBSession() as dbsession:
            a = Author.get_or_fetch(public_id=public_id,dbsession=dbsession)
            for r in a.reviews:
                print(r)


    elif cmd == "company-reviews":
        object_id = resolve_alias(args.args[0])
        with DBSession() as dbsession:
            c = Company.get(object_id=object_id, dbsession=dbsession)
            for r in c.reviews:
                print(r)

    elif cmd == "company-fetch":
        object_id = resolve_alias(args.args[0])
        with DBSession() as dbsession:
            c = Company.fetch(object_id=object_id, full=True, dbsession=dbsession)


    elif cmd == "queue":
        r = redis.Redis(decode_responses=True)

        if 'reset' in args.args:
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


    elif cmd == "sys":
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

        if args.args:
            oid = args.args[0]
        else:
            oid = random_company() or '4504127908538375'
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

    elif cmd == "dev":
        handle_dev(args=args)
        return
        
    elif cmd == "dump":
        db_dump()        

    else:
        print(f"Unknown command {cmd!r}")


