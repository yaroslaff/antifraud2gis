import pandas as pd

def run_author_metrics(adf: pd.DataFrame, cdf2gis: pd.DataFrame) -> dict:
    """
    Author metrics
    r1:mean/median - ratio of unique reviews (only one author) to total
    rpa:mean/median - Reviews per author
    private_ratio - %% of private 2gis profiles
    """

    metrics = dict()
    # R1: ratio of unique reviews (no neighbours) to total reviews
    # not sure if it works
    r1 = adf.groupby("author_id")["o_nr"].apply(lambda x: (x == 1).sum() / len(x))

    metrics['r1:mean'] = round(r1.mean(), 2)
    metrics['r1:median'] = round(r1.median(), 2)

    rev_count = adf.groupby("author_id").size()
    metrics['rpa:median'] = rev_count.median()
    metrics['rpa:mean'] = round(rev_count.mean(), 1)

    metrics['private_ratio'] = int(cdf2gis['private'].mean() * 100)
    return metrics
