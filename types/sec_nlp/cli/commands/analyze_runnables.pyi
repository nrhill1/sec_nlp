from pydantic_settings import CliPositionalArg as CliPositionalArg

from .analyze import AnalyzeCommand as AnalyzeCommand

class AnalyzeSearchCommand(AnalyzeCommand):
    symbols: CliPositionalArg[list[str]]

class AnalyzeAnalysisCommand(AnalyzeCommand):
    symbols: CliPositionalArg[list[str]]

class AnalyzeMarketCorrelationCommand(AnalyzeCommand):
    symbols: CliPositionalArg[list[str]]
