from langchain_core.runnables import Runnable as Runnable

from sec_nlp.pipelines.types import AnalysisResultDict as AnalysisResultDict

from ..search.vector_search import (
    SearchRetrieveInput as SearchRetrieveInput,
    SearchRunnable as SearchRunnable,
)
from .analysis_runner import AnalyzerRunnable as AnalyzerRunnable

def build_search_analysis_chain(
    *, search_runner: SearchRunnable, analyzer: AnalyzerRunnable
) -> Runnable[SearchRetrieveInput, list[AnalysisResultDict]]: ...
