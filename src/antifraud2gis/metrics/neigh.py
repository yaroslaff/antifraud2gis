import pandas as pd
from ..db import DBSession
from ..models import Company


"""
TODO:
Учитывать дату "рождения" авторов (mean/median) в каждом линке
Учинывать оценки A/B в линке
Учитывать как-то разницу дат отзывов на A/B. (боты часто в короткое время набивают оценки)
"""

class Neighbor:
    oid: str
    hits: int
    sum_rate: int
    rating: float
    public_ids: set[str]

    def __init__(self, oid: str, hits: int):
        self.oid = oid
        self.hits = hits
        self.sum_rate = 0
        self.rating = 0
        self.public_ids = set()

    def add_hit(self, public_id, rate):
        self.hits += 1
        self.sum_rate += rate

        self.rating = self.sum_rate / self.hits if self.hits > 0 else 0
        self.public_ids.add(public_id)

    def __repr__(self) -> str:
        return f'{self.oid}: hits={self.hits} ({len(self.public_ids)} authors) avg_rate={self.rating:.2f}'

class Neighbors:
    neighbors: dict[str, Neighbor]

    def __init__(self):
        self.neighbors = dict()

    def hit(self, public_id: str, oid: str, rate: int):
        if oid not in self.neighbors:
            self.neighbors[oid] = Neighbor(oid=oid, hits=0)
        self.neighbors[oid].add_hit(public_id=public_id, rate=rate)
    
    def topneighbors(self, minhits: int = 10):
        for n in sorted(self.neighbors.values(), key=lambda x: x.hits, reverse=True):
            if n.hits >= minhits:
                yield n



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
