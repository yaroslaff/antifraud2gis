from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from pathlib import Path
from dotenv import load_dotenv

import re
import os
import json
import gzip
import importlib.resources
import redis
import markdown
import frontmatter
import requests
import argparse

from dramatiq import get_broker

from rich import print_json

from ..models.company import Company, CompanyList
from ..exceptions import AFReportNotReady, AFNoCompany, AFNoTitle, AFCompanyError
from ..tasks import submit_fraud_task, get_qsize
from ..settings import settings
from ..const import REDIS_TASK_QUEUE_NAME, REDIS_TRUSTED_LIST, REDIS_UNTRUSTED_LIST, REDIS_WORKER_STATUS
# from ..search import search
from ..compare import compare
from ..logger import loginit, testlogger

from .api import router as api_router


app = FastAPI()
app.include_router(api_router.router)


static_path = importlib.resources.files("antifraud2gis") / "static"
templates_path = importlib.resources.files("antifraud2gis") / "templates"

templates = Jinja2Templates(directory=templates_path)

app.mount("/static", StaticFiles(directory=static_path), name="static")

all_jsonl = '/'

r = redis.Redis(decode_responses=True)


class ReportRequest(BaseModel):
    oid: str


def render(request, template_name, context: dict):

    last_trusted = [json.loads(item) for item in r.lrange(REDIS_TRUSTED_LIST, 0, -1)]
    last_untrusted = [json.loads(item) for item in r.lrange(REDIS_UNTRUSTED_LIST, 0, -1)]


    context.update({
        "request": request,
        "settings": settings,
        "trusted": last_trusted,
        "untrusted": last_untrusted,
    })
    return templates.TemplateResponse(template_name, context)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # index page

    if settings.motd and os.path.exists(settings.motd):
        motd_html = markdown.markdown(open(settings.motd).read())
    else:
        motd_html = None

    return render(request, "index.html",
        {
            "request": request,
            "motd": motd_html
        } 
    )


@app.get("/explain/{oid}", response_class=PlainTextResponse)
async def explain(request: Request, oid: str):
    try:
        c = Company(oid)
    except (AFNoCompany, AFNoTitle):
        return RedirectResponse(app.url_path_for("miss", oid=oid))

    if c.explain_path.exists():
        explanation = gzip.open(c.explain_path, "rt").read()
        return PlainTextResponse(content=explanation)


# @app.get("/compare/{oida}/{oidb}", response_class=PlainTextResponse)
async def route_compare(request: Request, oida: str, oidb: str):
    try:
        ca = Company(oida)
    except (AFNoCompany, AFNoTitle):
        return RedirectResponse(app.url_path_for("miss", oid=oida))

    try:
        cb = Company(oidb)
    except (AFNoCompany, AFNoTitle):
        return RedirectResponse(app.url_path_for("miss", oid=oidb))

    cmp_report = f"/tmp/af2gis-cmp-{oida}-{oidb}.txt"

    # rewrite as with
    with open(cmp_report, "w") as fh:
        compare(ca, cb, fh=fh)
    
    # return this file
    data =  open(cmp_report).read()
    os.unlink(cmp_report)
    return PlainTextResponse(content=data)


