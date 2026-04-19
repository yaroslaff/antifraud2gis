from .models.company import Company
from .models.metric import Metric
from .models.author import Author

from sqlalchemy.orm import Session
import pandas as pd
from rich import print_json

from .db import DBSession
from .exceptions import AFNoCompany
from .logger import logger
from .metrics import run_metrics, save_metrics, metrics_all, metrics_high, metrics_low, percentiles_values



class CompanyMetric:
    def __init__(self, company: Company, dbsession: Session):
        self.company = company
        self.dbsession = dbsession        
    
    def nmetrics(self) -> int:
        # return number of metrics in database for this company
        return self.dbsession.query(Metric).filter(Metric.company == self.company).count()

    def calculate(self):

        """ make metrics for company c """

        with DBSession() as dbsession:
            c = dbsession.merge(self.company)
            try:
                if c.full_load():
                    # if loaded new reviews, refresh
                    dbsession.refresh(c)

            except AFNoCompany as e:
                logger.error(e)
                c.error = str(e)
                dbsession.commit()
                return
            data = c.data_reviews()
            # print_json(data=data)

            logger.debug(f"Load {len(data)} authors...")
            # company df
            cdf = pd.DataFrame(data)

            if cdf.empty:
                logger.error(f"Empty reviews for {c.object_id}")
                metrics = {"is_empty": 1}
                save_metrics(c, metrics=metrics, dbsession=dbsession)
                return

            adf = make_adf(cdf = cdf, dbsession=dbsession)
            # print(adf.columns.tolist())
            # print(adf[adf['author_id'] == '4ea97e464bb6491c81868eead3aae2dd'][['author_id','object_id', 'rating', 'region_id', 'title', 'top_region_id', 'top_region_ratio']])


            logger.debug("Running metrics...")
            try:
                metrics = run_metrics(c.object_id, cdf, adf)
                save_metrics(c, metrics=metrics, dbsession=dbsession)
            except AFNoCompany as e:
                print(f"AFNoCompany exception: {c.object_id} {e}")
                c.error = f"AFNoCompany: {e}"
                dbsession.commit()            
                logger.error(e)
                return

            # total df    
            print_json(data=metrics)


    def dump(self):
        for m in self.dbsession.query(Metric).filter(Metric.company == self.company):
            print(m)


def make_adf(cdf: pd.DataFrame, dbsession: Session) -> pd.DataFrame:

    def add_region_id(adf: pd.DataFrame) -> pd.DataFrame:
        object_ids = adf['object_id'].dropna().unique().tolist()
        
        rows = dbsession.query(Company.object_id, Company.region_id, Company.title) \
            .filter(Company.object_id.in_(object_ids)) \
            .all()
        
        company_df = pd.DataFrame(rows, columns=['object_id', 'region_id', 'title'])
        company_df['shorttitle'] = company_df['title'].str.split(',').str[0].str.strip()

        adf = adf.merge(company_df, on='object_id', how='left')
        return adf

    def calc_top_region(adf: pd.DataFrame) -> pd.DataFrame:
        region_counts = adf.groupby(['author_id', 'region_id']).size().reset_index(name='count')
        total_counts = adf.groupby('author_id').size().reset_index(name='total')
        
        top_region = region_counts.loc[region_counts.groupby('author_id')['count'].idxmax()] \
            .rename(columns={'region_id': 'top_region_id', 'count': 'top_count'})
        
        top_region = top_region.merge(total_counts, on='author_id')
        top_region['top_region_ratio'] = top_region['top_count'] / top_region['total']
        
        return adf.merge(
            top_region[['author_id', 'top_region_id', 'top_region_ratio']],
            on='author_id',
            how='left'
        )

    def init_adf(cdf: pd.DataFrame) -> pd.DataFrame:
        adf = pd.DataFrame()
        with DBSession() as dbsession2:
            for author_id in cdf['author_id'].dropna().unique():
                a = Author.get_or_fetch(public_id=author_id, dbsession=dbsession2)
                adf = pd.concat(
                    [adf, pd.DataFrame(a.data_reviews(dbsession=dbsession2))],
                    ignore_index=True
                )

        return adf

    adf = init_adf(cdf=cdf)

    adf = add_region_id(adf)
    adf = calc_top_region(adf)

    return adf
        