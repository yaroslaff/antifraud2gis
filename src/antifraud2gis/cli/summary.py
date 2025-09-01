
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
from ..models.company import Company
from ..fraud import detect

from ..db import DBSession
from ..settings import settings
from ..models import Author, Review, Company, Metric


def printsummary():
    with DBSession() as dbsession:
        print("Nusers:", Author.nusers(dbsession=dbsession))
        print(f"Companies known: {dbsession.query(Company).count()} loaded: {dbsession.query(Company).filter(Company.updated_at).count():,} metrics: {dbsession.query(Company).filter(Company.metrics_calculated).count():,}")
        print(f"Reviews: {dbsession.query(Review).count()}")
        print(f"Metrics: {dbsession.query(Metric).count()}")

