from pathlib import Path

from sec_nlp.core.enums import FilingMode as FilingMode
from sec_nlp.core.preprocessor import Preprocessor as Preprocessor

def test_html_paths_for_symbol_and_limit(tmp_path: Path, write_html_tree) -> None: ...
def test_html_paths_for_symbol_missing_raises(tmp_path) -> None: ...
