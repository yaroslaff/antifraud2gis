import typer

metrics_app = typer.Typer()

@metrics_app.command(name="list")
def metrics_list(ctx: typer.Context):
    """ show metrics """
    print("listing metrics...")
