import pandas as pd
import numpy as np
from ..db import DBSession, Session
from ..models.company import Company
from ..models.review import Review



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
        print("CALC N", self.b_oid)
        # calc params after all reviews are processed
        self.b_age_mean = np.mean(self.ages)
        self.b_age_median = np.median(self.ages)

        self.b_age1r_mean = np.mean(self.ages1r)
        self.b_age1r_median = np.median(self.ages1r)

        print("make ac", self.a_oid)
        self.ac = Company.get_or_fetch(self.a_oid, dbsession=dbsession, full=False)

        print("make bc", self.b_oid)
        self.bc = Company.get_or_fetch(self.b_oid, dbsession=dbsession, full=False)
        
        self.long = self.ac.region_id != self.bc.region_id


    def dumps(self, dbsession) -> str:
        longtag = "[LONG]" if self.long else ""
        return f'{self.b_oid} {self.bc.title} ({self.bc.city} r{self.bc.region_id} {longtag}): hits={self.bhits} ({len(self.public_ids)} authors) avg_rate={self.brating:.2f} age: {np.median(self.ages):}/{np.mean(self.ages):.1f} '


class Neighbors:
    neighbors: dict[str, Neighbor]
    a_oid: str

    def __init__(self, a_oid: str):
        self.a_oid = a_oid
        self.neighbors = dict()

    def b_hit(self, r: Review):
        if r.object_id not in self.neighbors:
            self.neighbors[r.object_id] = Neighbor(a_oid=self.a_oid, b_oid=r.object_id)
        self.neighbors[r.object_id].b_hit(r=r)
    
    def a_hit(self, r: Review):
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
