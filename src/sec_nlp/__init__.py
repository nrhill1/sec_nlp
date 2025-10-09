from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("sec_nlp")
except PackageNotFoundError:
    __version__ = "0.0.0"

from .types import FilingMode
from .pipelines import Pipeline
from .chains import SummaryPayload, build_sec_summarizer
from .llms import LocalModelWrapper
from .utils import SECFilingDownloader, Preprocessor
from .cli.__main__ import main as cli_main


def _default_prompt_path() -> str:
    return str(files("sec_nlp.prompts").joinpath("sample_prompt_1.yml"))


__all__ = [
    "__version__",
    "FilingMode",
    "Pipeline",
    "SummaryPayload",
    "build_sec_summarizer",
    "LocalModelWrapper",
    "SECFilingDownloader",
    "Preprocessor",
    "cli_main",
    "_default_prompt_path",
]
