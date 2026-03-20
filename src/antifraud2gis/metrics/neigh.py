import pandas as pd
import numpy as np

from typing import Dict

from ..db import DBSession, Session
from ..models.company import Company
from ..models.review import Review
from ..settings import settings
from datetime import datetime, timezone, timedelta



"""
TODO:
Учитывать дату "рождения" авторов (mean/median) в каждом линке
Учинывать оценки A/B в линке
Учитывать как-то разницу дат отзывов на A/B. (боты часто в короткое время набивают оценки)
"""

class Neighbor:
    b_oid: str
    bhits: int
    bsum_rate: int
    brating: float
    public_ids: set[str]
    long: bool

    def __init__(self, a_oid, b_oid: str):
        self.a_oid = a_oid
        self.b_oid = b_oid
        
        self.ahits = 0
        self.bhits = 0

        self.bsum_rate = 0
        self.asum_rate = 0
        self.brating = 0
        self.arating = 0
        self.public_ids = set()
        self.ages = list()
        self.ages1r = list()

    def b_hit(self, r: Review):

        if r.object_id == self.a_oid:
            # print("SKIP a_review", r)
            return

        # print(f"M {self.b_oid} add {r}")

        self.bhits += 1
        self.bsum_rate += r.rating

        self.brating = self.bsum_rate / self.bhits if self.bhits > 0 else 0
        self.public_ids.add(r.author_id)

        age = (r.created - r.author.created).days
        age1r = (r.created - r.author.first_review()).days

        self.ages.append(age)
        self.ages1r.append(age1r)

    def a_hit(self, r: Review):
        """ hit to company A (not this B), other part of relation """
        self.asum_rate += r.rating
        self.ahits += 1

    def __repr__(self) -> str:
        return f'{self.b_oid}: hits={self.bhits} ({len(self.public_ids)} authors) avg_rate={self.brating:.2f} age: {np.median(self.ages):}/{np.mean(self.ages):.1f} '

    def calculate(self, dbsession: Session):
        # calc params after all reviews are processed
        self.b_age_mean = np.mean(self.ages)
        self.b_age_median = np.median(self.ages)

        self.b_age1r_mean = np.mean(self.ages1r)
        self.b_age1r_median = np.median(self.ages1r)

        self.ac = Company.get_or_fetch(self.a_oid, dbsession=dbsession, full=False)

        self.bc = Company.get_or_fetch(self.b_oid, dbsession=dbsession, full=False)
        
        self.long = self.ac.region_id != self.bc.region_id


    def dumps(self, dbsession) -> str:
        longtag = "[LONG]" if self.long else ""
        return f'{self.b_oid} {self.bc.title} ({self.bc.city} r{self.bc.region_id} {longtag}): hits={self.bhits} ({len(self.public_ids)} authors) avg_rate={self.brating:.2f} age: {np.median(self.ages):}/{np.mean(self.ages):.1f} '


