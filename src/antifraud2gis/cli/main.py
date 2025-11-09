#!/usr/bin/env python3

import argparse
import sys
import time
import json
from builtins import print as _print
from datetime import datetime

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
from sqlalchemy import create_engine, select, func, case
from sqlalchemy.orm import Session
import typer

from ..models.company import Company
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
from ..db import DBSession, ScopedDBSession, check_or_create_db


# CLI
# from .status import print_full_status

# from .summary import add_summary_parser, handle_summary, printsummary
#from .company import add_company_parser, handle_company
#from .user import add_user_parser, handle_user
#from .dev import add_dev_parser, handle_dev

last_summary = 0


app = typer.Typer(add_completion=False,     context_settings={"help_option_names": ["-h", "--help"]})
verbose_option = typer.Option(False, "--verbose", "-v", help="Enable verbose output")

@app.callback()
def app_callback(verbose: bool = verbose_option):
    """ Antifraud for 2GIS (dev tool) """
    loginit(verbose=verbose)


def argalias():
    aa = ArgAlias()
    aa.alias("l", "list")
    aa.alias("i", "info")
    aa.alias(["f", "fr"], "fraud")
    aa.alias(["sf","sfr"], "submitfraud")
    aa.alias("cmp", "compare")
    aa.alias(["s", "stat"], "status")
    
    aa.skip_flags()
    aa.parse()

def get_args():



    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=['info', 'list','stop','status', 'fraud', 'compare', 'submitfraud', 'delreport', 'wipe', 'export', 'search', 'aliases'])
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


@app.command()
def status(substatus: str | None = typer.Argument(None, help="db status (None, region, seen)")):
    """ status: database summary """

    now = datetime.now()

    if substatus is None:
        print_full_status()
    elif substatus == 'seen':
        with DBSession() as dbsession:
            stmt = select(
                func.count().label("total"),
                func.sum(case((Company.seen.is_(None), 1), else_=0)).label("unseen"),
                func.sum(case((Company.seen.is_not(None), 1), else_=0)).label("seen")
            )
            total, unseen, seen = dbsession.execute(stmt).one()
            print(f"{now:%Y-%m-%d %H:%M}: Companies {total=} {unseen=} {seen=}")

            stmt = select(
                func.count().label("total"),
                func.sum(case((Author.seen.is_(None), 1), else_=0)).label("unseen"),
                func.sum(case((Author.seen.is_not(None), 1), else_=0)).label("seen")
            )
            total, unseen, seen = dbsession.execute(stmt).one()
            print(f"{now:%Y-%m-%d %H:%M}: Authors {total=} {unseen=} {seen=}")



    elif substatus == 'region':
        with DBSession() as dbsession:
            stmt = select(
                func.count().label("total"),
                func.sum(case((Company.region_id<=0, 1)), else_=0).label("no_region"),
                func.sum(case((Company.region_id>0, 1)), else_=0).label("region")
            )
            total, no_region, region = dbsession.execute(stmt).one()
            print(f"{now:%Y-%m-%d %H:%M}: {total=} {no_region=} {region=}")
    else:
        print(f"Sorry, do not know substatus {substatus!r}", file=sys.stderr)

def print_full_status():

    from ..models.review import Review
    from ..models.metric import Metric

    with DBSession() as dbsession:
        print("Authors:", Author.nusers(dbsession=dbsession))
        print(f"Companies known: {dbsession.query(Company).count()} loaded: {dbsession.query(Company).filter(Company.updated_at).count():,} metrics: {dbsession.query(Company).filter(Company.metrics_calculated).count():,}")

        count_neg1 = dbsession.scalar(
            select(func.count()).select_from(Company).where(Company.region_id == -1)
        )

        count_other = dbsession.scalar(
            select(func.count()).select_from(Company).where(Company.region_id != -1)
        )

        print(f"Regions: {count_other} defined / {count_neg1} undefined")

        print(f"Reviews: {dbsession.query(Review).count()}")
        print(f"Metrics: {dbsession.query(Metric).count()}")



@app.command(name="aliases")
def cmd_aliases():
    """ list built-in aliases for companies """
    for oid, alias_rec in aliases.items():
        remark = alias_rec.get('remark', '')
        remark = f'({remark})' if remark else ''

        print(f"{oid} = {alias_rec['alias']} {remark}")

@app.command()
def info(oid: str):
    """ info about company """
    with DBSession() as dbsession:
        object_id = resolve_alias(oid)
        assert object_id is not None
        try:
            c = Company.get(object_id=object_id, dbsession=dbsession)
            if c is None:
                print("Not found company locally, loading from network")
                c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=False)
        except (AFNoCompany, AFNoTitle) as e:
            print(f"Company {oid} not found: {e}")
            return
        c = dbsession.merge(c)
        print(c.info())


@app.command()
def search(
    query: str,    
    brief: bool = typer.Option(False, "--brief", "-b", help="Show only object_id"),
    summary: bool = typer.Option(False, "--sum", help="Show summary"),    
):
    """
    Search companies by title (partial match), optionally filter by city.
    Excludes companies with an error field set.
    """


    with DBSession() as session:
        results = Company.search(session, query=query)
        found = 0
        for c in results:
            found +=1
            # typer.echo(c.object_id if brief else f"- {c.title} ({c.city}) @ {c.address or 'N/A'}")
            print(c.object_id if brief else c)

        if summary:
            print(f"# Found {found} companies")
            raise typer.Exit(1)





@app.command()
def fraud(oid: str,
        explain: bool = typer.Option(False, "--explain", "-e", help="Show explanation"),
        force: bool = typer.Option(False, "--force", "-f", help="Force recalculation")):
    
    """ fraud detection """

    check_or_create_db()

    with DBSession() as dbsession:
        object_id = resolve_alias(oid)

        if object_id is None:
            print(f"No such company ({oid})")
            return

        try:
            c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession)
        except (AFNoCompany, AFNoTitle, AFCompanyError) as e:
            print(f"No such company (geo or no 2gis reviews): {type(e).__name__}")
            c = Company.get(object_id=object_id, dbsession=dbsession)
            if c is None:                
                return
            c.error = str(e)
            print("set error:", c.error)
            dbsession.commit()            
            return

        # if args.show:
        #    settings.show_hit_th = args.show

        try:
            detect(c, explain=explain, force=force, dbsession=dbsession)
        except AFReportAlreadyExists as e:
            print(f"Report already exists for {c} and no --force")
        dump_report(str(c.object_id))




def main():
    # args = get_args()

    stopfile = Path('~/.af2gis-stop').expanduser()
    
    argalias()
    app()
    sys.exit(0)

    #
    # UNUSED code below
    #


    dbsession = None

    r = redis.Redis(decode_responses=True)

    check_or_create_db()

    if args.cmd == "stop":
        stopfile.touch()
        print(f"Stopfile {stopfile} created")

    elif args.cmd == "status":
        print_full_status()

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

        object_id=resolve_alias(args.company)
        with DBSession() as dbsession:

            try:
                c = Company.get(object_id=object_id, dbsession=dbsession)
                if c is None:
                    print("Locally loaded C:", c)
                    print(f"Company {args.company} not found in database")
                    c = Company.get_or_fetch(object_id=object_id, dbsession=dbsession, full=False)
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
        

