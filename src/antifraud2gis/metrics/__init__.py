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

    cdf["author_created"] = pd.to_datetime(cdf["author_created"])
    cdf["created"] = pd.to_datetime(cdf["created"])
    cdf["age"] = (cdf["created"] - cdf["author_created"]).dt.days

    cdf2gis = cdf.loc[cdf["provider"] == "2gis"]

    print("mean/median age:", cdf2gis["age"].mean(), cdf2gis["age"].median())

    metrics["external_ratio"] = int(100 * (len(cdf) - len(cdf2gis)) / len(cdf))
    metrics['mean_age'] = int(cdf2gis.loc[:, "age"].mean())
    metrics['median_age'] = int(cdf2gis.loc[:, "age"].median())
    
    
    rev_count = adf.groupby("author_id").size()
    print("REV COUNT")
    print(rev_count)

    neighbour_count = adf.groupby("object_id").size()

    neighbour_count = neighbour_count.drop(object_id, errors="ignore")
    neighbour_count = neighbour_count[neighbour_count >= 2]

    print("NEIGH count")
    print(neighbour_count)



    adf["a_nr"] = adf.groupby("author_id")["id"].transform("count")
    adf["o_nr"] = adf.groupby("object_id")["id"].transform("count")

    print("ADF:")
    print(adf[["author_id", "object_id", "a_nr", "o_nr"]].sort_values("o_nr", ascending=False).head(20))
    print(adf.columns)


    nbr = adf.groupby("author_id")["o_nr"].mean()
    print("=== mean_o_nr")
    print(nbr)
    print(nbr.mean(), nbr.median())

    metrics['nbr:mean'] = round(nbr.mean(),2)
    metrics['nbr:median'] = round(nbr.median(),2)

    # R1: ratio of unique reviews (no neighbours) to total reviews
    r1 = adf.groupby("author_id")["o_nr"].apply(lambda x: (x == 1).sum() / len(x))
    print("== ratio1")
    print(r1)
    print(r1.mean(), r1.median())

    metrics['r1:mean'] = round(r1.mean(),2)
    metrics['r1:median'] = round(r1.median(),2)



    metrics['rpa:median'] = rev_count.median()
    metrics['rpa:mean'] = round(rev_count.mean(), 1)
    
    
    
    per_obj = adf.groupby(["author_id", "object_id"]).size().reset_index(name="cnt")

    res = (
        per_obj.groupby("author_id")
        .agg(
            total_reviews=("cnt", "sum"),
            uniq=("cnt", lambda x: (x == 1).sum())
        )
        .reset_index()
        .assign(uniqp=lambda d: 100 * d["uniq"] / d["total_reviews"])
    )

    print(res.to_string())

    metrics['author_uniq_mean'] = round(res['uniqp'].mean(), 1)
    metrics['author_uniq_median'] = round(res['uniqp'].median(), 1)

    return metrics
