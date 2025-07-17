#!/usr/bin/env python3

import argparse
import sys
import time
import json
from builtins import print as _print

from argalias import ArgAlias

from rich import print_json, print
from rich.console import Console
from rich.table import Table
import redis
import gzip
# import lmdb
import os

from pathlib import Path

# import sqlite3

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ..models.company import Company, CompanyList
from ..models.author import Author
from ..fraud import detect, dump_report
from ..compare import compare
from ..tasks import submit_fraud_task, cooldown_queue
from ..logger import loginit, logger, testlogger
from ..const import REDIS_DRAMATIQ_QUEUE
from ..exceptions import AFNoCompany, AFReportNotReady, AFReportAlreadyExists, AFNoTitle, AFCompanyError
from ..settings import settings
from ..statistics import statistics
from ..aliases import resolve_alias
# from ..search import search
from ..aliases import aliases
from ..base import Base
from ..dbsession import DBSession, ScopedDBSession


# CLI
from .summary import printsummary

# from .summary import add_summary_parser, handle_summary, printsummary
#from .company import add_company_parser, handle_company
#from .user import add_user_parser, handle_user
#from .dev import add_dev_parser, handle_dev

last_summary = 0

def get_args():


    aa = ArgAlias()
    aa.alias(["list"], "l")
    aa.alias(["info"], "i")
    aa.alias(["fraud"], "f", "fr")
    aa.alias(["submitfraud"], "sf", "sfr")
    aa.alias(["compare"], "cmp")
    aa.alias(["summary"], "sum", "s")
    
    aa.skip_flags()
    aa.parse()

    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=['info', 'list','stop','summary', 'fraud', 'compare', 'submitfraud', 'delreport', 'wipe', 'export', 'search', 'aliases'])
    parser.add_argument("-v", "--verbose", default=False, action='store_true')
    parser.add_argument("--sleep", type=float, default=None, help='sleep N.M seconds after each processed company')
    parser.add_argument("--fmt", "-f", default="normal", choices=['brief', 'normal', 'full'])
    parser.add_argument("args", nargs='*')

    g = parser.add_argument_group('Company selection')
    g.add_argument("-t", "--town", default=None, help="Filter by town")
    g.add_argument("-n", "--name", default=None, help="Filter by name (fnmatch)")
    g.add_argument("-l", "--limit", metavar='N', type=int, help="Limit to N companies")
    g.add_argument("-d", "--detection", metavar='DETECTION', help="Only with this detection. also trusted, untrusted")
    g.add_argument("-c", "--company", metavar='OID', help="Company ID")
    g.add_argument("--report", default=None, action='store_true', help="Company has antifraud report")
    g.add_argument("--noreport", default=None, action='store_true', help="Company has NO antifraud report")
    g.add_argument("--really", default=None, action='store_true', help="Really. (flag for dangerous commands like wipe)")
    
    g = parser.add_argument_group('Fraud options')
    g.add_argument("-s", "--show", metavar='N', type=int, help="Show links with N hits")
    g.add_argument("--overwrite", default=None, action='store_true', help="Recalculate even if fraud report exists")
    g.add_argument("--explain", default=False, action='store_true', help="Re-run fraud detection with explanation")
    g.add_argument("--maxq", metavar='N', default=None, type=int, help="Sleep if redis queue is over N")

    return parser.parse_args()

def any_filter(args):
    return args.company or args.name or args.town or args.detection or args.report or args.noreport

def createdb():
    print("CREATE db", settings.dburl)

    engine = create_engine(settings.dburl)
    Base.metadata.create_all(engine)
    print("Database initialized.")
    return

def check_or_create_db():

    with DBSession() as dbsession:
        try:
            # n_users = dbsession.query(User).count()
            n_users = Author.nusers(dbsession=dbsession)
        except sqlalchemy.exc.OperationalError as e:
            print("No db file? Create it")
            createdb()
            n_users = dbsession.query(Author).count()


