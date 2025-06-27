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

    '70000001035102877': {
        'alias': 'dikul',
        'remark': 'should be error, medical, no back-reviews'
    },

    '5348552838627287': {
        'alias': 'aurora',
    },

    

}

def resolve_alias(alias: str):
    print("Resolve", alias)
    for k, v in aliases.items():
        if v.get('alias') == alias:
            return k
    return alias
        