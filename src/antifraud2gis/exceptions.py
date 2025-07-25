class AFException(Exception):
    pass

class AFReportNotReady(AFException):
    pass

class AFNoCompany(AFException):
    """ fetch could not load this company, no company by this OID in 2GIS """
    pass

class AFReportAlreadyExists(AFException):
    pass

class AFNoTitle(AFException):
    """ cannot get title from reviews (probably reviews from 2gis provider) """
    pass

class AFCompanyError(AFException):
    # constructor will throw it if company has error
    pass

class AFAuthorPrivate(AFException):
    pass

class AFAuthorUnavailable(AFException):
    # 500 from 2gis. e.g. 412846e8aca14251bb470de8bb4578ac
    pass

class AFCompanyNotFound(AFException):
    # company not found in LMDB 
    pass
