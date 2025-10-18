# sec_nlp/tests/utils/test_preprocessor.py
from pathlib import Path

import pytest
from sec_nlp.utils.preprocessor import Preprocessor

from sec_nlp.core.types import FilingMode


def test_html_paths_for_symbol_and_limit(tmp_path: Path, write_html_tree) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    write_html_tree(symbol="AAPL", form="10-K", acc="0001", html="<html>R</html>")
    write_html_tree(symbol="AAPL", form="10-K", acc="0002", html="<html>R</html>")
    pre = Preprocessor(downloads_folder=dl, chunk_size=200, chunk_overlap=20)
    paths = pre.html_paths_for_symbol("AAPL", mode=FilingMode.annual, limit=1)
    assert len(paths) == 1 and paths[0].name.endswith(".html")


def test_html_paths_for_symbol_missing_raises(tmp_path) -> None:
    pre = Preprocessor(downloads_folder=tmp_path / "dl2")
    with pytest.raises(FileNotFoundError):
        pre.html_paths_for_symbol("MSFT", mode=FilingMode.annual)
