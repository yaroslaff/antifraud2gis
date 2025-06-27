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

from ..company import CompanyList, Company
from ..user import User, reset_user_pool
from ..review import Review
from ..settings import settings
from ..fraud import detect, dump_report
from ..exceptions import AFNoCompany, AFNoTitle, AFCompanyError
from ..aliases import aliases
from .summary import printsummary
from ..tasks import submit_fraud_task, cooldown_queue
from ..const import REDIS_TASK_QUEUE_NAME, REDIS_TRUSTED_LIST, REDIS_UNTRUSTED_LIST, REDIS_WORKER_STATUS, REDIS_WORKER_STATUS_SET, \
                        REDIS_DRAMATIQ_QUEUE, REVIEWS_KEY, \
                        LMDB_MAP_SIZE, REDIS_WORKER_STARTED
from ..logger import logger
from ..session import session
from ..utils import random_company
from ..companydb import update_company, check_by_oid, get_by_oid, dbsearch, dbtruncate, make_connection
from ..db import db
from ..dbsession import get_db_session

def countdown(n=5):
    for i in range(n, 0, -1):
        print(f'\rCountdown: {i}', end=" ", flush=True)
        time.sleep(1)
    print()


def reinit(cl: CompanyList):

    for path in [ settings.storage, settings.company_storage, settings.user_storage]:
        if not path.exists():
            print(f"Create {path}")
            path.mkdir()

    
    deleted_reports = 0
    for c in cl.companies():
        if c.report_path.exists():
            c.report_path.unlink()
            deleted_reports += 1
    print(f"deleted {deleted_reports} old reports")


    for oid, data in aliases.items():
        c = Company(oid)
        c.load_basic_from_network()
        if 'alias' in data:
            c.alias = data['alias']
            print(c)
        if 'tags' in data:
            c.tags = data['tags']
        c.save_basic()


def findnew():

    found = False

    # read random user
    cl = CompanyList()
    files = [f for f in settings.user_storage.iterdir() if f.is_file()]

    while not found:
        uid = random.choice(files).name.split('-')[0]
        u = User(uid)
        for r in u.reviews():
            print(r)
            try:
                c = cl[r.oid]
                print("Exist:", c)
            except KeyError as e:
                try:
                    c = Company(r.oid)
                except (AFNoCompany, AFNoTitle) as e:
                    continue
                detect(c, cl)
                dump_report(r.oid)
                found = True
    
    printsummary(cl)



def handle_dev(args: argparse.Namespace):
    cmd = args.cmd
    cl = CompanyList()

    total = 0
    errors = 0

    if cmd == "delerror":
        if args.real:
            print("Running in REAL mode")
            if not args.now:
                countdown()
        else:
            print("Running in dry run mode")

        for c in cl.companies():
            total += 1
            if c.error is not None:
                print("deleting", c)
                c.delete()
                errors += 1
        print(f"Total/Err: {total} / {errors} ")

    elif cmd == "reinit":
        if args.real:
            print("Running in REAL mode")
            if not args.now:
                countdown()
            reinit(cl)
        else:
            print("Running in dry run mode")

    elif cmd == "findnew":
        findnew()
    elif cmd == "tmp":
        # check users age for review
        u = User(args.args[0])
        print(u.birthday())



def town_iterator(town: str, nreviews: int):
    for crec in dbsearch(query='', addr=town, nreviews=nreviews, limit=0):
        yield crec


def nreviews_for_oid(r, oid: str, provider:str):
    key = f'af2gis:nreviews:{oid}:{provider}'
    nr = r.get(key)
    if nr is not None:
        return int(nr)
    
    # calculate and save
    c = Company(oid)
    c.load_reviews()
    nr = c.nreviews(provider=provider)
    r.set(key, nr)
    return nr

def do_delkeys(prefix: str):
    r = redis.Redis(decode_responses=True)
    for key in r.scan_iter(f"{prefix}*"):
        print("delete", key)
        r.delete(key)


