from collections import Counter
import numpy as np

from .fd import BaseFD
from ..user import User
from ..company import Company
from ..review import Review
from ..settings import settings

"""
test: 141265769524555
"""

class EmptyUserFD(BaseFD):

    def __init__(self, c, explain: bool = False):
        super().__init__(c, explain=explain)

        self.empty_ratings = list()
        self.non_empty_ratings = list()
        self.records = list()

    def feed(self, cr: Review, empty=False):
        if empty:                        
            self.empty_ratings.append(cr.rating)

            if self._explain:

                if cr.uid is None:
                    self.records.append(f"NONE {cr.created_str} {cr.rating } uid:{cr.uid}")
                else:
                    u = User(cr.uid)
                    u.load()
                    self.records.append(f"EMPTY {cr.created_str} {cr.rating} uid: {cr.uid} {u.name} nr:{u.nreviews()}")

        else:
            self.non_empty_ratings.append(cr.rating)
            u = User(cr.uid)
            u.load()
            self.records.append(f"REAL {cr.created_str} {cr.rating} uid: {cr.uid} {u.name} nr:{u.nreviews()}")
        
    def get_score(self):

        empty_users_ratio = int(100 * len(self.empty_ratings) / ((len(self.empty_ratings) + len(self.non_empty_ratings))))
        empty_users_r = float(np.mean(self.empty_ratings))
        non_empty_users_r = float(np.mean(self.non_empty_ratings))
        
        # self.score['empty-users'] = len(self.empty_ratings)
        # self.score['non-empty-users'] = len(self.non_empty_ratings)
        self.score['empty_user_ratio'] = empty_users_ratio

        if empty_users_ratio >= settings.empty_user and (empty_users_r - non_empty_users_r ) >= settings.empty_user_diff:
            self.score['detections'].append(f'empty_user_ratio {empty_users_ratio}% >= {settings.empty_user}%; ' \
                f'empty rating: {empty_users_r:.1f} - non-empty {non_empty_users_r:.1f} = {(empty_users_r - non_empty_users_r):.1f} >= {settings.empty_user_diff}')
            return self.score

        return self.score
    
    def explain(self, fh):
        print("EXPLAIN empty_user_ratio", file=fh)
        for line in self.records:
            print(line, file=fh)
        print(f"Empty ratings ({len(self.empty_ratings)}): {self.empty_ratings}", file=fh)
        print(f"Not-empty ratings ({len(self.non_empty_ratings)}): {self.non_empty_ratings}", file=fh)
        print("", file=fh)