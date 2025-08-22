import typer
from rich import print_json
import dateutil

from ...models.author import Author
from ...db import DBSession
from ...net.author_reviews import AuthorReviewsIterator


author_app = typer.Typer(help="Author commands")


@author_app.command(name="fetch")
def fetch(public_id: str):
    """ fetch reviews for author """
    with DBSession() as dbsession:
        Author.fetch(public_id=public_id, dbsession=dbsession)


@author_app.command(name="reviews")
def reviews(public_id: str):
    """ show reviews for user """
    with DBSession() as dbsession:
        a = Author.get_or_fetch(public_id=public_id, dbsession=dbsession)
        for r in a.reviews:
            print(r)

@author_app.command(name="reviews-net")
def reviews_net(public_id: str, brief: bool = typer.Option(False, "--brief", "-b", help="brief")):
    """ show reviews for author """
    ar = AuthorReviewsIterator(public_id=public_id)
    for r in ar:
        if brief:
            print(f"{dateutil.parser.parse(r['date_created']).date()} {r['object']['id']} ({r['object']['address'].split(',')[0]}) {r['object']['name']} {r['rating']}")  
        else:
            print_json(data=r)

@author_app.command(name="reviews-wipe")
def reviews_wipe(public_id: str):
    """ wipe reviews for author """
    with DBSession() as dbsession:
        a = Author.get_or_fetch(public_id=public_id,dbsession=dbsession)
        for r in a.reviews:
            print("DEL", r)
            dbsession.delete(r)
        dbsession.delete(a)
        dbsession.commit()

