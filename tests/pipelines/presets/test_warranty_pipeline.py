# tests/pipelines/presets/test_warranty_pipeline.py
from pathlib import Path
from typing import ClassVar

from sec_nlp.pipelines.presets.warranty import (
    WarrantyPipeline,
)
from sec_nlp.pipelines.presets.warranty.config import WarrantyConfig
from sec_nlp.pipelines.types import FilingMetadata, WarrantyExtractionDict


class _TestWarrantyPipeline(WarrantyPipeline):
    pipeline_type: ClassVar[str] = "warranty_test"
    description: ClassVar[str] = "Test warranty pipeline"

    def _build_components(self) -> None:
        return


def _make_pipe(tmp_path: Path) -> WarrantyPipeline:
    config = WarrantyConfig(out_path=tmp_path, export_format="both")
    return _TestWarrantyPipeline(config=config)


def test_coverage_metrics_written(tmp_path: Path) -> None:
    pipe = _make_pipe(tmp_path)
    extraction_results: list[WarrantyExtractionDict] = [
        {
            "warranty_liability": 1.0,
            "warranty_payout": 2.0,
            "net_revenue": 3.0,
            "confidence": 0.9,
            "period": "2024",
        },
        {
            "error": "fail",
        },
    ]
    meta: FilingMetadata = {
        "accession_number": "000-123",
        "form_type": "10-K",
    }
    out = pipe._write_results("SYM", meta, extraction_results)
    assert out is not None
    data = out.read_text()
    assert '"processing":' in data
    assert '"chunks_analyzed": 2' in data
