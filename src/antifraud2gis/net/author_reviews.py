from ..const import REVIEWS_KEY
from ..session import http_session
from loguru import logger
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from ..session import http_session
from ..exceptions import AFAuthorUnavailable, AFAuthorPrivate
import requests

import time
from rich import print_json

WARN_TIME = 300

class AuthorReviewsIterator:
    def __init__(self, public_id: str, timeout=None):
        self.public_id = public_id
        self.url = f'https://api.auth.2gis.com/public-profile/1.1/user/{self.public_id}/content/feed?page_size=20'
        self.page = 1
        self.meta = None
        self.timeout = timeout
        self._reviews = []
        self.created = time.time()

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            if not self._reviews:
                self._load_next_page()
            if self._reviews:
                r = self._reviews.pop(0)
                if 'review' in r:
                    return r['review']
                else:
                    pass

    def _load_next_page(self):

        if time.time() > self.created + WARN_TIME:
            print(f"ARI for {self.public_id} runs for: {int(time.time() - self.created)}")

        if self.url is None:
            raise StopIteration

        # logger.debug(f"ITER Loading reviews p{self.page} for author {self.public_id} from {self.url}")
        try:
            # print(f"fetch new page p{self.page} for author {self.public_id}")
            if self.page:
                # wait 2s for each next page
                # time.sleep(2)
                pass
            r = http_session.get(self.url, timeout=self.timeout)
        except (requests.exceptions.RetryError, requests.exceptions.ConnectionError) as e:
            logger.error(f"Cannot get reviews for {self.public_id} from {self.url}")
            raise AFAuthorUnavailable
        
        if r.status_code == 403:
            raise AFAuthorPrivate(public_id=self.public_id)

        if r.status_code in [400, 403, 500, 404]:
            logger.warning(f"user {self.public_id} reviews error {r.status_code} url: {self.url}")
            raise StopIteration
        else:
            r.raise_for_status()

        data = r.json()
        
        self._reviews = data['content_feed']

        try:
            token = data['next_page_token']
        except KeyError:
            # logger.debug("no token in response")
            self.url = None
            return

        # logger.debug(f"token: {token}")
        

        # Next Page
        parsed_url = urlparse(self.url)
        query_params = parse_qs(parsed_url.query)
        query_params['page_token'] = token
        new_query = urlencode(query_params, doseq=True)
        self.url = urlunparse(parsed_url._replace(query=new_query))
        self.page+=1
