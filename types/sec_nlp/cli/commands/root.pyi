from _typeshed import Incomplete
from pydantic_settings import (
    BaseSettings,
    CliSubCommand as CliSubCommand,
)

from sec_nlp.core.infra.logger import logger as logger

from .analyze import AnalyzeCommand as AnalyzeCommand
from .clean import Clean as Clean
from .exb import Exb as Exb
from .financials import Financials as Financials
from .holdings import Holdings as Holdings
from .insider import Insider as Insider
from .qdrant import Qdrant as Qdrant
from .runs import Runs as Runs
from .version import Version as Version
from .warranty import Warranty as Warranty

class Root(BaseSettings):
    model_config: Incomplete
    analyze: CliSubCommand[AnalyzeCommand]
    warranty: CliSubCommand[Warranty]
    exb: CliSubCommand[Exb]
    financials: CliSubCommand[Financials]
    holdings: CliSubCommand[Holdings]
    insider: CliSubCommand[Insider]
    clean: CliSubCommand[Clean]
    qdrant: CliSubCommand[Qdrant]
    runs: CliSubCommand[Runs]
    version: CliSubCommand[Version]
    def cli_cmd(self) -> None: ...
