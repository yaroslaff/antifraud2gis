import requests
import requests_cache
from requests_cache import CachedSession

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .settings import settings


# requests_cache.install_cache(settings.requests_cache_path, expire_after=settings.requests_cache_expire)


#if settings.requests_cache_path:
#    print(f"Use cache from {settings.requests_cache_path}")
#    http_session = CachedSession(settings.requests_cache_path, expire_after=settings.requests_cache_expire, backend='sqlite')
#else:
#    http_session = requests.Session()


def create_retry_session(retries=3, backoff=5, status_forcelist=(429, 500, 502, 503, 504)):
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST"]  # or Retry.DEFAULT_ALLOWED_METHODS in newer versions
    )
    adapter = HTTPAdapter(max_retries=retry)
    
    session = requests.Session()
    session = CachedSession(settings.requests_cache_path, expire_after=settings.requests_cache_expire, backend='sqlite')

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    if session.proxies is None and settings.proxy is not None:
        session.proxies = {
            "http": settings.proxy,
            "https": settings.proxy
        }

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })

    return session

http_session = create_retry_session()

