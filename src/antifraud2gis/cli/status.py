
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
from sqlalchemy import select, func


def printstatus():
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

