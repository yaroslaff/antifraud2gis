import pandas as pd
import datetime
from ..settings import settings

from ..db import DBSession, Session
from ..models import Company, Metric

from .zodiac import run_zodiac_metrics
from .basic import run_basic_metrics
from .neigh import run_neigh_metrics
from .author import run_author_metrics
from .neigh import Neighbors

# too high value => suspicious
metrics_high = ['private_ratio', 'external_ratio', 'zodiac:ratio', 'neigh:top1ratio', 'neigh:top5ratio']
# too low value => suspicious
metrics_low = ['rpa:mean', 'rpa:median' , 'neigh:ratio']


metrics_all = metrics_high + metrics_low

percentiles_values = [75, 90, 95, 99, 99.9]



def save_metrics(c: Company, metrics: dict, dbsession: Session):

    for metric_name, value in metrics.items():

        metric = dbsession.query(Metric).filter_by(company=c, name=metric_name).first()
        if metric:
            if isinstance(value, (int, float)):
                metric.value = value
            else:
                metric.value = None
                metric.string_value = str(value)
        else:
            if isinstance(value, (int, float)):
                metric = Metric(company=c, region_id=c.region_id, name=metric_name, value=value)
            else:
                # maybe string?
                metric = Metric(company=c, region_id=c.region_id, name=metric_name, value=None, string_value=str(value))
            dbsession.add(metric)

    c.metrics_calculated = datetime.datetime.now()
    c.metrics_signature = settings.param_fp()
    
    ### dbsession.add(c)
    dbsession.commit()


def intnone(x: float | None) -> int | None:
    if x is None or pd.isna(x):
        return None
    return int(x)


def make_df(cdf, adf: pd.DataFrame) -> tuple:


    """
    Prepare dataframes
    cdf2gis - new dataset, reviews to company only from 2gis provider
    

    Fields:
    author_created and created - converted to datetime
    age - age of author (days passed since author account created)
    a_nr - how many reviews from this author in dataset (just author reviews)
    o_nr - how many reviews to this company in dataset (neighbours)    
    """

    # basic convertation first
    cdf["author_created"] = pd.to_datetime(cdf["author_created"])
    cdf["created"] = pd.to_datetime(cdf["created"])

    cdf2gis = cdf.loc[cdf["provider"] == "2gis"].copy()
    cdf2gis["age"] = (cdf2gis["created"] - cdf2gis["author_created"]).dt.days

    # a_nr of review: how many reviews from this authour in dataset
    adf["a_nr"] = adf.groupby("author_id")["id"].transform("count")    

    # o_nr of review: how many reviews to this object in this dataset
    adf["o_nr"] = adf.groupby("object_id")["id"].transform("count")

    return cdf, adf, cdf2gis




def run_metrics(object_id: str, cdf: pd.DataFrame, adf: pd.DataFrame) -> dict[str, float]:

    if(adf.empty):
        return dict(is_empty=1)

    cdf, adf, cdf2gis = make_df(cdf, adf)

    metrics = dict()

    metrics.update(run_basic_metrics(cdf, adf, cdf2gis))

    if cdf.empty or adf.empty or cdf2gis.empty or "is_empty" in metrics:
        return metrics

    metrics.update(run_neigh_metrics(object_id=object_id, reviews2gis=metrics['reviews:2gis'], adf=adf))
    metrics.update(run_author_metrics(adf=adf, cdf2gis=cdf2gis))
    metrics.update(run_zodiac_metrics(cdf2gis=cdf2gis))

    nn = Neighbors(object_id)
    nn.process()
    metrics.update(nn.run_metrics())

    return metrics
