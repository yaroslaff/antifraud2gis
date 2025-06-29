class AFException(Exception):
    pass

class AFReportNotReady(AFException):
    pass

class AFNoCompany(AFException):
    pass

class AFReportAlreadyExists(AFException):
    pass

class AFNoTitle(AFException):
    """ cannot get title from reviews (probably reviews from 2gis provider) """
    pass

class AFCompanyError(AFException):
    # constructor will throw it if company has error
    pass

class AFUserPrivate(AFException):
    pass

class AFCompanyNotFound(AFException):
    # company not found in LMDB 
    pass