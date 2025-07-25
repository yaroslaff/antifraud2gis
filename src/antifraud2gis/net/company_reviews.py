from ..const import REVIEWS_KEY
from ..session import http_session

import requests
import time

class CompanyReviewsIterator:
    def __init__(self, object_id: str):
        self.object_id = object_id
        self.url = f'https://public-api.reviews.2gis.com/2.0/branches/{self.object_id}/reviews?limit=50&fields=meta.providers,meta.branch_rating,meta.branch_reviews_count,meta.total_count,reviews.hiding_reason,reviews.is_verified&without_my_first_review=false&rated=true&sort_by=friends&key={REVIEWS_KEY}&locale=ru_RU'
        self.page = 1
        self.meta = None
        self._reviews = []

    def __iter__(self):
        return self

    def __next__(self):
        if not self._reviews and self.url is not None:
            self._load_next_page()

        if not self._reviews:
            raise StopIteration

        return self._reviews.pop(0)

    def _load_next_page(self):

        r = None
        while r is None:

            try:                    
                r = http_session.get(self.url)
            except requests.RequestException as e:
                print("RequestException", e)
                time.sleep(1)
                

        if r.status_code == 400:
            raise NotImplementedError

        r.raise_for_status()

        data = r.json()

        self.meta = data['meta']

        self._reviews = data['reviews']

        # next page
        self.url = data['meta'].get('next_link')
        # fix url
        if self.url and ':8080' in self.url:
            self.url = self.url.replace(':8080', '')



