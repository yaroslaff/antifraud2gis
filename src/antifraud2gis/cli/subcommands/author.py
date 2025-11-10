import typer
from rich import print_json
from rich.table import Table
from rich.console import Console

import dateutil
import sys



from ...models.author import Author
from ...db import DBSession
from ...net.author_reviews import AuthorReviewsIterator


author_app = typer.Typer(help="Author commands")


@author_app.command(name="fetch")
def fetch(public_id: str):
    """ fetch reviews for author """


    with DBSession() as dbsession:
        a = Author.get(public_id=public_id, dbsession=dbsession)
        if a is not None:
            old_nreviews = a.nreviews()
            print(f"Author {public_id} already in DB ({old_nreviews} reviews)")
            a.update_reviews(dbsession=dbsession)
            dbsession.commit()
            new_nreviews = a.nreviews()
            print(f"Updated: {old_nreviews} -> {new_nreviews} reviews")
            return
        else:
            print(f"Fetch new author {public_id}")

    Author.fetch(public_id=public_id)



@author_app.command(name="wipe")
def wipe(public_id: str):
    # delete author and all reviews
    """ wipe author and all reviews """

    with DBSession() as dbsession:
        a = Author.get(public_id=public_id,dbsession=dbsession)
        if a is None:
            print(f"Author {public_id} not found")
            return
        print(f"Wipe author {a.public_id} {a.name} and {len(a.reviews)} reviews")
        for r in a.reviews:
            print("DEL", r)
            dbsession.delete(r)
        dbsession.delete(a)
        dbsession.commit()


@author_app.command(name="old_reviews")
def old_reviews(public_id: str):
    """ show reviews for user """
    with DBSession() as dbsession:
        a = Author.get_or_fetch(public_id=public_id, dbsession=dbsession)
        print(f"# Author {a.public_id} {a.name} has {len(a.reviews)} reviews")

        for r in sorted(a.reviews, key=lambda r: r.created, reverse=True):
            print(r.created.date(), r.company.object_id, r.company.city, r.company.title, r.rating)

from rich.table import Table
from rich.console import Console
import typer

@author_app.command(name="reviews")
def reviews(public_id: str, 
            table: bool = typer.Option(False, "-t", "--table", help="Show as table")):
    """Show reviews for user"""

    with DBSession() as dbsession:
        a = Author.get_or_fetch(public_id=public_id, dbsession=dbsession)
        reviews = sorted(a.reviews, key=lambda r: r.created, reverse=True)
        first_date = reviews[-1].created.date() if reviews else "-"
        last_date = reviews[0].created.date() if reviews else "-"

        if table:
            console = Console()

            # summary
            summary = Table(show_header=False, title="Author Summary")
            summary.add_column("Field", style="bold cyan")
            summary.add_column("Value", style="bold white")

            summary.add_row("Author", f"{a.name} ({a.public_id})")
            summary.add_row("Reviews count", str(len(reviews)))
            summary.add_row("First review", str(first_date))
            summary.add_row("Last review", str(last_date))

            console.print(summary)
            # console.print()  # spacer

            # reviews
            tbl = Table(title="Reviews", show_lines=False)
            tbl.add_column("Date")
            tbl.add_column("RevID")
            tbl.add_column("Company ID", style="dim")
            tbl.add_column("City", style="dim")
            tbl.add_column("Title")
            tbl.add_column("Rating", justify="right")

            for r in reviews:
                tbl.add_row(
                    str(r.created.date()),
                    str(r.id),
                    str(r.company.object_id),
                    r.company.city or "",
                    r.company.title or "",
                    str(r.rating),
                )

            console.print(tbl)
        else:

            print(f"# Author {a.public_id} {a.name} has {len(reviews)} reviews (from {first_date} to {last_date})")
            for r in reviews:
                print(
                    r.created.date(),
                    r.id,
                    r.company.object_id,
                    r.company.city,
                    r.company.title,
                    r.rating,
                )



@author_app.command(name="reviews-net")
def reviews_net(
    public_id: str, 
    oid: str = typer.Argument(None, help="Dump only review for this object_id"),
    brief: bool = typer.Option(False, "--brief", "-b", help="brief")):
    """ show reviews for author """
    ar = AuthorReviewsIterator(public_id=public_id)
    for r in ar:

        if oid and r['object']['id'] != oid:
            # print(f"Skip review for {r['object']['id']}")
            continue

        if brief:
            print(f"{dateutil.parser.parse(r['date_created']).date()} {r['object']['id']} ({r['object']['address'].split(',')[0]}) {r['object']['name']} {r['rating']}")  
        else:
            print_json(data=r)

@author_app.command(name="reviews-data")
def reviews_data(public_id: str):
    """ show reviews for author (from db) """
    with DBSession() as dbsession:
        a = Author.get(public_id=public_id, dbsession=dbsession)
        if a is None:
            print(f"Author {public_id} not found", file=sys.stderr)
            return
        data = a.data_reviews()
        print_json(data=data)


@author_app.command(name="reviews-wipe")
def reviews_wipe(public_id: str,
        review: str = typer.Argument(None, help="Only this review")):
    """ wipe reviews for author """

    with DBSession() as dbsession:
        a = Author.get_or_fetch(public_id=public_id,dbsession=dbsession)
        for r in a.reviews:
            if review and r.id != review:
                continue
            print("DEL", r)
            dbsession.delete(r)        
        dbsession.commit()

