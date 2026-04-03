import pandas as pd

def run_author_metrics(adf: pd.DataFrame, cdf2gis: pd.DataFrame) -> dict:
    """
    Author metrics
    rpa:mean/median - Reviews per author
    private_ratio - %% of private 2gis profiles
    """

    metrics = dict()
    # R1: ratio of unique reviews (no neighbours) to total reviews
    # not sure if it works

    pubadf = adf[adf['private'] == False]

    rev_count = pubadf.groupby("author_id").size()


    print(cdf2gis)

    metrics['rpa:median'] = rev_count.median()
    metrics['rpa:mean'] = round(rev_count.mean(), 1)

    metrics['private_ratio'] = int(cdf2gis['private'].mean() * 100)

    return metrics
