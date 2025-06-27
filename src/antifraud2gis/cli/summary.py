
import argparse
from rich.console import Console
from rich.table import Table
import time
import sys
import re
# import lmdb
from pathlib import Path

from collections import defaultdict


from ..logger import logger

from ..const import LMDB_MAP_SIZE
from ..company import Company, CompanyList
from ..fraud import detect
from ..db import db
from ..settings import settings
from ..user import User

def add_summary_parser(subparsers):
    sum_parser = subparsers.add_parser("summary", help="Operations with whole database")
    sum_parser.add_argument("cmd", nargs='?', choices=['summary', 'dump', 'table', 'recalc', 'search'])
    sum_parser.add_argument("-f", "--full", default=False, action='store_true')
    sum_parser.add_argument("args", nargs='*')

    return sum_parser


def printsummary(cl: CompanyList, full=False):

    global last_summary

    userpath = settings.user_storage
    total = len(list(cl.companies()))    
    nerr = 0
    ncalc = 0
    nncalc = 0
    for c in cl.companies():
        if c.error:
            nerr += 1
            continue
        if not c.report_path.exists():
            nncalc += 1
            continue
        ncalc += 1

    logger.info(f"SUMMARY Companies: {total=}, {nerr=} {ncalc=} {nncalc=}")
    
    env = lmdb.open(settings.lmdb_storage.as_posix(), readonly=True, map_size=LMDB_MAP_SIZE)
    prefixes = defaultdict(int)
    with env.begin() as txn:
        with txn.cursor() as cur:
            for key, val in cur:
                keyprefix = key.decode().split(':')[0]
                prefixes[keyprefix] += 1
                #print(keyprefix)
    logger.info(f"SUMMARY LMDB prefixes: {dict(prefixes)}")


    if full:
        user_reviews_count = sum(1 for p in userpath.iterdir() if p.is_file())
        logger.info(f"SUMMARY Users with reviews: {user_reviews_count}")
    last_summary = time.time()



def handle_summary(args: argparse.Namespace):
    cmd = args.cmd
    if cmd == 'table':
        cl = CompanyList()
        console = Console()
        table = Table(show_header=True, header_style="bold magenta", title="Scores")
        table.add_column("T", style='red')
        table.add_column("Company name")
        table.add_column("alias")
        table.add_column("NR")
        table.add_column("TwinScore")
        table.add_column("WSS")
        table.add_column("DoubleMedian")
        table.add_column("ND")


        aliased = list()
        for c in cl.companies():
            if c.alias is None:
                continue
            aliased.append(c)

        try:
            sortfield = args.args[0]
        except IndexError:
            sortfield = 'DoubleMedian'
        
        aliased.sort(key=lambda x: x.score.get(sortfield, 0), reverse=True)

        for c in aliased:
            #print(c)
            #print(c.score)

            if not c.score or c.score.get('NR') is None:
                print("NO SCORE for", c)
                detect(c, cl)

                

            NR_str = f"{c.score.get('NR'):.2f}"
            TwinScore_str = f"{c.score.get('TwinScore'):.2f}"
            WSS_str = f"{c.score.get('WSS'):.2f}"
            DoubleMedian_str = f"{c.score.get('DoubleMedian')}"
            NDangerous_str = f"{c.score.get('NDangerous')}"

            # print(NR_str, TwinScore_str, WSS_str, DoubleMedian_str, NDangerous_str)

            table.add_row(c.tags, c.title, c.alias, 
                            NR_str, TwinScore_str, WSS_str, 
                            DoubleMedian_str, NDangerous_str)
        
        console.print(table)
    elif cmd == "dump":
        db.dump()
    elif cmd == "recalc":
        cl = CompanyList()
        for c in cl.companies():
            if c.alias is None:
                continue
            detect(c, cl)
            
    elif cmd == "summary":
        cl = CompanyList()
        printsummary(cl, args.full)

    elif cmd == "search":
        cl = CompanyList()
        if not args.args:
            print("need regex to search")
            sys.exit(1)
        regex = args.args[0]
        for c in cl.companies():            
            if c.title and re.match(regex, c.title, re.IGNORECASE):
                print(c)
            
