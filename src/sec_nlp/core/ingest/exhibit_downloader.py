# src/sec_nlp/core/ingest/exhibit_downloader.py
# src/sec_nlp/core/exhibit_downloader.py
"""Download and parse exhibit documents from SEC EDGAR filings."""

import re
import time
from pathlib import Path

import requests
from tqdm import tqdm

from sec_nlp.core.infra.logger import format_size, logger


class ExhibitDocument:
    """Represents an exhibit document from a filing."""

    def __init__(
        self,
        exhibit_number: str,
        filename: str,
        description: str | None = None,
        content: str | None = None,
        url: str | None = None,
        accession_number: str | None = None,
    ):
        """Initialize exhibit document.

        Args:
            exhibit_number: Exhibit number (e.g., "10.1", "21")
            filename: Filename of the exhibit
            description: Description of the exhibit
            content: Content of the exhibit (if already loaded)
            url: URL to download the exhibit from
            accession_number: Filing accession number if known
        """
        self.exhibit_number = exhibit_number
        self.filename = filename
        self.description = description
        self.content = content
        self.url = url
        self.accession_number = accession_number

    def __repr__(self) -> str:
        return f"<ExhibitDocument {self.exhibit_number} - {self.filename}>"


class ExhibitDownloader:
    """Download and parse exhibit documents from SEC filings."""

    # Pattern to identify document boundaries in full-submission.txt
    DOCUMENT_BOUNDARY = re.compile(
        r"<DOCUMENT>\s*<TYPE>([^<]+)\s*<SEQUENCE>(\d+)\s*<FILENAME>([^<]+)",
        re.IGNORECASE | re.DOTALL,
    )

    # Pattern to extract exhibit number from filename
    EXHIBIT_PATTERN = re.compile(
        r"ex[-_]?(\d+[a-z]?(?:[_.-]\d+)?)\.", re.IGNORECASE
    )

    def __init__(
        self,
        company_name: str,
        email: str,
        rate_limit: float = 0.1,
    ):
        """Initialize exhibit downloader.

        Args:
            company_name: Name for User-Agent
            email: Email for User-Agent (SEC requirement)
            rate_limit: Seconds to wait between requests
        """
        self.company_name = company_name
        self.email = email
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": f"{company_name} {email}",
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def parse_full_submission(
        self, full_submission_path: Path, accession_number: str | None = None
    ) -> list[ExhibitDocument]:
        """Parse full-submission.txt to extract embedded documents.

        Args:
            full_submission_path: Path to full-submission.txt
            accession_number: Optional accession number for this filing

        Returns:
            List of exhibit documents found in the submission
        """
        if not full_submission_path.exists():
            logger.warning(
                "Full submission file not found: %s", full_submission_path
            )
            return []

        logger.debug("Parsing full submission: %s", full_submission_path.name)

        try:
            with open(
                full_submission_path, encoding="utf-8", errors="ignore"
            ) as f:
                content = f.read()
        except Exception as e:
            logger.error("Failed to read full submission: %s", e)
            return []

        # Use directory name as accession number if not provided
        acc_number = accession_number or full_submission_path.parent.name

        # Split by <DOCUMENT> tags
        documents = content.split("<DOCUMENT>")

        exhibits: list[ExhibitDocument] = []

        for doc_section in documents[1:]:  # Skip first (empty) section
            try:
                # Extract metadata
                type_match = re.search(
                    r"<TYPE>([^<\n]+)", doc_section, re.IGNORECASE
                )
                filename_match = re.search(
                    r"<FILENAME>([^<\n]+)", doc_section, re.IGNORECASE
                )

                if not filename_match:
                    continue

                filename = filename_match.group(1).strip()
                doc_type = (
                    type_match.group(1).strip() if type_match else "UNKNOWN"
                )

                # Extract exhibit number from filename or type
                exhibit_number = self._extract_exhibit_number(
                    filename, doc_type
                )

                if not exhibit_number:
                    continue

                # Only include exhibit files (not main docs)
                if not self._is_exhibit_file(filename, doc_type):
                    continue

                # Extract content (everything after </TEXT> or after metadata)
                content_match = re.search(
                    r"<TEXT>(.*?)</TEXT>",
                    doc_section,
                    re.IGNORECASE | re.DOTALL,
                )

                if content_match:
                    doc_content = content_match.group(1).strip()
                else:
                    # Fallback: take everything after metadata
                    doc_content = doc_section[
                        500:
                    ]  # Skip first 500 chars of metadata

                # Extract description from metadata
                description_match = re.search(
                    r"<DESCRIPTION>([^<\n]+)", doc_section, re.IGNORECASE
                )
                description = (
                    description_match.group(1).strip()
                    if description_match
                    else None
                )

                exhibit = ExhibitDocument(
                    exhibit_number=exhibit_number,
                    filename=filename,
                    description=description,
                    content=doc_content,
                    accession_number=acc_number,
                )

                exhibits.append(exhibit)
                logger.debug("Found exhibit %s: %s", exhibit_number, filename)

            except Exception as e:
                logger.debug("Error parsing document section: %s", e)
                continue

        logger.debug(
            "Extracted %d exhibits from full submission", len(exhibits)
        )
        return exhibits

    def download_exhibits_from_index(
        self,
        accession_number: str,
        cik: str,
        exhibit_numbers: list[str] | None = None,
        output_dir: Path | None = None,
    ) -> list[ExhibitDocument]:
        """Download exhibit files from SEC EDGAR using the filing index.

        Args:
            accession_number: Filing accession number (e.g., "0000950170-25-046424")
            cik: Company CIK
            exhibit_numbers: List of exhibit numbers to download (e.g., ["10", "10.1"])
                           If None, downloads all exhibits
            output_dir: Directory to save files (optional)

        Returns:
            List of downloaded exhibit documents
        """
        # Remove dashes from accession number for URL
        acc_no_clean = accession_number.replace("-", "")

        # Build index URL
        _index_url = (
            f"https://www.sec.gov/cgi-bin/viewer?"
            f"action=view&cik={cik}&accession_number={accession_number}&xbrl_type=v"
        )

        # Alternative: Direct archive URL
        archive_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_clean}/"
        )

        logger.debug("Fetching filing index from SEC...")

        try:
            time.sleep(self.rate_limit)
            response = self.session.get(archive_url, timeout=30)
            response.raise_for_status()

            # Parse HTML to find exhibit links
            html = response.text

            # Find all exhibit file links
            # Pattern: href="ex-10_1.htm" or similar
            exhibit_links = re.findall(
                r'href="([^"]*ex[-_]?\d+[a-z]?(?:[_.-]\d+)?\.(?:htm|html|txt))"',
                html,
                re.IGNORECASE,
            )

            if not exhibit_links:
                logger.debug(
                    "No exhibit files found in archive listing (cik=%s accession=%s)",
                    cik,
                    accession_number,
                )
                return []

            logger.debug(
                "Found %d potential exhibit files in archive (cik=%s accession=%s)",
                len(exhibit_links),
                cik,
                accession_number,
            )

            exhibits: list[ExhibitDocument] = []
            total_bytes = 0
            matched = 0
            skipped_filter = 0

            for link in tqdm(
                exhibit_links,
                desc="Downloading exhibits",
                unit="file",
                leave=False,
                disable=len(exhibit_links) <= 1,
            ):
                try:
                    # Extract exhibit number from filename
                    exhibit_number = self._extract_exhibit_number(link, "")

                    if not exhibit_number:
                        continue

                    # Filter by requested exhibit numbers if specified
                    if exhibit_numbers and not self._matches_exhibit_filter(
                        exhibit_number, exhibit_numbers
                    ):
                        skipped_filter += 1
                        continue
                    matched += 1

                    # Download the exhibit file
                    file_url = f"{archive_url}{link}"
                    time.sleep(self.rate_limit)

                    logger.debug(
                        "Downloading exhibit %s from %s", exhibit_number, link
                    )

                    file_response = self.session.get(file_url, timeout=30)
                    file_response.raise_for_status()

                    content_bytes = file_response.content or b""
                    content = file_response.text
                    total_bytes += len(content_bytes)
                    logger.debug(
                        "Downloaded exhibit %s (%s): %s",
                        exhibit_number,
                        link,
                        format_size(len(content_bytes)),
                    )

                    # Save to disk if output_dir provided
                    if output_dir:
                        output_dir.mkdir(parents=True, exist_ok=True)
                        output_file = output_dir / link
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(content)
                        logger.debug("Saved to %s", output_file)

                    exhibit = ExhibitDocument(
                        exhibit_number=exhibit_number,
                        filename=link,
                        content=content,
                        url=file_url,
                        accession_number=accession_number,
                    )

                    exhibits.append(exhibit)

                except Exception as e:
                    logger.debug("Failed to download %s: %s", link, e)
                    continue

            logger.info(
                "Downloaded %d exhibits for accession %s (%s) [matched=%d skipped_filter=%d total_links=%d]",
                len(exhibits),
                accession_number,
                format_size(total_bytes),
                matched,
                skipped_filter,
                len(exhibit_links),
            )
            return exhibits

        except Exception as e:
            logger.error("Failed to fetch filing index: %s", e)
            return []

    def _extract_exhibit_number(
        self, filename: str, doc_type: str
    ) -> str | None:
        """Extract exhibit number from filename or document type.

        Args:
            filename: Filename of the document
            doc_type: Document type field

        Returns:
            Exhibit number or None
        """
        # Try filename first
        filename_lower = filename.lower()

        # Pattern: ex-10_1.htm, ex10-1.html, ex101.txt
        match = self.EXHIBIT_PATTERN.search(filename_lower)
        if match:
            number = match.group(1)
            # Normalize: 10_1 -> 10.1, 10-1 -> 10.1
            number = number.replace("_", ".").replace("-", ".")
            return number

        # Try document type
        if doc_type.upper().startswith("EX-"):
            # e.g., "EX-10.1"
            return doc_type[3:].strip()

        return None

    def _is_exhibit_file(self, filename: str, doc_type: str) -> bool:
        """Check if this is an exhibit file (not main filing doc).

        Args:
            filename: Filename
            doc_type: Document type

        Returns:
            True if this is an exhibit file
        """
        filename_lower = filename.lower()

        # Exclude main filing documents
        if any(
            x in filename_lower
            for x in [
                "primary-document",
                "main",
                "index",
                "complete",
                "filing",
                "form",
            ]
        ):
            return False

        # Check if it's an exhibit
        if filename_lower.startswith("ex"):
            return True

        return doc_type.upper().startswith("EX-")

    def _matches_exhibit_filter(
        self, exhibit_number: str, filter_numbers: list[str]
    ) -> bool:
        """Check if exhibit number matches filter.

        Args:
            exhibit_number: Exhibit number (e.g., "10.1")
            filter_numbers: List of numbers to match (e.g., ["10"])

        Returns:
            True if matches
        """
        # Extract base number (before decimal)
        base = exhibit_number.split(".")[0]

        for filter_num in filter_numbers:
            if base == filter_num or exhibit_number == filter_num:
                return True

        return False


def create_exhibit_downloader(
    company_name: str,
    email: str,
    rate_limit: float = 0.1,
) -> ExhibitDownloader:
    """Create an exhibit downloader.

    Args:
        company_name: Company name for User-Agent
        email: Email for User-Agent
        rate_limit: Rate limit between requests

    Returns:
        Configured ExhibitDownloader
    """
    return ExhibitDownloader(
        company_name=company_name,
        email=email,
        rate_limit=rate_limit,
    )
