from ..const import REVIEWS_KEY
from ..session import http_session

import requests
import time
import json

WARN_TIME = 300

class CompanyReviewsIterator:
    def __init__(self, object_id: str, timeout=None, sleep=None):
        self.object_id = object_id
        self.timeout = timeout
        self.sleep = sleep
        self.url = f'https://public-api.reviews.2gis.com/2.0/branches/{self.object_id}/reviews?limit=50&fields=meta.providers,meta.branch_rating,meta.branch_reviews_count,meta.total_count,reviews.hiding_reason,reviews.is_verified&without_my_first_review=false&rated=true&sort_by=friends&key={REVIEWS_KEY}&locale=ru_RU'
        self.pages_loaded = 0 # increased only for page with 1+ reviews
        self.meta = None
        self._reviews = []
        self.created = time.time()

    def __iter__(self):
        return self

    def __next__(self):
        if not self._reviews and self.url is not None:
            self._load_next_page()

        if not self._reviews:
            raise StopIteration

        return self._reviews.pop(0)

    def _load_next_page(self):

        if self.pages_loaded and self.sleep:
            print(f"sleep {self.sleep} after {self.pages_loaded}")
            time.sleep(self.sleep)

        if time.time() > self.created + WARN_TIME:
            print(f"CRI for {self.object_id} runs for: {int(time.time() - self.created)}")

        r = None
        while r is None:

            try:
                r = http_session.get(self.url, timeout=self.timeout)
            except requests.RequestException as e:
                print("RequestException", e)
                time.sleep(1)

        if r.status_code == 400:
            raise NotImplementedError

        r.raise_for_status()

        data = r.json()

        self.meta = data['meta']

        self._reviews = data['reviews']
        if self._reviews:
            self.pages_loaded += 1

        # next page
        self.url = data['meta'].get('next_link')
        # fix url
        if self.url and ':8080' in self.url:
            self.url = self.url.replace(':8080', '')

    def __repr__(self):
        return f"CompanyReviewsIretator {self.object_id}"