def main():
    args = get_args()

    stopfile = Path('~/.af2gis-stop').expanduser()
    
    dbsession = None

    r = redis.Redis(decode_responses=True)

    cl = CompanyList()

    loginit("DEBUG" if args.verbose else "INFO")

    check_or_create_db()

    if args.cmd == "stop":
        stopfile.touch()
        print(f"Stopfile {stopfile} created")

    elif args.cmd == "summary":
        printsummary()

    elif args.cmd == "aliases":
        for oid, alias_rec in aliases.items():
            remark = alias_rec.get('remark', '')
            remark = f'({remark})' if remark else ''

            print(f"{oid} = {alias_rec['alias']} {remark}")

    elif args.cmd == "compare":
        if len(args.args) != 2:
            print("Need 2 companies")
            sys.exit(1)
        c1 = cl[args.args[0]]
        c2 = cl[args.args[1]]
        compare(c1, c2)

    elif args.cmd == "info":

        with DBSession() as dbsession:

            try:
                c = Company.get_or_fetch(object_id=resolve_alias(args.company), dbsession=dbsession, full=False)
            except (AFNoCompany, AFNoTitle):
                print(f"Company {args.company} not found")
                return
            print(c.info(dbsession=dbsession))
            
    elif args.cmd == "search":
        try:
            needle = args.args[0]
        except IndexError:
            needle=''


        res = dbsearch(needle, detection=args.detection, addr=args.town, limit=args.limit)
        for rec in res:
            print(rec)
        if args.fmt == 'full':
            print("total:", len(res))
        

    elif args.cmd == "fraud":
        with DBSession() as dbsession:
            try:
                c = Company.get_or_fetch(object_id=resolve_alias(args.company), dbsession=dbsession)
            except (AFNoCompany, AFNoTitle, AFCompanyError):
                print("No such company (geo or no 2gis reviews)")
                return

            if args.show:
                settings.show_hit_th = args.show

            try:
                detect(c, cl, explain=args.explain, force=args.overwrite, dbsession=dbsession)
            except AFReportAlreadyExists as e:
                print(f"Report already exists for {c} and no --overwrite")
            dump_report(c.object_id)


    elif args.cmd in ["list", "delreport", "wipe", "submitfraud", "export"]:

        # sanity check
        if args.cmd in ["submitfraud", "fraud", "delreport", "wipe"] and not any_filter(args):
            if len(args.args) == 1:
                args.company = args.args[0]
            else:
                print(f"Need company filter for {args.cmd}")
                sys.exit(1)

        if args.cmd == "wipe" and args.company:
            # do not iterate over list, do not create Company() object, company may be broken. just wipe and forget.
            Company.wipe(args.company)
            return


        # if company is given, create it first (if it's missing)
        if args.company and args.cmd not in ['wipe']:
            try:
                c = Company.get_or_fetch(object_id=resolve_alias(args.company))
            except (AFNoCompany, AFNoTitle, AFCompanyError):
                print("No such company (geo or no 2gis reviews)")
                return

        # PRE PROCESSING
        if args.cmd == "delreport":
            # force args.report
            args.report = True

        total_processed = 0
        effectively_processed = 0


        for c in cl.companies(oid=args.company, name=args.name, town=args.town, detection=args.detection, report=args.report, noreport=args.noreport, limit=args.limit):

            total_processed += 1

            if args.cmd == "list":
                if args.fmt == "brief":
                    _print(c.object_id)
                else:
                    print(c)

            elif args.cmd == "submitfraud":
                if args.maxq:
                    cooldown_queue(args.maxq)
                print("submit fraud request for", c)
                submit_fraud_task(oid = c.object_id, force=args.overwrite)


            elif args.cmd == "delreport":                
                print(f"Delete report for {c}")
                c.report_path.unlink(missing_ok=True)
                c.explain_path.unlink(missing_ok=True)
                c.trusted = None
                c.detections = list()
                c.save_basic()


            elif args.cmd == "wipe":
                if args.really:
                    print(f"wipe {c}")
                    c.wipe(c.object_id)
                else:
                    print("[NOT REALLY] wipe", c)

            elif args.cmd == "export":
                _print(json.dumps(c.export()))
            
            # Stop if stopfile
            if stopfile.exists():
                print("Stopfile found, exit")
                stopfile.unlink()
                sys.exit(0)
        
            # Stop if processed enough
            if args.limit:
                if args.cmd == "fraud":
                    if effectively_processed >= args.limit:
                        print(f"Processed {args.limit} companies, exit")
                        break
                else:
                    if total_processed >= args.limit:
                        print(f"Processed {args.limit} companies, exit")
                        break
            
            if args.sleep:
                time.sleep(args.sleep)


        if args.fmt == 'normal' and args.cmd not in ['export']:
            # POST PROCESSING
            if args.cmd == "fraud":
                print(f'# Fraud reports calculated {effectively_processed}')

            print(f'# Total processed {total_processed} comanies')
            print(statistics)
