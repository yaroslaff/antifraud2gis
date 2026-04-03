from typing import Optional
from sqlalchemy import select, func
from random import randint

from .models.company import Company
from .db import DBSession
from .settings import settings
from .exceptions import AFNoCompany

aliases = {
    '70000001094664808': {
        'alias': 'manty',
        'tags': 'x'
    },
    '70000001086696739': {
        'alias': 'vostochnoe',
        'tags': 'x'
    },

    '141266769572238': {
        'alias': 'gcarenda',
        'tags': 'x'
    },

    '70000001020949692': {
        'alias': 'mario',
        'tags': 'x'
    },

    '4363390420001056': {
        'alias': 'limpopo',
        'tags': 'x'
    },

    '70000001034207247': {
        'alias': 'crystal',
        'tags': 'x'
    },

    '70000001079658519':{
        'alias': 'nashamarka',
        'tags': 'x'
    },

    '70000001027452411':{
        'alias': 'aragvi',
        'tags': 'x'
    },


    '141265769369926': {
        'alias': 'nskg',
    },

    '70000001023347049': {
        'alias': 'madina',
    },
    '70000001029225378': {
        'alias': 'gorodok',
    },
    '141265770941878': {
        'alias': 'schulz',
    },        


    '141265769369691': {
        'alias': 'rshb',
    },        
    '141265771980582': {
        'alias': 'rshb2',
    },        

    '141265769366331': {
        'alias': 'sber',
    },        

    '141265769882893': {
        'alias': 'raif',
    },       
    
    '70000001063580224': {
        'alias': 'simsim',
    },
    '141265769360673': {
        'alias': 'novat',
    },
    '141265770459396': {
        'alias': 'aura',
    },
    '141265769338187': {
        'alias': 'nskzoo',
    },
    '4504127908731515': {
        'alias': 'mskzoo',
    },
    '985690699467625': {
        'alias': 'roev',
    },
    '70000001080281737': {
        'alias': 'tolmachevo',
    },
    '4504127908780545': {
        'alias': 'domodedovo',
    },
    '4504127921282909': {
        'alias': 'sheremetevo',
    },

    '141265770878134': {
        'alias': 'lenta'
    },
    '141265769737695': {
        'alias': 'lenta2'
    },
    '141265769524556': {
        'alias': 'lenta3'
    },
    '141265769640819': {
        'alias': 'auchan'
    },
    '141265770910298': {
        'alias': 'auchan2'
    },
    '141265770140530': {
        'alias': 'auchan3'
    },
    '70000001021506525': {
        'alias': 'hotdogmaster'
    },
    '70000001051303735': {
        'alias': 'hotdogmaster2'
    },
    '70000001017423547': {
        'alias': 'hotdogmaster3'
    },
    '70000001099184992': {
        'alias': 'revolution',
        'remark': 'very few reviews, good for quick tests'
    },
    '70000001057636776': {
        'alias': 'vilada',
        'remark': 'very few reviews'
    },
    '70000001035102877': {
        'alias': 'dikul',
        'remark': 'should be error, medical, no back-reviews'
    },

    '5348552838627287': {
        'alias': 'aurora',
    },
    '70000001083275091': {
        'alias': 'kioskbp',
        'remark': 'no address'
    },
    '70000001057669889': {
        'alias': 'sp',
        'remark': 'sametitle?'
    },
    '141265770417218': {
        'alias': 'suncity'
    }
}


def random_next(purpose: str = "fraud", region_id: str | None = None):
    if purpose == "fraud":
        with DBSession() as dbsession:
            nxt = Company.random_next_company(dbsession=dbsession, city=settings.lock_city, region_id=region_id)
            if nxt:
                return str(nxt.object_id)
            else:
                return None
    elif purpose == "metrics":
        with DBSession() as dbsession:

            base = select(Company).where(
                Company.metrics_calculated.is_(None),
                Company.updated_at.isnot(None),
                Company.error.is_(None)
            )
            count = dbsession.scalar(
                base.with_only_columns(func.count()).order_by(None)
            )
            assert count is not None
            offset = randint(0, min(count, 100))
            c = dbsession.scalars(base.offset(offset=offset).limit(1)).first()
            assert c is not None
            return c.object_id
            



def resolve_alias(alias: str, purpose: str = "fraud", region_id = None) -> str | None:
    for k, v in aliases.items():
        if v.get('alias') == alias:
            return k
        
    # not an alias
    if alias == ":next":
        return random_next(purpose=purpose, region_id = region_id)
    
    else:
        if (len(alias) < 15 or len(alias) > 17) and not alias.startswith('_test'):
            raise AFNoCompany(f"Invalid alias {alias!r}")

    return alias
        