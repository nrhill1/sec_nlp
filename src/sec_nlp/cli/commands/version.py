import typer


def version_command() -> None:
    """Show version information."""
    from sec_nlp import __version__

    typer.echo(f"sec-nlp -- version: {__version__}")
