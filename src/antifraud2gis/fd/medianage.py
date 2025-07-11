from collections import Counter
import numpy as np


from .fd import BaseFD
from ..models.author import Author
from ..models.company import Company
from ..models.review import Review
from ..settings import settings
from ..logger import logger

"""
    test companies for medianage (detect): 
    141265770459735
    70000001043693695 
    70000001074538667
"""

class MedianAgeFD(BaseFD):

    def __init__(self, c, explain: bool = False):
        super().__init__(c, explain=explain)
        self.user_ages = list()
        self.records = list()
        self.low_rating = 0
        self.agerate = np.empty((0, 2), dtype=int)
        self.processed = 0

    def feed(self, cr: Review, empty: bool = False):

        if empty:
            return

        author = cr.author

        self.agerate = np.vstack([self.agerate, [cr.author_age, cr.rating]])
        self.records.append(f"{author.public_id} {cr.rating} ({author.name} {cr.created_str} - {author.birthday_str}) = {cr.author_age}")
        self.processed += 1

    def get_score(self):

        if self.processed <= settings.apply_median_userage:
            return self.score

        if len(self.agerate) == 0:
            return self.score
        
        ages = self.agerate[:, 0]
        ratings = self.agerate[:, 1]  
        self.median_age = int(np.median(ages))

        self.young_mask = ages <= self.median_age

        young_ratings = ratings[ages <= self.median_age]
        old_ratings = ratings[ages > self.median_age]

        self.young_rating = round(np.mean(young_ratings), 1)
        self.old_rating = round(np.mean(old_ratings), 1)
        self.rating_diff = round(self.young_rating - self.old_rating, 1)

        self.score['median_user_age'] = self.median_age
        

        if len(young_ratings) >= settings.median_user_age_nusers \
                and self.median_age <= settings.median_user_age \
                and self.rating_diff >= settings.rating_diff:
            self.score['young_rating'] = self.young_rating
            self.score['old_rating'] = self.old_rating
            self.score['median_user_age'] = self.median_age
            self.detection = (f"median_user_age {self.median_age} <= {settings.median_user_age} " \
                                            f"({len(young_ratings)} of {self.agerate.shape[0]}) " \
                                            f"and rating_diff {self.young_rating}-{self.old_rating}={self.rating_diff} >= {settings.rating_diff}")
            self.score['detections'].append(self.detection)
            logger.debug(f"median_user_age {self.median_age} <= {settings.median_user_age} ({len(young_ratings)} of {self.agerate.shape[0]})")

        return self.score
    
    def explain(self, fh):
        print(f"Explanation for median_user_age", file=fh)

        for idx, line in enumerate([x for x, m in zip(self.records, self.young_mask) if m], start=1):
            print(f"{idx} {line}", file=fh)

        print(file=fh)
        print(f"Median age: {self.median_age} >= {settings.median_user_age}", file=fh)
        print(f"Young rating({self.young_rating}) - old rating({self.old_rating}) = {self.rating_diff} (> {settings.rating_diff})", file=fh)
        print(f"Detection: {self.detection}", file=fh)
        print(file=fh)

        return


        for idx, line in enumerate(self.records, start=1):
            print(f'{idx} {line}', file=fh)

        print(f"reviews with low rating: {self.score['ma_low_rating']}", file=fh)
        print(f"ages ({len(self.user_ages)}): {sorted(self.user_ages)}", file=fh)
        print(f"median age: {self.score['median_user_age']}", file=fh)
        print("", file=fh)
