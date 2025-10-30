from sec_nlp.core import FilingMode as FilingMode
from sec_nlp.pipelines.summary import SummaryPipeline as SummaryPipeline

def summarize_command(
    symbols: list[str] = ...,
    mode: FilingMode = ...,
    start_date: str | None = ...,
    end_date: str | None = ...,
) -> None: ...
