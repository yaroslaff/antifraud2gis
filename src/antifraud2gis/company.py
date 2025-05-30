import json
from loguru import logger
import time
import fnmatch
import sys
import gzip
import zlib
import traceback
import numpy as np
import lmdb
import redis
from rich.progress import Progress
from rich import print_json
from rich.pretty import pretty_repr
from requests.exceptions import RequestException
from typing import Generator

from .settings import settings
from .const import DATAFORMAT_VERSION, SLEEPTIME, WSS_THRESHOLD, LOAD_NREVIEWS, REVIEWS_KEY, LMDB_MAP_SIZE
from .user import User, get_user
from .review import Review
from .session import session
from .exceptions import AFNoCompany, AFNoTitle, AFCompanyError, AFCompanyNotFound
from .aliases import resolve_alias
from .statistics import statistics
from .aliases import aliases, resolve_alias
from .db import db
from .companydb import dbsearch

# to avoid circular import
#class RelationDict:
#    pass


class Company:

    relations: 'RelationDict'

    def __init__(self, object_id: str):
        assert object_id is not None


        object_id = resolve_alias(object_id)

        if not object_id.isdigit():
            raise AFNoCompany(f'Not an digital OID {object_id!r}')

        self.object_id = object_id
        self.reviews_path = settings.company_storage / (object_id + '-reviews.json.gz')
        self.basic_path = settings.company_storage / (object_id + '-basic.json.gz')
        self.report_path = settings.company_storage / (object_id + '-report.json.gz')
        self.explain_path = settings.company_storage / (object_id + '-explain.txt.gz')
        self.loaded_from_disk = False

        self._reviews = list()
        
        # basic info
        self.title = None
        self.alias = None
        self.remark = None
        self.address = None

        self.error = None

        self.tags = None

        self.rate = None

        self.total_count_2gis = None
        self.branch_count_2gis = None
        self.branch_rating_2gis = None

        self.frozen = False

        self.trusted = None
        self.detections = list()

        self.load_basic()
        if self.error:
            raise AFCompanyError(f'{self.object_id} ERROR: {self.error}')

        self.relations = None

        if self.title is None:
            try:
                self.update_title()
            except AFCompanyNotFound as e:
                # resolve title by reviews
                self.update_title_by_reviews()



    @staticmethod
    def wipe(object_id: str):
        assert object_id.isdigit()
        # wipe everything for company
        filelist =  [ 
            settings.company_storage / (object_id + '-reviews.json.gz'),
            settings.company_storage / (object_id + '-basic.json.gz'),
            settings.company_storage / (object_id + '-report.json.gz'),
            settings.company_storage / (object_id + '-explain.txt.gz'),
            ]
        
        for f in filelist:
            if f.exists():
                print("unlink", f)
                f.unlink()




    def load_basic(self):
        if not self.load_basic_from_disk():
            self.load_basic_from_network()
            self.save_basic()
        
    def set_tag(self, tag):
        self.tags = tag
        self.save_basic()

    def load_basic_from_disk(self):
        if self.basic_path.exists():
            with gzip.open(self.basic_path, "rt") as f:
                try:
                    _basic = json.load(f)
                except json.JSONDecodeError:
                    print("Cannot parse JSON!")
                    print(self.basic_path)
                    sys.exit(1)

                version = int(_basic.get('version', 0))
                if version != DATAFORMAT_VERSION:
                    logger.debug(f"version mismatch {version} != {DATAFORMAT_VERSION} for {self.object_id}")
                    return False
                self.title = _basic['title']
                self.alias = _basic['alias']
                self.remark = _basic['remark']
                self.address = _basic.get('address')
                self.version = _basic.get('version', 0)
                self.error = _basic.get('error', None)
                self.frozen = _basic.get('frozen', False)
                self.tags = _basic.get('tags', None)
                self.total_count_2gis = _basic.get('total_count_2gis', None)
                self.branch_count_2gis = _basic.get('branch_count_2gis', None)
                self.branch_rating_2gis = _basic.get('branch_rating_2gis', None)
                self.trusted = _basic.get('trusted', None)
                self.detections = _basic.get('detections', list())

                if not self.title:
                    # logger.debug(f"no title for {self.object_id}")
                    pass
                self.loaded_from_disk = True
                return bool(self.title)
        else:
            return False


    def save_basic(self):
        with gzip.open(self.basic_path, 'wt') as f:
            basic = {
                'version': DATAFORMAT_VERSION,
                'title': self.title, 
                'alias': self.alias,
                'remark': self.remark,
                'address': self.address,
                'trusted': self.trusted,
                # 'score': self.score,
                'error': self.error,
                'frozen': self.frozen,
                'total_count_2gis': self.total_count_2gis,
                'branch_count_2gis': self.branch_count_2gis,
                'branch_rating_2gis': self.branch_rating_2gis,
                'detections': self.detections
            }
            if self.tags:
                basic['tags'] = self.tags
            json.dump(basic, f)

            if not self.loaded_from_disk:
                statistics.created_new_companies += 1



    def load_reviews(self, local_only=False):
        if self._reviews:
            return
        
        if self.reviews_path.exists():
            try:
                with gzip.open(self.reviews_path, "rt") as f:
                    # print(f"Load company reviews from {self.reviews_path} mtime: {int(self.reviews_path.stat().st_mtime)} sz: {self.reviews_path.stat().st_size}")
                    self._reviews = json.load(f)
                    self.count_rate()
            except (gzip.BadGzipFile, OSError, zlib.error):
                logger.error(f"Bad gzip file! {self.reviews_path}")
                sys.exit(1)
        else:
            if not local_only:
                self.load_reviews_from_network()
        return len(self._reviews)

    def count_rate(self):
        self.ratings = list()
        for r in self._reviews:
            if r['rating'] is None:
                # 70000001006412601
                # rating could be None e.g. when provider=4sq
                continue
            if r['rating'] is not None:
                self.ratings.append(r['rating'])

        if self.ratings:
            self.rate = round(float(np.mean(self.ratings)), 2)
        return(self.rate)

    def users(self):
        for r in self._reviews:
            uid = r['user']['public_id']
            if uid is None:
                continue
            yield User(uid)

    def users_ids(self):
        for r in self._reviews:
            yield r['user']['public_id']

    def uids(self):
        for r in self._reviews:
            uid = r['user']['public_id']
            if uid is None:
                continue
            yield uid

    def load_users(self, until_resolve=False):
        self.load_reviews()
        # print(f"load users from {len(self._reviews)} reviews")
        with Progress() as progress:
            task = progress.add_task("[cyan]Loading user's reviews...", total=len(self._reviews))

            for idx, r in enumerate(self._reviews):
                progress.update(task, advance=1, description=f"[green]User {idx}")
                upid = r['user']['public_id']

                if upid is None:
                    # print("skip: no public_id", r['user']['name'])
                    continue

                # logger.debug(f"Loading user {r['user']['name']} {upid} ({idx+1}/{len(self._reviews)})")
                user = get_user(upid)
                user.load()
                if until_resolve:
                    try:
                        title, address = Company.resolve_oid(self.object_id)
                    except AFCompanyNotFound:
                        pass
                    else:
                        # print("resolved!", title, address)
                        return

    def load_reviews_from_network(self):
        url = f'https://public-api.reviews.2gis.com/2.0/branches/{self.object_id}/reviews?limit=50&fields=meta.providers,meta.branch_rating,meta.branch_reviews_count,meta.total_count,reviews.hiding_reason,reviews.is_verified&without_my_first_review=false&rated=true&sort_by=friends&key={REVIEWS_KEY}&locale=ru_RU'
        unused_geo = f'https://public-api.reviews.2gis.com/2.0/geo/141373143684284/reviews?limit=50&fields=meta.providers,meta.geo_rating,meta.geo_reviews_count,meta.total_count,reviews.hiding_reason&sort_by=friends&without_my_first_review=false&key={REVIEWS_KEY}&locale=ru_RU'

        # print("LOAD NETWORK REVIEWS", self.object_id)

        page=0
        while url:
            if ':8080' in url:
                logger.debug(f'strip :8080 from {url}')
                url = url.replace(':8080', '')
            logger.debug(f".. load company reviews p{page} for {self}: {url}")
            r = None
            while r is None:

                try:                    
                    r = session.get(url)
                except RequestException as e:
                    print("RequestException", e)
                    time.sleep(1)
            
            #print(r.status_code)
            #print(r)
            #print(r.text)

            if r.status_code == 400:
                print("bad request", url)
                self.save_basic()
                break

            r.raise_for_status()
            data = r.json()

            # branch review may exists, but not total_count
            # 70000001028529798

            if self.total_count_2gis is None:
                self.total_count_2gis = data['meta']['total_count']
                self.branch_count_2gis = data['meta']['branch_reviews_count']
                self.branch_rating_2gis = data['meta']['branch_rating']
                # print(f"Total/Branch reviews count: {self.total_count_2gis}/{self.branch_count_2gis}")


            if self.total_count_2gis == 0 or self.branch_count_2gis == 0:                
                raise AFNoCompany(f"No reviews for {self.object_id}")

            # print(f"{self.object_id} page {page} first: {data['reviews'][0]['date_created']} last: {data['reviews'][-1]['date_created']}")

            self._reviews.extend(data['reviews'])
            url = data['meta'].get('next_link')
            logger.debug(f'next_link: {url}')
            time.sleep(SLEEPTIME)

            if len(self._reviews) >= LOAD_NREVIEWS:
                # print(f"max reviews {len(self._reviews)} reached")
                break

            page+=1
        

        logger.info(f"Company {self.object_id}: loaded from network {len(self._reviews)} reviews")
        # why we were called?
        # print("----------")
        # print("".join(traceback.format_stack(limit=10)))         

        self.count_rate()

        with gzip.open(self.reviews_path, 'wt') as f:
            json.dump(self._reviews, f)

        statistics.total_companies_loaded+=1
        statistics.total_companies_loaded_network+=1

    def risk(self):
        if not self.score:
            return None
        
        if self.score.get('WSS') is None:
            return None

        if self.score['WSS'] > WSS_THRESHOLD:
            return True

        return False


    def __repr__(self):

        if self.error:
            return f'Company({self.object_id} {self.title!r} ERR:{self.error})'
   
        titlestr = f"{self.title!r} [{self.alias}]" if self.alias else repr(self.title)

        tags = " "
        if self.frozen:
            tags += "[FROZEN]"

        if self.trusted is None:
            trusted_line = "?"
        else:
            if self.trusted:
                trusted_line = "TRUSTED"
            else:
                trusted_line = f"RISK ({'+'.join(self.detections)})"

        return f'Company({self.object_id} rate: {self.branch_rating_2gis} {titlestr} addr: {self.address} reviews:{len(self._reviews) if self._reviews else "not loaded"}{tags} {trusted_line})'

    def get_title(self):
        return self.title or self.object_id

    def get_town(self):
        if self.address is None:
            return None
        return self.address.split(',')[0].replace(u'\xa0', u' ')


    def export(self):
        self.load_reviews()
        data = {
            'oid': self.object_id,
            'title': self.title,
            'address': self.address,
            'town': self.get_town(),
            'searchstr': f"{self.get_town()} {self.title}",
            'rating_2gis': self.branch_rating_2gis,
            'trusted': self.trusted,
            'nreviews': self.nreviews(),
            'detections': ' '.join(self.detections)
        }
        
        if self.trusted is None and self.report_path.exists():
            with gzip.open(self.report_path, 'rt') as f:
                report = json.load(f)
                data['trusted'] = report["score"]['trusted']
                
        return data

    def reviews(self):
        for r in self._reviews:
            rev = Review(r, company=self)
            if rev.age > settings.max_review_age:
                continue
            yield rev

    def nreviews(self, provider = None):

        if provider is None:
            return len(self._reviews)
        # count reviews now myself
        n = 0
        for rev in self._reviews:
            r = Review(rev, company=self)
            if r.age > settings.max_review_age:
                continue

            if provider == '*' or rev['provider'] == provider:
                n += 1

        return n


    def review_from(self, uid: str) -> Review:
        self.load_reviews()
        for r in self._reviews:
            if r['user']['public_id'] == uid:
                user = get_user(uid)
                return Review(r, user=user)

    def update_title_by_reviews(self):
        self.load_reviews()
        self.load_users(until_resolve=True)

        try:
            self.update_title()
        except AFCompanyNotFound:
            logger.debug(f"Broken company {self.object_id} (no reviews or medical)")
            self.error = True
            self.save_basic()

        return

        for r in self._reviews:
            upid = r['user']['public_id']
            if upid is None:
                continue

            user = get_user(upid)
            user.load()
            ci = user.get_company_info(self.object_id)
            if ci is None:
                # print(f"no company info for me {self.object_id}, process next user")
                continue
            else:
                print("QQQQQQQQQQQQQQQQ")
                print_json(data=ci)


          

    def load_basic_from_network(self):
        # print(f"ZZZZZZ company load basic from network: {self.object_id}")
        # print("".join(traceback.format_stack(limit=10)))         

        # print("load_basic", self.object_id)
        # print(self.title, self.address, "err:",self.error)

        self.load_reviews()
        return
    
        # OLD CODE, lmdb do not 
        for idx, r in enumerate(self._reviews):
            upid = r['user']['public_id']
                        
            if upid is None:
                # print("skip: no public_id", r['user']['name'])
                continue

            # logger.debug(f"Loading user {r['user']['name']} {upid} ({idx+1}/{len(self._reviews)})")
            user = get_user(upid)
            user.load()
            ci = user.get_company_info(self.object_id)
            if ci is None:
                # print(f"no company info for me {self.object_id}, process next user")
                continue

            # print(f"found company info for me {self.object_id} in user {user}")
            self.title = ci['name']
            self.address = ci['address']
            return

    @staticmethod
    def resolve_oid(object_id: str):
        """ set self.title/address from user's reviews """
        # env = lmdb.open(settings.lmdb_storage.as_posix(), map_size=LMDB_MAP_SIZE, readonly=True)
        env = lmdb.open(settings.lmdb_storage.as_posix(), readonly=True)

        with env.begin() as txn:
            jdata = txn.get(b"object:" + object_id.encode())
            if jdata:
                data = json.loads(jdata)
                return data['name'], data['address']
            else:
                raise AFCompanyNotFound(f'Company {object_id} not found in LMDB')


    def update_title(self):
        """ set self.title/address from user's reviews """
        self.title, self.address = Company.resolve_oid(self.object_id)

    def delete(self):
        # delete all files about company
        if self.reviews_path.exists():
            self.reviews_path.unlink()
        if self.basic_path.exists():
            self.basic_path.unlink()


    def culture(self):

        whitelisted = [
            '70000001063840471' # Дом книги, СПб
        ]

        if self.object_id in whitelisted:
            return True

        culture_titles = ['храм', 'музей', 'парк']
        title = self.get_title().lower()
        return any(sub in title for sub in culture_titles)

    def report_reliable(self, report: dict):
        if 'detections' in report['score']:
            for detection in report['score']['detections']:
                if detection.startswith('risk_users') and self.culture():
                    return False
                
        return True

