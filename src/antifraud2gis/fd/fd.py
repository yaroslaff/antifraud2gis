from enum import Enum

from ..models.author import Author
from ..models.company import Company
from ..models.review import Review
from ..settings import settings

class BaseFD():
    """ Base class for all Fraud Detector classes """
    def __init__(self, c: Company, explain: bool = False):

        self._c = c
        self._explain = explain
        
        self.score = dict()
        self.score['detections'] = list()

    
    def feed(self, rev: Review, empty=False):
        pass

    def get_score(self):
        pass

    def explain(self, fh):
        pass