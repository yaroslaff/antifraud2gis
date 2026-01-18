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

    metrics['zodiac:mean_age'] = intnone(cdf2gis["age"].mean()) 
    metrics['zodiac:median_age'] = intnone(cdf2gis["age"].median())

    cdf2gis = cdf2gis.sort_values("author_created")
    s = pd.Series(1, index=cdf2gis["author_created"])
    counts = s.rolling("30D").sum()
    # находим максимум и соответствующую дату конца окна
    end_time = counts.idxmax()
    max_count = counts.max()
    start_time = end_time - pd.Timedelta(days=30)
    print(f"Max: {max_count} from {start_time.date()} to {end_time.date()}")


    # verify. print everything from start_time to end_time
    peak30d = cdf2gis[(cdf2gis["author_created"] >= start_time) & (cdf2gis["author_created"] <= end_time)]    

    if len(peak30d) == max_count:
        print("Zodiac double_check passed")
    else:
        print("Zodiac double_check FAILED")
    
    assert len(peak30d) == max_count

    metrics['zodiac:nauthors'] = intnone(max_count)
    metrics['zodiac:period_start'] = start_time.strftime("%Y-%m-%d")
    metrics['zodiac:period_end'] = end_time.strftime("%Y-%m-%d")
    metrics['zodiac:ratio'] = round(len(cdf2gis) / max_count,2)
    metrics['zodiac:rating'] = round(peak30d['rating'].mean(), 1)
    
    return metrics
