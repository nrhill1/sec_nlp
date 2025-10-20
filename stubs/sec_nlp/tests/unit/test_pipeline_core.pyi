from pathlib import Path
from sec_nlp.core.pipeline import Pipeline as Pipeline
from sec_nlp.core.types import FilingMode as FilingMode
from typing import Any, Protocol, TypedDict
from unittest.mock import MagicMock

class HasPageContent(Protocol):
    page_content: str

class ChainSummary(TypedDict):
    summary: str
    points: list[str]
    confidence: float

class ChainOutput(TypedDict):
    status: str
    summary: ChainSummary

class BatchingGraph(Protocol):
    def batch(self, batch_inputs: list[dict[str, Any]]) -> list[ChainOutput]: ...

def make_fake_doc(text: str) -> HasPageContent: ...
def test_pipeline_instantiation_validates_and_loads_prompt(tmp_path: Path) -> None: ...
def test_pipeline_run_writes_summary(mock_build_chain: MagicMock, MockPre: MagicMock, MockDL: MagicMock, tmp_path: Path) -> None: ...
def test_pipeline_date_validators_and_errors(tmp_path: Path) -> None: ...
