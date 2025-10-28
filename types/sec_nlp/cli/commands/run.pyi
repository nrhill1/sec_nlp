from sec_nlp.pipelines.dispatcher import dispatch_pipeline as dispatch_pipeline

from sec_nlp.core import FilingMode as FilingMode

def run_command(symbols: list[str] = ..., mode: FilingMode = ..., start_date: str | None = ...) -> None: ...
