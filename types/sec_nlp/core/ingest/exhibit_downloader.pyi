from pathlib import Path

from _typeshed import Incomplete

from sec_nlp.core.infra.logger import (
    format_size as format_size,
    logger as logger,
)

class ExhibitDocument:
    exhibit_number: Incomplete
    filename: Incomplete
    description: Incomplete
    content: Incomplete
    url: Incomplete
    accession_number: Incomplete
    def __init__(
        self,
        exhibit_number: str,
        filename: str,
        description: str | None = None,
        content: str | None = None,
        url: str | None = None,
        accession_number: str | None = None,
    ) -> None: ...

class ExhibitDownloader:
    DOCUMENT_BOUNDARY: Incomplete
    EXHIBIT_PATTERN: Incomplete
    company_name: Incomplete
    email: Incomplete
    rate_limit: Incomplete
    session: Incomplete
    def __init__(
        self, company_name: str, email: str, rate_limit: float = 0.1
    ) -> None: ...
    def parse_full_submission(
        self, full_submission_path: Path, accession_number: str | None = None
    ) -> list[ExhibitDocument]: ...
    def download_exhibits_from_index(
        self,
        accession_number: str,
        cik: str,
        exhibit_numbers: list[str] | None = None,
        output_dir: Path | None = None,
    ) -> list[ExhibitDocument]: ...

def create_exhibit_downloader(
    company_name: str, email: str, rate_limit: float = 0.1
) -> ExhibitDownloader: ...
