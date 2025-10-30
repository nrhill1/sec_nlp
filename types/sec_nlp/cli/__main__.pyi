from _typeshed import Incomplete

from sec_nlp.cli.commands import info_command as info_command
from sec_nlp.cli.commands import summarize_command as summarize_command
from sec_nlp.cli.commands import version_command as version_command

console: Incomplete
main: Incomplete

def version_callback(value: bool) -> None: ...
def main_callback(version: bool = ...) -> None: ...