class CompanyList():
    path = None
    def __init__(self, path=None):
        self.path = path or settings.company_storage
    
    def __getitem__(self, index):

        assert(self.path)

        basicpath = self.path / f'{index}-basic.json.gz'
        if basicpath.exists():
            # logger.debug(f"Found company {index} by ID")
            return Company(index)
        
        # not found, try by alias
        for oid, rec in aliases.items():
            if rec.get('alias') == index:
                logger.debug(f"Found company {index} by alias")
                return Company(oid)
        raise KeyError(f"Company {index} not found")


    def companies(self, oid=None, name = None, town = None, detection=None, report = None, noreport = None, limit=None) -> Generator[Company, None, None]:
        n = 0

        if oid:
            try:
                c = Company(oid)
            except (AFCompanyError, AFNoCompany):
                # no review 70000001096097346
                return

            if company_match(c, oid=None, name=name, town=town, detection=detection, report=report, noreport=noreport):
                yield c
            return

        for record in dbsearch(query=name, addr=town, detection=detection, limit=limit):
            try:
                c = Company(record['oid'])
            except (AFCompanyError, AFNoCompany):
                continue

            yield c

        return
    

        # Old very slow file-based code
        for idx, f in enumerate(self.path.glob('*-basic.json.gz')):
            company_oid = f.name.split('-')[0]

            try:

                c = Company(company_oid)
            except AFCompanyError as e:
                # do not use such companies
                continue
            # print("created c", c.report_path)
            if company_match(c, oid=oid, name=name, town=town, detection=detection, report=report, noreport=noreport):
                yield c
                n+=1
                if limit and n==limit:
                    return
    

    def company_exists(self, oid):
        basicpath = self.path / f'{oid}-basic.json.gz'
        return basicpath.exists()

    def getdesc(self, oid):
        if self.company_exists(oid):
            return str(Company(oid))
        else:
            return oid

def company_match(c: Company, oid: str, name: str = None, town: str = None, detection=None, report = None, noreport = None):

    if oid and c.object_id != oid:
        return False   

    # print("??", detection)
    # print(c.trusted)

    if detection:
        if detection == "trusted":
            if not c.trusted:
                return False
        elif detection == "untrusted":
            if not c.trusted is False:
                return False
        else:
            if not detection in c.detections:
                return False

    if report:
        if not c.report_path.exists():
            return False

    if noreport:
        if c.report_path.exists():
            return False

    if name:
        name = name.lower()
        cname = c.get_title().lower()
        if not fnmatch.fnmatch(cname, name):
            return False

    if town:                
        # filter by town
        town = town.lower()
        ctown = c.get_town()
        if ctown is None:
            return False
        ctown = ctown.lower()        
        if town != ctown:
            return False
        
        
    # all filters matched
    return True