@app.get("/report/{oid}", name="report", response_class=HTMLResponse)
async def report(request: Request, oid: str):
    try:
        c = Company(oid)
    except (AFNoCompany, AFNoTitle, AFCompanyError) :
        return RedirectResponse(app.url_path_for("miss", oid=oid))
        # raise HTTPException(status_code=404, detail="Company not found")

    try:
        with gzip.open(c.report_path, "rt") as fh:
            report = json.load(fh)
            # print_json(data=report)
            # print(report['relations'][0])


            report_reliable = c.report_reliable(report=report)

            for rel in report['relations']:
                rep_path = settings.company_storage / (rel['oid'] + '-report.json.gz')
                if rep_path.exists():
                    with gzip.open(rep_path, "rt") as fh:
                        rel_report = json.load(fh)
                        rel['trusted'] = rel_report['score']['trusted']
                else:
                    rel['trusted'] = None

            last_trusted = [json.loads(item) for item in r.lrange(REDIS_TRUSTED_LIST, 0, -1)]
            last_untrusted = [json.loads(item) for item in r.lrange(REDIS_UNTRUSTED_LIST, 0, -1)]


            return render(
                request,
                "report.html", {
                    "c": c,
                    "oid": c.object_id,
                    "title": c.title,
                    "score": report['score'],
                    "relations": report['relations'],
                    "report_reliable": report_reliable
                    }
            )

    except FileNotFoundError:
        # return 
        return RedirectResponse(app.url_path_for("miss", oid=oid))
        # raise HTTPException(status_code=404, detail="Report not found")

    return "OK"

@app.get("/miss/{oid}", response_class=HTMLResponse)
async def miss(request: Request, oid: str):

    last_trusted = [json.loads(item) for item in r.lrange(REDIS_TRUSTED_LIST, 0, -1)]
    last_untrusted = [json.loads(item) for item in r.lrange(REDIS_UNTRUSTED_LIST, 0, -1)]

    try:
        c = Company(oid)
        assert c.title is not None

    except (AFNoCompany, AFNoTitle, AFCompanyError, AssertionError) as e:
        return render(
            request,
            "nocompany.html", {
                "request": request, "oid": oid,
                "trusted": last_trusted,
                "untrusted": last_untrusted
            }
        )
        



    return render(
        request,
        "miss.html", {
            "request": request, "title": c.title, "oid": c.object_id,   
            "settings": settings,
            "trusted": last_trusted,
            "untrusted": last_untrusted
        }
    )


@app.post("/submit", response_class=HTMLResponse)
async def submit(request: Request, oid: str = Form(...), force: bool = Form(False), 
                 cf_token: Optional[str] = Form(default=None, alias="cf-turnstile-response"),):

    try:
        c = Company(oid)
    except (AFNoCompany) as e:
        return render(request,
            "nocompany.html", {
                "request": request, "oid": oid,
            }
        )
    
    if settings.turnstile_sitekey:
        # captcha must be sovled!

        if not cf_token:
            print("no captcha response")
            return RedirectResponse(app.url_path_for("report", oid=oid), status_code=303)

        verification_response = requests.post(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data={
                'secret': settings.turnstile_secret,
                'response': cf_token
            }
        )
            
        verification_result = verification_response.json()
        if not verification_result.get('success'):
            # CAPTCHA verification failed
            print(f"CAPTCHA verification failed")
            return RedirectResponse(app.url_path_for("report", oid=oid), status_code=303)


    if c.branch_rating_2gis is None:
        print("re-create company")        
        Company.wipe(oid)
        # c = Company(oid)

    if c.report_path.exists():
        if force:
            # pass
            c.report_path.unlink(missing_ok=True)
            c.explain_path.unlink(missing_ok=True)
        else:
            print("already exists", c)
            return RedirectResponse(app.url_path_for("report", oid=oid), status_code=303)
        
    submit_fraud_task(oid, force=force)
    # r.rpush('af2gis:queue', oid)

    """
    c.report_path.unlink(missing_ok=True)
    c.explain_path.unlink(missing_ok=True)
    c.trusted = None
    c.detections = list()
    c.save_basic()
    """

    return RedirectResponse(app.url_path_for("progress", oid=oid), status_code=303)




@app.get("/search", response_class=HTMLResponse)
async def search_view(request: Request, query: str, detections: str):

    limit = 50
    
    if detections in ["trusted", "untrusted"]:
        detections_arg = detections
    else:
        detections_arg = None

    if query.isdigit() and len(query) >= 12:
        return RedirectResponse(app.url_path_for("report", oid=query), status_code=303)
    else:
        # results = search(query, limit=25)

        results = dbsearch(query, detection=detections_arg, limit=50)

        last_trusted = [json.loads(item) for item in r.lrange(REDIS_TRUSTED_LIST, 0, -1)]
        last_untrusted = [json.loads(item) for item in r.lrange(REDIS_UNTRUSTED_LIST, 0, -1)]

        return render(
            request,
            "search.html", {
                "request": request,
                "query": query,
                "detections": detections,
                "title": f"Поиск: {query}",
                "results": results,
                "trusted": last_trusted,
                "untrusted": last_untrusted,
                "limit": limit
                }
        )



