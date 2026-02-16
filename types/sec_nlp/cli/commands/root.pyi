from _typeshed import Incomplete
from pydantic_settings import (
    BaseSettings,
    CliSubCommand as CliSubCommand,
)

from sec_nlp.core.infra.logger import logger as logger

from .analyze import AnalyzeCommand as AnalyzeCommand
from .analyze_runnables import (
    AnalyzeAnalysisCommand as AnalyzeAnalysisCommand,
    AnalyzeMarketCorrelationCommand as AnalyzeMarketCorrelationCommand,
    AnalyzeSearchCommand as AnalyzeSearchCommand,
)
from .clean import Clean as Clean
from .efts import EFTS as EFTS
from .exb import Exb as Exb
from .financials import Financials as Financials
from .holdings import Holdings as Holdings
from .insider import Insider as Insider
from .market import Market as Market
from .news import News as News
from .qdrant import Qdrant as Qdrant
from .runs import Runs as Runs
from .version import Version as Version
from .warranty import Warranty as Warranty

class Root(BaseSettings):
    model_config: Incomplete
    analyze: CliSubCommand[AnalyzeCommand]
    scan: CliSubCommand[AnalyzeSearchCommand]
    brief: CliSubCommand[AnalyzeAnalysisCommand]
    pulse: CliSubCommand[AnalyzeMarketCorrelationCommand]
    warranty: CliSubCommand[Warranty]
    exb: CliSubCommand[Exb]
    financials: CliSubCommand[Financials]
    holdings: CliSubCommand[Holdings]
    insider: CliSubCommand[Insider]
    news: CliSubCommand[News]
    efts: CliSubCommand[EFTS]
    clean: CliSubCommand[Clean]
    qdrant: CliSubCommand[Qdrant]
    market: CliSubCommand[Market]
    runs: CliSubCommand[Runs]
    version: CliSubCommand[Version]
    def cli_cmd(self) -> None: ...
