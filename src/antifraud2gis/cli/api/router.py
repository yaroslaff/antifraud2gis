from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import gzip
import json

from rich import print_json

from ...models.company import Company, CompanyList
from ...exceptions import AFReportNotReady, AFNoCompany, AFNoTitle, AFCompanyError

router = APIRouter(prefix="/api/0.1")

@router.get("/ping")
async def ping():
    return {"message": "pong"}

@router.get("/report/2gis/{oid}", name="api_report", response_class=JSONResponse)
async def report(request: Request, oid: str):
    r = dict()
    r['status'] = None
    r['trusted'] = None
    r['url'] = None

    try:
        c = Company(oid)
    except (AFNoCompany, AFNoTitle, AFCompanyError) as e:
        r['status'] = 'NO'
        return r

    try:
        with gzip.open(c.report_path, "rt") as fh:
            report = json.load(fh)
    except FileNotFoundError:
        r['status'] = 'MISS'        
        r['url'] = str(request.url_for("miss", oid=oid))
        return r

    r['status'] = 'OK'
    r['trusted'] = report['score']['trusted']
    return r
