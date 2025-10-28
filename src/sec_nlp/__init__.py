# sec_nlp/__init__.py
"""SEC NLP - CLI tool for SEC filing analysis."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("sec_nlp")
except PackageNotFoundError:
    __version__ = "0.0.0"

from .cli import main
from .core import (
    FilingManager,
    FilingMode,
    Pipeline,
    Preprocessor,
    get_logger,
    setup_logging,
)
from .core.llm import (
    SummarizationInput,
    SummarizationOutput,
    build_hf_pipeline,
    build_ollama_llm,
    build_summarization_runnable,
)
from .pipelines import (
    BaseConfig,
    BasePipeline,
    BaseResult,
    PipelineRegistry,
)
from .pipelines.impl import (
    AnalysisConfig,
    AnalysisPipeline,
    EmbeddingConfig,
    EmbeddingPipeline,
    SummaryConfig,
    SummaryPipeline,
)

__all__: list[str] = [
    "__version__",
    # cli
    "main"
    # core
    "Pipeline",
    "FilingManager",
    "Preprocessor",
    "FilingMode",
    "get_logger",
    "setup_logging"
    ## llm
    "LocalLLMBase",
    "FlanT5LocalLLM",
    "build_ollama_llm",
    "SummarizationInput",
    "SummarizationOutput",
    "build_summarization_runnable",
    # pipeline
    "BasePipeline",
    "BasePipelineConfig",
    "BasePipelineResult",
    "PipelineRegistry",
    "create_pipeline",
    ## impl
    "AnalysisPipeline",
    "AnalysisPipelineConfig",
    "EmbeddingPipeline",
    "EmbeddingPipelineConfig",
    "SummaryPipeline",
    "SummaryPipelineConfig",
]
