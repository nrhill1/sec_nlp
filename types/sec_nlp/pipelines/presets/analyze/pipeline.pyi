from typing import ClassVar, Literal

from langchain_core.callbacks.base import (
    BaseCallbackHandler as BaseCallbackHandler,
)
from langchain_core.documents import Document as Document
from langchain_core.language_models import (
    BaseLanguageModel as BaseLanguageModel,
)
from langchain_core.prompts.base import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from langchain_qdrant import QdrantVectorStore as QdrantVectorStore

from sec_nlp.core.infra.logger import (
    log_divider as log_divider,
    logger as logger,
)
from sec_nlp.core.ingest.loader import Loader as Loader
from sec_nlp.core.llm.chains import (
    InputModelKeys as InputModelKeys,
    build_runnable as build_runnable,
)
from sec_nlp.core.text.deduplication import (
    SimHashConfig as SimHashConfig,
    SimHashDeduplicator as SimHashDeduplicator,
)
from sec_nlp.core.text.filters import SectionFilter as SectionFilter
from sec_nlp.core.text.section_extractor import (
    SectionExtractor as SectionExtractor,
)
from sec_nlp.pipelines import BasePipeline as BasePipeline
from sec_nlp.pipelines.observability.telemetry import (
    log_chunk_length_stats as log_chunk_length_stats,
)
from sec_nlp.pipelines.runtime import (
    get_accession_from_metadata as get_accession_from_metadata,
)
from sec_nlp.pipelines.types import (
    AnalysisResultDict as AnalysisResultDict,
    MetadataRecord as MetadataRecord,
)
from sec_nlp.prompts import load_prompt_template as load_prompt_template
from sec_nlp.types import ResultDict as ResultDict

from .config import AnalyzeConfig as AnalyzeConfig
from .io.outputs import OutputFormatter as OutputFormatter
from .io.result_writer import write_results as write_results
from .models import (
    AnalysisInput as AnalysisInput,
    AnalysisResult as AnalysisResult,
    AnalyzeResult as AnalyzeResult,
)
from .steps.analysis.analysis_runner import AnalyzerRunnable as AnalyzerRunnable
from .steps.analysis.callbacks import (
    TracingCallbackHandler as TracingCallbackHandler,
)
from .steps.analysis.instructions import (
    AnalysisInstructionBuilder as AnalysisInstructionBuilder,
)
from .steps.indexing.vector_index import VectorIndexer as VectorIndexer
from .steps.preprocess.preprocess import ChunkPreprocessor as ChunkPreprocessor
from .steps.preprocess.topic_scoring import (
    build_topic_matcher as build_topic_matcher,
)
from .steps.search.vector_search import (
    SearchResultsByQuery as SearchResultsByQuery,
    SearchRunnable as SearchRunnable,
)
from .types import (
    ChunkStats as ChunkStats,
    SymbolRunMetadata as SymbolRunMetadata,
    Timings as Timings,
)

type PromptInput = dict[
    str, InputModelKeys | list[InputModelKeys] | dict[str, InputModelKeys]
]

class AnalyzePipeline(BasePipeline):
    pipeline_type: ClassVar[Literal["analyze"]]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    requires_vector_db: ClassVar[bool]
    config: AnalyzeConfig
    @classmethod
    def config_model(cls) -> type[AnalyzeConfig]: ...
    @classmethod
    def result_model(cls) -> type[AnalyzeResult]: ...
    def run(self) -> AnalyzeResult: ...