def do_provider(args, cl: CompanyList):

    redis_conn = redis.Redis(decode_responses=True)

    try:
        min_nprov_th = int(args.args[1])
    except IndexError:
        min_nprov_th = 20

    try:
        th = int(args.args[2])
    except IndexError:
        th = 0


    started = time.time()
    provider = args.args[0]
    print(f"# Analyse companies with {min_nprov_th}+ reviews from {provider}, show companies with more then {th}% reviews from {provider}")

    processed = 0
    provider_ratio = list()
    over_th = 0
    higher = 0
    lower = 0

    all_providers = defaultdict(int)

    for crec in town_iterator(args.town, nreviews=100):

        if crec['oid'] in settings.skip_oids:
            continue
        try:
            crec['provider_nr'] = nreviews_for_oid(redis_conn, crec['oid'], provider=provider)        
            if crec['provider_nr'] < min_nprov_th:
                continue

        except AFCompanyError as e:
            continue

        # here we start processing
        nprov = 0
        total = 0
        ratio = 0 
        prov_rating = list()
        rating = list()
        skipped = 0
        c = Company(crec['oid'])
        c.load_reviews()

        


        for rev in c.reviews():

            total += 1

            all_providers[rev.provider] += 1

            if rev.provider == provider:
                nprov += 1
                prov_rating.append(rev.rating)
            else:
                rating.append(rev.rating)

        # percent of this provider/total
        ratio = int(100*nprov/total)

        # avg rating other providers
        avg = np.mean(rating) if rating else 0
        # avg rating this provider
        avg_prov = np.mean(prov_rating) if prov_rating else 0

        
        if avg_prov > avg:
            higher += 1
            hl_str = "HI"
            if avg_prov > avg + settings.rating_diff:
                hl_str = "HI+"
        else:
            lower += 1
            hl_str = "LO"

        processed += 1

        if ratio > th:
            over_th += 1
            print(f"{processed}: {c.object_id} {c.get_title()} (skip:{skipped}) {hl_str} ({avg:.1f}) {provider}: {nprov} / {total} = {ratio} ({avg_prov:.1f})")
            # print(f"  rating ({len(rating)}): {rating}")
            # print(f"  {provider} rating ({len(prov_rating)}): {prov_rating}")



    print(f"processed {processed} companies in {int(time.time() - started)} sec. providers: {dict(all_providers)}")
    
    if processed:
        print(f"over th ({th}): {over_th} ({100*over_th/processed:.1f}%)")
        
        hilorate = higher/lower if lower else 0
        print(f"hi: {higher} lo: {lower} hi/lo: {hilorate:.2f}")

    return


def get_args():


    aa = ArgAlias()
    aa.alias(["queue"], "q")
    aa.alias(["company-users"], "cu")
    aa.alias(["user-reviews"], "ur")
    
    aa.skip_flags()
    aa.parse()


    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=['company-users', 'users', 'user-reviews', 'company-reviews', 'queue', 'explore', 'provider', 'sys', 'filldb', 'dev', 'convert', 'delkeys', 'dump'])
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
    dbsession = get_db_session()
    limit = 10

    print(f"Users (up to {limit}/{dbsession.query(User).count()}):")
    for idx, user in enumerate(dbsession.query(User).limit(limit).all()):
        print(idx, user)
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

    cmd = args.cmd

    if cmd == "company-users":
        c = cl[args.company]
        print(c)
        c.load_reviews()
        for u in c.users():
            print(u)

    elif cmd == "user-reviews":
        public_id = args.args[0]
        dbsession = get_db_session()
        u = User.get_or_fetch(public_id=public_id,dbsession=dbsession)
        for r in u.reviews:
            print(r)


    elif cmd == "company-reviews":

        c = Company(args.company)
        c.load_reviews()
        for r in c.reviews():
            print(r)


    elif cmd == "users":
        for u in User.users():
            print(u)

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

        r = session.get("https://ipinfo.io/ip")
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
            r = session.get(testurl, timeout=3)
            print(f"Session HTTP response code: {r.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Direct HTTP reviews request error: {e}")


        data = r.json()
        print(f"Meta code: {data['meta']['code']}, rating:{data['meta']['branch_rating']} count: {data['meta']['branch_reviews_count']}/{data['meta']['total_count']}")
        print(f"Reviews: {len(data['reviews'])}")

    elif cmd == "filldb":

        if args.overwrite:
            dbtruncate()

        inserted = 0
        started = time.time()
        for c in cl.companies(oid=args.company, name=args.name, town=args.town, report=args.report, noreport=args.noreport):
                inserted += 1
                print(f"{inserted} add {c.object_id} {c.title}")
                update_company(c.export())
                if inserted % 100 == 0:
                    print(f"+++ Inserted {inserted} companies in {int(time.time() - started)} seconds")

        print(f"Done. Inserted {inserted} records, already exists.")

    elif cmd == "provider":
        do_provider(args, cl)

    elif cmd == "explore":

        if args.town is None:
            print("Need a town to explore")
            return

        town = args.town.lower()
        submitted = 0

        print("total users:", User.nusers())
        
        total_users=User.nusers()

        for idx, u in enumerate(User.users()):
            
            if idx % 1000 == 0:
                print(f"Processed {idx}/{total_users} users")

            cooldown_queue(10)

            for rev in u.reviews():
                if rev.get_town().lower() != town:
                    continue

                if db.is_nocompany(rev.oid):
                    # logger.info(f"Skip nocompany (in db) {rev.oid} {rev.title}")
                    continue

                if not cl.company_exists(rev.oid):
                    cooldown_queue(10)
                    try:
                        c = Company(rev.oid)
                    except (AFNoCompany, AFNoTitle) as e:
                        # logger.info(f"AFNoCompany {rev.oid} {rev.title}")
                        db.add_nocompany(rev.oid)
                        continue

                    logger.info(f"{submitted}: new company {rev.get_town()} {rev.oid} {rev.title}")
                    submit_fraud_task(rev.oid)

                    submitted += 1

                    if submitted % 20 == 0:
                        reset_user_pool()

                if stopfile.exists():
                    logger.info("Stopfile found, exit")
                    stopfile.unlink()
                    return
        else:
            print(f"Finished. Last used: {idx} submitted: {submitted}")

    elif cmd == "dev":
        return
        

    elif cmd == "dump":
        db_dump()        

    elif cmd == "delkeys":
        do_delkeys(args.args[0])
    else:
        print(f"Unknown command {cmd!r}")


