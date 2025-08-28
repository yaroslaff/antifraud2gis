import pandas as pd
import datetime
from ..settings import settings

from ..db import DBSession, Session
from ..models import Company, Metric


def save_metrics(c: Company, metrics: dict, dbsession: Session):

    print("SAVE METRICS")

    for metric_name, value in metrics.items():

        metric = dbsession.query(Metric).filter_by(company=c, name=metric_name).first()
        if metric:
            metric.value = value
        else:
            metric = Metric(company=c, name=metric_name, value=value)
            dbsession.add(metric)

    c.metrics_calculated = datetime.datetime.now()
    c.metrics_signature = settings.param_fp()
    dbsession.add(c)
    dbsession.commit()






def run_metrics(object_id: str, cdf: pd.DataFrame, adf: pd.DataFrame) -> dict[str, float]:

    metrics = dict()

    metrics["reviews:total"] = len(cdf)

    cdf["author_created"] = pd.to_datetime(cdf["author_created"])
    cdf["created"] = pd.to_datetime(cdf["created"])
    cdf["age"] = (cdf["created"] - cdf["author_created"]).dt.days

    cdf2gis = cdf.loc[cdf["provider"] == "2gis"].copy()
    metrics["reviews:2gis"] = len(cdf2gis)

    metrics["external_total"] = int(len(cdf) - len(cdf2gis))
    metrics["external_ratio"] = int(100 * (len(cdf) - len(cdf2gis)) / len(cdf))


    metrics['mean_age'] = int(cdf2gis.loc[:, "age"].mean())
    metrics['median_age'] = int(cdf2gis.loc[:, "age"].median())
    
    
    rev_count = adf.groupby("author_id").size()

    neighbour_count = adf.groupby("object_id").size()

    neighbour_count = neighbour_count.drop(object_id, errors="ignore")

    metrics['neigh:total'] = len(neighbour_count)
    metrics['neigh:ratio'] = round(len(neighbour_count) / metrics['reviews:2gis'], 2)


    neighbour_count = neighbour_count[neighbour_count >= 2]



    # print("NEIGH count (top)")
    # print(neighbour_count.sort_values(ascending=False).head(10).to_string())

    for oid, hits in neighbour_count.sort_values(ascending=False).head(10).items():
        _c = Company.get_or_fetch(object_id=oid, dbsession=DBSession(), full=False)
        print(f"{hits}: {_c}")

    # metrics['neigh:tophits'] = int(neighbour_count.sort_values(ascending=False).iloc[0])

    if not neighbour_count.empty:
        # could be zero-size sometimes    
        top_neigh = neighbour_count.idxmax()
        top_value = int(neighbour_count.loc[top_neigh])

        metrics['neigh:top:hits'] = top_value
        metrics['neigh:top:hits_ratio'] = round(100 * top_value / metrics['reviews:2gis'], 2)


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

    else:
        metrics['neigh:top:hits'] = 0
        metrics['neigh:top:hits_ratio'] = 0
        metrics['tn:nbr:mean'] = 0
        metrics['tn:nbr:median'] = 0
        metrics['tn:nbr:ratio'] = 0


    # a_nr of review: how many reviews from this authour in dataset
    adf["a_nr"] = adf.groupby("author_id")["id"].transform("count")

    # o_nr of review: how many reviews to this object in this dataset
    adf["o_nr"] = adf.groupby("object_id")["id"].transform("count")


    


    # print("ADF:")
    # print(adf[["author_id", "object_id", "a_nr", "o_nr"]].sort_values("o_nr", ascending=False).head(20))
    # print(adf.columns)


    # metric nbr: average number of o_nr for author (>1 almost always, because for main company o_nr is >1). 
    # This metric shows how versatile and unique an author is, indicating how many reviews they have on companies that are atypical for this audience.
    # lower is better
    nbr = adf.groupby("author_id")["o_nr"].mean()

    metrics['nbr:mean'] = round(nbr.mean(),2)
    metrics['nbr:median'] = round(nbr.median(),2)
    metrics['nbr:ratio'] = round(100 * nbr.median() / metrics['reviews:2gis'],2)

    # R1: ratio of unique reviews (no neighbours) to total reviews
    # not sure if it works
    r1 = adf.groupby("author_id")["o_nr"].apply(lambda x: (x == 1).sum() / len(x))

    metrics['r1:mean'] = round(r1.mean(), 2)
    metrics['r1:median'] = round(r1.median(), 2)

    metrics['rpa:median'] = rev_count.median()
    metrics['rpa:mean'] = round(rev_count.mean(), 1)


    # Zodiac metric
    # For cdf dataframe, make Series of 12 elements based on month of all records author_created
    # I want to know how many authors are born each month
    zodiac = cdf2gis["author_created"].dt.month.value_counts().sort_index().reindex(range(1, 13), fill_value=0)
    
    metrics['zodiac:max'] = int(zodiac.max())
    metrics['zodiac:std'] = round(zodiac.std(), 2)
    metrics['zodiac:cv'] = round(zodiac.std() / zodiac.mean(), 2)

    cdf2gis['author_created_ym'] = cdf2gis['author_created'].dt.strftime('%Y%m')
    
    ym = cdf2gis.groupby('author_created_ym')['author_id'].nunique().sort_values()
    
    metrics['zodiacym:max'] = int(ym.max())
    metrics['zodiacym:std'] = round(ym.std(), 2)
    metrics['zodiacym:cv'] = round(ym.std() / ym.mean(), 2)
    metrics['zodiacym:len'] = len(ym)
    metrics['zodiacym:ratio'] = round(len(ym)/len(cdf2gis), 2)






    return metrics
