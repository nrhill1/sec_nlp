from _typeshed import Incomplete

from sec_nlp.cli.commands import analyze_command as analyze_command
from sec_nlp.cli.commands import embed_command as embed_command
from sec_nlp.cli.commands import info_command as info_command
from sec_nlp.cli.commands import run_command as run_command
from sec_nlp.cli.commands import version_command as version_command

console: Incomplete
app: Incomplete

def version_callback(value: bool) -> None: ...
def main_callback(version: bool = ...) -> None: ...
def main() -> None: ...
