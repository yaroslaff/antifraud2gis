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
    def __init__(self, public_id, message=None):
        self.public_id = public_id
        super().__init__(message or f"Author {public_id} is private")


class AFAuthorUnavailable(AFException):
    # 500 from 2gis. e.g. 412846e8aca14251bb470de8bb4578ac
    # 404 from 2gis. e.g. f88ae363201048c29b77a39a6e2af4b7 or 57be482e014e463dabc7ceea0a58f4fd (aurora)
    pass

class AFCompanyNotFound(AFException):
    # company not found in LMDB 
    pass

class AFNetworkProblem(AFException):
    # any network problem
    pass
