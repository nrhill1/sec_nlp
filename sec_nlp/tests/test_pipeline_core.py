from unittest.mock import patch, MagicMock
import json

from datetime import date
from sec_nlp.pipelines.pipeline import Pipeline
from sec_nlp.types import FilingMode


def make_fake_doc(text):
    D = MagicMock()
    D.page_content = text
    return D


def test_pipeline_instantiation_validates_and_loads_prompt(tmp_path):
    p = Pipeline(
        mode=FilingMode.annual,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        keyword="revenue",
        out_path=tmp_path / "out",
        dl_path=tmp_path / "dl",
        dry_run=True,
    )
    assert p.keyword_lower == "revenue"

    assert p.out_path.exists()
    assert p.dl_path.exists()


@patch("sec_nlp.pipelines.pipeline.SECFilingDownloader")
@patch("sec_nlp.pipelines.pipeline.Preprocessor")
@patch("sec_nlp.pipelines.pipeline.build_sec_runnable")
def test_pipeline_run_writes_summary(mock_build_chain, MockPre, MockDL, tmp_path):
    out_path = tmp_path / "out"
    out_path.mkdir()
    dl_path = tmp_path / "dl"
    dl_path.mkdir()

    dl_inst = MockDL.return_value
    dl_inst.add_symbol.return_value = None
    dl_inst.download_filings.return_value = {"AAPL": True}

    pre_inst = MockPre.return_value
    fake_html = (
        dl_path
        / "sec-edgar-filings"
        / "AAPL"
        / "10-K"
        / "0001"
        / "primary-document.html"
    )
    fake_html.parent.mkdir(parents=True, exist_ok=True)
    fake_html.write_text("<html>Revenue is up</html>", encoding="utf-8")
    pre_inst.html_paths_for_symbol.return_value = [fake_html]
    pre_inst.transform_html.return_value = [make_fake_doc("Revenue increased due to X")]

    class FakeGraph:
        def batch(self, batch_inputs):
            return [
                {
                    "status": "ok",
                    "summary": {
                        "summary": "Revenue up",
                        "points": ["X"],
                        "confidence": 0.9,
                    },
                }
                for _ in batch_inputs
            ]

    mock_build_chain.return_value = FakeGraph()

    pipe = Pipeline(
        mode=FilingMode.annual,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        keyword="revenue",
        out_path=out_path,
        dl_path=dl_path,
        dry_run=True,
    )

    written = pipe.run("AAPL")

    assert len(written) == 1
    out_file = written[0]
    assert out_file.exists()
    payload = json.loads(out_file.read_text())
    assert payload["symbol"] == "AAPL"
    assert payload["summaries"][0]["summary"] == "Revenue up"


def test_pipeline_date_validators_and_errors(tmp_path):
    with pytest.raises(Exception):
        Pipeline(
            mode=FilingMode.annual,
            start_date=date(2025, 1, 2),
            end_date=date(2025, 1, 1),
            keyword="rev",
            out_path=tmp_path / "o",
            dl_path=tmp_path / "d",
            dry_run=True,
        )