class Neighbors:
    neighbors: dict[str, Neighbor]
    a_oid: str
    authors: set
    nreviews: int # only b reviews

    def __init__(self, a_oid: str):
        self.a_oid = a_oid
        self.neighbors = dict()
        self.nreviews = 0
        self.authors = set()

    def b_hit(self, r: Review):

        if r.object_id == self.a_oid:
            print("!!! SKIP a_review", r)
            assert False, "b_hit should not process a_reviews"
            

        if r.object_id not in self.neighbors:
            self.neighbors[r.object_id] = Neighbor(a_oid=self.a_oid, b_oid=r.object_id)
        self.neighbors[r.object_id].b_hit(r=r)
        self.nreviews += 1
    
    def a_hit(self, r: Review):
        self.authors.add(r.author_id)
        for n in self.neighbors.values():
            n.a_hit(r)

    def calculate(self, dbsession: Session):
        for n in self.neighbors.values():
            n.calculate(dbsession=dbsession)

    def topneighbors(self, minhits: int = 10):
        for n in sorted(self.neighbors.values(), key=lambda x: x.bhits, reverse=True):
            if n.bhits >= minhits:
                yield n

    def process(self):

        assert self.a_oid not in self.neighbors, "a_oid should not be in neighbors"

        with DBSession() as dbsession:

            days = settings.max_review_age
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)


            author_ids = (
                dbsession.query(Review.author_id)
                .filter(Review.object_id == self.a_oid, Review.created >= cutoff)
                .distinct()
                .all()
            )

            author_ids = [a[0] for a in author_ids]
            print(f'{len(author_ids)} authors')

            reviews = (
                dbsession.query(Review)
                .join(Company, Review.object_id == Company.object_id)
                .filter(
                    Review.author_id.in_(author_ids),
                    Company.error.is_(None),
                    Review.created >= cutoff
                )
            )

            print("processing reviews")

            assert self.a_oid not in self.neighbors, "a_oid should not be in neighbors"

            a_reviews = list()
            for idx, r in enumerate(reviews):
                # print(idx, r)

                if r.object_id == self.a_oid:
                    # self.a_hit(r=r)
                    a_reviews.append(r)
                    pass
                else:
                    self.b_hit(r=r)

            assert self.a_oid not in self.neighbors, "a_oid should not be in neighbors"


            print("processing a_reviews")
            for r in a_reviews:                
                self.a_hit(r=r)
                assert self.a_oid not in self.neighbors, "a_oid should not be in neighbors"


            print(f"loaded {idx} reviews")

        assert self.a_oid not in self.neighbors, "a_oid should not be in neighbors"

        print("calculate")
        self.calculate(dbsession=dbsession)

        assert self.a_oid not in self.neighbors, "a_oid should not be in neighbors"


        return

        with DBSession() as dbsession:
            c = Company.get(object_id=self.a_oid, dbsession=dbsession)
            for r in c.fresh_reviews(dbsession=dbsession, provider="2gis"):
                for ar in r.author.fresh_reviews(dbsession=dbsession):
                    if ar.company.error:
                        # print("ERR", ar.company)
                        continue
                    self.b_hit(ar)

            for r in c.fresh_reviews(dbsession=dbsession, provider="2gis"):
                self.a_hit(r=r)
            
            self.calculate(dbsession=dbsession)

    def summary(self):
        print(f"Summary for {self.a_oid}\n---")
        print(f"nreviews: {self.nreviews}")
        print(f"nauthors: {len(self.authors)}")
    

    def run_metrics(self) -> Dict[str, int | float | str ]:
        metrics = dict()
        metrics['neigh:total'] = len(self.neighbors)

        topn = next(self.topneighbors())

        metrics['neigh:topnhits'] = len(topn.public_ids) if topn else 0
        metrics['neigh:authors'] = len(self.authors)
        metrics['neigh:topnhits_ratio'] = round(100 * len(topn.public_ids) / len(self.authors), 2) if topn and self.nreviews > 0 else 0
        return metrics

def run_neigh_metrics(object_id: str, reviews2gis: int, adf: pd.DataFrame) -> dict:


    """
    Neighbour statistics

    neigh:total - number of neighbours (target not counted)
    neigh:ratio - ratio of neigh:total/reviews2gis
    """


    metrics = dict()

    neighbour_count = adf.groupby("object_id").size()
    neighbour_count = neighbour_count.drop(object_id, errors="ignore")
    metrics['neigh:total'] = len(neighbour_count)
    metrics['neigh:ratio'] = round(len(neighbour_count) / reviews2gis, 2)

    neighbour_count = neighbour_count[neighbour_count >= 2]

    for oid, hits in neighbour_count.sort_values(ascending=False).head(10).items():
        with DBSession() as dbsession:
            _c = Company.get_or_fetch(object_id=oid, dbsession=dbsession, full=False)   
            print(f"{hits} hits: {_c}")

    # metrics['neigh:tophits'] = int(neighbour_count.sort_values(ascending=False).iloc[0])

    if neighbour_count.empty:
        return metrics

    return metrics
