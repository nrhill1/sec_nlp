import argparse
from pathlib import Path

from _typeshed import Incomplete

from sec_nlp.core import FilingMode as FilingMode
from sec_nlp.core import Pipeline as Pipeline
from sec_nlp.core import default_prompt_path as default_prompt_path
from sec_nlp.core import get_logger as get_logger
from sec_nlp.core import settings as settings
from sec_nlp.core import setup_logging as setup_logging

logger: Incomplete

def parse_args() -> argparse.Namespace: ...
def setup_folders(fresh: bool) -> tuple[Path, Path]: ...
def cleanup_downloads(downloads_folder: Path) -> None: ...
def main() -> None: ...
