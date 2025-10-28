# sec_nlp/cli/commands/__init__.py
from sec_nlp.cli.commands.analyze import analyze_command
from sec_nlp.cli.commands.embed import embed_command
from sec_nlp.cli.commands.examples import examples_command
from sec_nlp.cli.commands.info import info_command
from sec_nlp.cli.commands.run import run_command
from sec_nlp.cli.commands.version import version_command

__all__ = [
    "run_command",
    "analyze_command",
    "embed_command",
    "info_command",
    "examples_command",
    "version_command",
]
