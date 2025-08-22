import pandas as pd




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

    metrics['median_rpa'] = rev_count.median()
    metrics['mean_rpa'] = round(rev_count.mean(), 1)
    
    
    
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
