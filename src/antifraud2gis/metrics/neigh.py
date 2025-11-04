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
    
    # could be zero-size sometimes    
    top_neigh = neighbour_count.idxmax()
    top_value = int(neighbour_count.loc[top_neigh])

    metrics['neigh:top:hits'] = top_value
    metrics['neigh:top:hits_ratio'] = round(100 * top_value / reviews2gis, 2)


    tn_authors = adf[adf['object_id'] == top_neigh]['author_id'].unique()

    # same adf but only for top-neighbour authors
    tn_df = adf[adf['author_id'].isin(tn_authors)].copy()

    # a_nr of review: how many reviews from this authour in dataset
    tn_df["a_nr"] = tn_df.groupby("author_id")["id"].transform("count")

    # o_nr of review: how many reviews to this object in this dataset
    tn_df["o_nr"] = tn_df.groupby("object_id")["id"].transform("count")

    tn_nbr = tn_df.groupby("author_id")["o_nr"].mean()
    metrics['tn:nbr:mean'] = round(tn_nbr.mean(),2)
    metrics['tn:nbr:median'] = round(tn_nbr.median(),2)
    metrics['tn:nbr:ratio'] = round(100 * tn_nbr.median() / len(tn_nbr),2)

    # metric nbr: average number of o_nr for author (>1 almost always, because for main company o_nr is >1). 
    # This metric shows how versatile and unique an author is, indicating how many reviews they have on companies that are atypical for this audience.
    # lower is better
    nbr = adf.groupby("author_id")["o_nr"].mean()

    metrics['nbr:mean'] = round(nbr.mean(),2)
    metrics['nbr:median'] = round(nbr.median(),2)
    metrics['nbr:ratio'] = round(100 * nbr.median() / reviews2gis,2)


    return metrics
