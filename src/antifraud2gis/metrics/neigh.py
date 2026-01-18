import pandas as pd
from ..db import DBSession
from ..models import Company

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
