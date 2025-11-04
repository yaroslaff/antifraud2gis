import pandas as pd


def intnone(x: float | None) -> int | None:
    if x is None or pd.isna(x):
        return None
    return int(x)


def run_zodiac_metrics(cdf2gis: pd.DataFrame) -> dict:
    metrics = dict()
    # Zodiac metric
    # For cdf dataframe, make Series of 12 elements based on month of all records author_created
    # I want to know how many authors are born each month
    if cdf2gis.empty:
        return metrics

    metrics['mean_age'] = intnone(cdf2gis.loc[:, "age"].mean()) 
    metrics['median_age'] = intnone(cdf2gis.loc[:, "age"].median())



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