@app.get("/progress/{oid}", response_class=HTMLResponse)
async def progress(request: Request, oid: str):
    try:
        c = Company(oid)
        print("miss for", c)
    except (AFNoCompany, AssertionError):
        return render(
            request,
            "nocompany.html", {
                "request": request, "oid": oid,
            }
        )

    if c.report_path.exists():
        return RedirectResponse(app.url_path_for("report", oid=oid))

    wstatus = r.get(REDIS_WORKER_STATUS)
    tasks = r.lrange(REDIS_TASK_QUEUE_NAME, 0, -1)  # возвращает list of bytes    
    queue_size = len(tasks)
    try:
        qpos = tasks.index(oid) + 1
    except ValueError:
        qpos=None
    

    # position = next((i for i, task in enumerate(tasks) if task_id in str(task)), None)
    # print("pos:", position)

    last_trusted = [json.loads(item) for item in r.lrange(REDIS_TRUSTED_LIST, 0, -1)]
    last_untrusted = [json.loads(item) for item in r.lrange(REDIS_UNTRUSTED_LIST, 0, -1)]


    return render(
        request,
        "progress.html", {
            "request": request, "title": c.title, "oid": c.object_id,
            "qsize": queue_size, "wstatus": wstatus, "qpos": qpos,
            "trusted": last_trusted,
            "untrusted": last_untrusted
        }
    )


@app.get("/page/{page}", response_class=HTMLResponse)
def md_page(request: Request, page: str):
    if page not in ['about', 'anomaly', 'disclaimer', 'credits']:
        raise HTTPException(status_code=404, detail="Page not found")

    try:
        md_file = importlib.resources.files("antifraud2gis") / 'pages' / f"{page}.md"
        post = frontmatter.loads(md_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HTMLResponse(status_code=404, content="Page not found")


    title = post.get("title", page.capitalize())
    content_html = markdown.markdown(post.content)

    last_trusted = [json.loads(item) for item in r.lrange(REDIS_TRUSTED_LIST, 0, -1)]
    last_untrusted = [json.loads(item) for item in r.lrange(REDIS_UNTRUSTED_LIST, 0, -1)]



    return render(request, "markdown.html", {
        "request": request,
        "title": title,
        "content": content_html,
        "trusted": last_trusted,
        "untrusted": last_untrusted
    })

# catch-all must go LAST
@app.get("{full_path:path}")
async def catch_all(request: Request, full_path: str):
    # https://2gis.ru/togliatti/user/dfee5cd501624eafb36d4abc1c440a56/firm/3096753025014179?m=49.718483%2C53.511175%2F10.83
    m = re.search(r"/firm/(\d{10,20})", full_path)
    if m:
        object_id = m.group(1)
        print(f"Extracted {object_id} from {full_path}")
        response = RedirectResponse(app.url_path_for("report", oid=object_id))
        print("Redirect to:", {response.headers['Location']})
        return response
    else:
        return RedirectResponse(app.url_path_for("home"))

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", default=False, action='store_true')
    return parser.parse_args()


def main():
    global templates

    args = get_args()
    loginit("DEBUG" if args.verbose else "INFO")
    testlogger()
    import uvicorn
    auto_reload = bool(os.getenv("AUTO_RELOAD", False))
    print("AUTO_RELOAD:", auto_reload)
    load_dotenv()
    uvicorn.run("antifraud2gis.cli.af2web:app", host="0.0.0.0", port=8000, reload=auto_reload)

if __name__ == "__main__":
    main()