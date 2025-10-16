"""
Type stubs for edgars module

This file provides type hints for the Rust-based edgars module.
"""

from typing import Dict, List, Tuple, Optional, Any, Union

__version__: str
__author__: str

# ============================================================================
# Client
# ============================================================================

class Client:
    """HTTP client for SEC EDGAR API with rate limiting"""

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """
        Create a new SEC client.

        Args:
            user_agent: Custom User-Agent string (should include contact email)
            timeout: Request timeout in seconds
        """
        ...

    def fetch_text(self, url: str) -> str:
        """
        Fetch text content from URL.

        Args:
            url: HTTPS URL from sec.gov domain

        Returns:
            Response body as string

        Raises:
            RuntimeError: On network errors or invalid responses
            ValueError: On validation errors (invalid URL, wrong domain)
        """
        ...

    def fetch_json(self, url: str) -> Dict[str, Any]:
        """
        Fetch and parse JSON from URL.

        Args:
            url: HTTPS URL from sec.gov domain

        Returns:
            Parsed JSON as dictionary

        Raises:
            RuntimeError: On network or parsing errors
            ValueError: On validation errors
        """
        ...

    def fetch_bytes(self, url: str) -> bytes:
        """
        Fetch raw bytes from URL.

        Args:
            url: HTTPS URL from sec.gov domain

        Returns:
            Response body as bytes

        Raises:
            RuntimeError: On network errors
            ValueError: On validation errors
        """
        ...

# ============================================================================
# Document
# ============================================================================

class Document:
    """Parsed SEC document metadata"""

    form_type: str
    """SEC form type (e.g., '10-K', '8-K', 'DEF 14A')"""

    format: str
    """Document format ('HTML', 'JSON', 'Text', 'XML')"""

    title: Optional[str]
    """Document title if available"""

    size_bytes: int
    """Document size in bytes"""

# ============================================================================
# CIK/Ticker Functions
# ============================================================================

def normalize_cik_str(cik: str) -> str:
    """
    Normalize CIK to 10-digit zero-padded format.

    Args:
        cik: CIK string (can include prefixes, dashes, etc.)

    Returns:
        10-digit zero-padded CIK

    Examples:
        >>> normalize_cik_str("320193")
        '0000320193'
        >>> normalize_cik_str("CIK0000320193")
        '0000320193'
    """
    ...

def lookup_ticker(ticker: str) -> str:
    """
    Look up CIK by ticker symbol.

    Args:
        ticker: Stock ticker symbol (case-insensitive)

    Returns:
        10-digit CIK

    Raises:
        ValueError: If ticker not found
        RuntimeError: On network errors

    Examples:
        >>> lookup_ticker("AAPL")
        '0000320193'
    """
    ...

def get_all_tickers() -> List[Tuple[str, str]]:
    """
    Get all ticker-to-CIK mappings.

    Returns:
        List of (ticker, cik) tuples

    Raises:
        RuntimeError: On network errors

    Examples:
        >>> tickers = get_all_tickers()
        >>> len(tickers) > 5000
        True
        >>> ("AAPL", "0000320193") in tickers
        True
    """
    ...

# ============================================================================
# Company Data Functions
# ============================================================================

def get_company_facts(cik: str) -> Dict[str, Any]:
    """
    Fetch company XBRL facts from SEC API.

    Args:
        cik: Company CIK (will be normalized)

    Returns:
        Dictionary containing:
            - cik: int - Company CIK number
            - entityName: str - Company name
            - facts: dict - Taxonomies and concepts

    Raises:
        RuntimeError: On network or parsing errors

    Examples:
        >>> facts = get_company_facts("320193")
        >>> facts["entityName"]
        'Apple Inc.'
        >>> "us-gaap" in facts["facts"]
        True
    """
    ...

def get_company_filings(cik: str) -> Dict[str, Any]:
    """
    Fetch company submissions/filings from SEC API.

    Args:
        cik: Company CIK (will be normalized)

    Returns:
        Dictionary containing:
            - cik: str - Company CIK (padded)
            - name: str - Company name
            - filings: dict - Filing information
                - recent: dict - Recent filings with arrays:
                    - form: List[str] - Form types
                    - accessionNumber: List[str] - Accession numbers
                    - filingDate: List[str] - Filing dates
                    - primaryDocument: List[str] - Primary document names

    Raises:
        RuntimeError: On network or parsing errors

    Examples:
        >>> filings = get_company_filings("320193")
        >>> filings["name"]
        'Apple Inc.'
        >>> "10-K" in filings["filings"]["recent"]["form"]
        True
    """
    ...

# ============================================================================
# Parser Functions
# ============================================================================

def parse_html_doc(html: str) -> Document:
    """
    Parse HTML SEC document.

    Args:
        html: HTML content

    Returns:
        Parsed document metadata

    Raises:
        RuntimeError: If form type cannot be determined or parsing fails

    Examples:
        >>> doc = parse_html_doc("<html><body>FORM 10-K</body></html>")
        >>> doc.form_type
        '10-K'
        >>> doc.format
        'HTML'
    """
    ...

def parse_json_doc(json: str) -> Document:
    """
    Parse JSON SEC document.

    Args:
        json: JSON content

    Returns:
        Parsed document metadata

    Raises:
        RuntimeError: On JSON parsing errors

    Examples:
        >>> doc = parse_json_doc('{"submissionType":"8-K"}')
        >>> doc.form_type
        '8-K'
        >>> doc.format
        'JSON'
    """
    ...

def parse_document(content: str) -> Document:
    """
        Auto-detect format and parse SEC document.
    s
        Detects format based on content and parses accordingly.
        Supports HTML, JSON, and plain text formats.

        Args:
            content: Document content

        Returns:
            Parsed document metadata

        Raises:
            RuntimeError: If format cannot be detected or parsing fails

        Examples:
            >>> doc = parse_document('{"submissionType":"10-K"}')
            >>> doc.format
            'JSON'
            >>> doc = parse_document("<html>FORM 8-K</html>")
            >>> doc.format
            'HTML'
    """
    ...
