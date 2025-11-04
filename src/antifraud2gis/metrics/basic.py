from ..settings import settings

def run_basic_metrics(cdf, adf, cdf2gis) -> dict:
    """
    Basic statistics

    reviews:company - number of reviews to this (metric's target) company
    reviews:audience - size of adf, all reviews of auditory
    reviews:2gis - only 2gis reviews to target company

    is_empty - 1 if at least one of dataframes is empty

    external_total - number of external reviews (not 2gis) to company
    external_ratio - %% of external reviews to total

    """
    metrics = dict()
    metrics["reviews:company"] = len(cdf)
    metrics["reviews:audience"] = len(adf)

    metrics["reviews:2gis"] = len(cdf2gis)

    if cdf.empty or adf.empty or cdf2gis.empty or len(cdf2gis) < settings.min_reviews:
        metrics["is_empty"] = 1
    else:
        metrics["external_total"] = int(len(cdf) - len(cdf2gis))
        metrics["external_ratio"] = int(100 * (len(cdf) - len(cdf2gis)) / len(cdf))


    return metrics
