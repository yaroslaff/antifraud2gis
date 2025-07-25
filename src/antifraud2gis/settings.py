from pathlib import Path
import os
# import lmdb
from dotenv import load_dotenv
from .const import LMDB_MAP_SIZE

class Settings():
    def __init__(self):
        load_dotenv()

        # algorithm version
        self.algo = 1

        self.storage = Path("~/.af2gis-storage").expanduser()

        self.dburl = "sqlite:///" + str(self.storage / "db.sqlite3")
        self.requests_cache_path = str(self.storage / "cache.sqlite3")
        self.requests_cache_expire = 3600 * 24 * 30
                                            
        self.user_storage = self.storage / "users"
        # self.lmdb_storage = self.storage / "db.lmdb"

        # self.private_user_storage = self.storage / "users" / "_private.json"
        self.company_storage = self.storage / "companies"

        # self.search = self.storage / "search.jsonl"
        # self.searchnew = self.storage / "searchnew.jsonl"
        # self.companydb = self.storage / "companies.db"

        # trust company if <= min_reviews
        self.min_reviews = int(os.getenv('MIN_REVIEWS', '20'))


        # location-specific
        self.lock_city = os.getenv("LOCK_CITY")

        # Relations-specific
        self.risk_hit_th = int(os.getenv('RISK_HIT', '10'))
        self.sametitle_rel = int(os.getenv('SAMETITLE_REL', '3'))
        self.sametitle_ratio = int(os.getenv('SAMETITLE_RATIO', '50'))

        self.happy_long_rel_happy_ratio = int(os.getenv('HAPPY_LONG_REL', '50'))
        self.happy_long_rel = int(os.getenv('HAPPY_LONG_REL', '10'))
        self.happy_long_rel_min_towns = int(os.getenv('HAPPY_LONG_REL_MIN_TOWNS', '3'))

        # median rpu for relations/printing
        self.risk_median_th = int(os.getenv('RISK_MEDIAN', '15'))
        self.show_hit_th = int(os.getenv('SHOW_HIT', '1000'))



        # for relations and median age
        self.risk_highrate_th = float(os.getenv('RISK_HIGHRATE', '4.9'))
        self.risk_user_ratio = float(os.getenv('RISK_USER', '30'))


        # untrusted if EMPTY_USER% (and their rating differs)
        self.empty_user = float(os.getenv('EMPTY_USER', '75'))
        
        # do not run empty-user if less then N users available empty/real
        self.apply_empty_user_min = int(os.getenv('APPLY_EMPTY_USER', '20'))

        self.apply_median_rpu = int(os.getenv('APPLY_MEDIAN_RPU', '20'))
        self.apply_median_userage = int(os.getenv('APPLY_MEDIAN_UA', '20'))

        self.rating_diff = float(os.getenv('RATING_DIFF', '1.2'))

        self.median_rpu = float(os.getenv('MEDIAN_RPU', '5'))
        
        # 2 year old maximum 365
        self.max_review_age = int(os.getenv('MAX_REVIEW_AGE', '730'))

        self.median_user_age = int(os.getenv('MEDIAN_USER_AGE', '30'))
        self.median_user_age_nusers = int(os.getenv('MEDIAN_USER_AGE_NUSERS', '10'))


        # Other system parameters
        self.proxy = os.getenv('HTTPS_PROXY', None)



        # web UI
        self.turnstile_sitekey = os.getenv('TURNSTILE_SITEKEY', None)
        self.turnstile_secret = os.getenv('TURNSTILE_SECRET', None)
        self.gtag = os.getenv('GTAG', None)
        self.motd = os.getenv('MOTD', None)
    
        # Debugging
        self.skip_oids = list(filter(None, os.getenv('SKIP_OIDS', '').split(' ')))
        self.debug_uids = list(filter(None, os.getenv('DEBUG_UIDS', '').split(' ')))

        self.create_directories()

    def create_directories(self):
        if not self.company_storage.exists():
            self.company_storage.mkdir(parents=True)

        if False:
            if not self.user_storage.exists():
                self.user_storage.mkdir(parents=True)
            if not self.lmdb_storage.exists():
                env = lmdb.open(self.lmdb_storage.as_posix(), map_size=LMDB_MAP_SIZE)
                with env.begin(write=True):
                    pass  
                env.close()


    def param_fp(self):
        return f"algo={self.algo} risk_hit={self.risk_hit_th} risk_median_th={self.risk_median_th} risk_highrate_th={self.risk_highrate_th} " \
            f"empty_user={self.empty_user} " \
            f"risk_user_ratio={self.risk_user_ratio} " \
            f"happy_long_rel_th={self.happy_long_rel} happy_long_rel_happy_ratio={self.happy_long_rel_happy_ratio} " \
            f"median_user_age={self.median_user_age} median_rpu={self.median_rpu} " \
            f"sametitle_rel={self.sametitle_rel} sametitle_ratio={self.sametitle_ratio} " \
            f"apply_empty_user_min={self.apply_empty_user_min} apply_median_rpu={self.apply_median_rpu} apply_median_userage={self.apply_median_userage} " \
            f"rating_diff={self.rating_diff} max_review_age={self.max_review_age}"


settings = Settings()