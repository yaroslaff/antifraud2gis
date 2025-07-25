
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
from ..models.author import Author
from ..models.review import Review
from ..models.company import Company


def printsummary():
    dbsession = DBSession()

    print("Nusers:", Author.nusers(dbsession=dbsession))
    print(f"Companies: {dbsession.query(Company).count()}")
    print(f"Reviews: {dbsession.query(Review).count()}")
