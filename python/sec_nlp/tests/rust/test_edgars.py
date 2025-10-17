from typing import Any

import pytest

try:
    import edgars
except ImportError:
    pytest.skip("edgars not installed", allow_module_level=True)


# ============================================================================
# Client Tests
# ============================================================================


class TestClient:
    def test_client_creation(self) -> None:
        """Test creating a client with default settings"""
        client: edgars.Client = edgars.Client()
        assert client is not None

    def test_client_with_user_agent(self) -> None:
        """Test creating a client with custom user agent"""
        client: edgars.Client = edgars.Client(user_agent="test-app/1.0 (test@example.com)")
        assert client is not None

    def test_client_with_timeout(self) -> None:
        """Test creating a client with custom timeout"""
        client: edgars.Client = edgars.Client(timeout=60)
        assert client is not None

    def test_fetch_text(self) -> None:
        """Test fetching text content"""
        client: edgars.Client = edgars.Client()
        text: str = client.fetch_text("https://www.sec.gov/files/company_tickers.json")

        assert isinstance(text, str)
        assert len(text) > 1000
        assert "ticker" in text.lower()

    def test_fetch_json(self) -> None:
        """Test fetching and parsing JSON"""
        client: edgars.Client = edgars.Client()
        data: dict[str, Any] = client.fetch_json("https://www.sec.gov/files/company_tickers.json")

        assert isinstance(data, dict)
        assert len(data) > 5000  # Should have thousands of companies

    def test_fetch_invalid_domain_raises(self) -> None:
        """Test that fetching from non-SEC domain raises error"""
        client: edgars.Client = edgars.Client()

        with pytest.raises(Exception) as exc_info:
            client.fetch_text("https://example.com/test")

        assert "sec.gov" in str(exc_info.value).lower()

    def test_fetch_http_rejected(self) -> None:
        """Test that HTTP (non-HTTPS) URLs are rejected"""
        client: edgars.Client = edgars.Client()

        with pytest.raises(Exception) as exc_info:
            client.fetch_text("http://www.sec.gov/test")

        assert "https" in str(exc_info.value).lower()


# ============================================================================
# CIK/Ticker Tests
# ============================================================================


class TestCIKTicker:
    def test_normalize_cik(self) -> None:
        """Test CIK normalization"""
        assert edgars.normalize_cik_str("320193") == "0000320193"
        assert edgars.normalize_cik_str("0000320193") == "0000320193"
        assert edgars.normalize_cik_str("1") == "0000000001"

    def test_normalize_cik_with_prefix(self) -> None:
        """Test CIK normalization with CIK prefix"""
        assert edgars.normalize_cik_str("CIK0000320193") == "0000320193"
        assert edgars.normalize_cik_str("CIK-320193") == "0000320193"

    def test_lookup_ticker(self) -> None:
        """Test ticker to CIK lookup"""
        cik: str = edgars.lookup_ticker("AAPL")
        assert cik == "0000320193"

    def test_lookup_ticker_case_insensitive(self) -> None:
        """Test that ticker lookup is case insensitive"""
        cik_upper: str = edgars.lookup_ticker("AAPL")
        cik_lower: str = edgars.lookup_ticker("aapl")
        assert cik_upper == cik_lower

    def test_lookup_invalid_ticker_raises(self) -> None:
        """Test that invalid ticker raises error"""
        with pytest.raises(Exception) as exc_info:
            edgars.lookup_ticker("NOTREALTICKER123")

        assert "not found" in str(exc_info.value).lower()

    def test_get_all_tickers(self) -> None:
        """Test fetching all ticker mappings"""
        tickers: list[tuple[str, str]] = edgars.get_all_tickers()

        assert isinstance(tickers, list)
        assert len(tickers) > 5000

        # Check format
        ticker: str
        cik: str
        ticker, cik = tickers[0]
        assert isinstance(ticker, str)
        assert isinstance(cik, str)
        assert len(cik) == 10  # Should be 10-digit CIK

    def test_get_all_tickers_contains_major_stocks(self) -> None:
        """Test that ticker map contains major stocks"""
        tickers_dict: dict[str, str] = dict(edgars.get_all_tickers())

        major_stocks: list[str] = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        for ticker in major_stocks:
            assert ticker in tickers_dict, f"{ticker} not in ticker map"


# ============================================================================
# Company Data Tests
# ============================================================================


class TestCompanyData:
    def test_get_company_facts(self) -> None:
        """Test fetching company XBRL facts"""
        facts: dict[str, Any] = edgars.get_company_facts("320193")  # Apple

        assert isinstance(facts, dict)
        assert "cik" in facts
        assert "entityName" in facts
        assert "facts" in facts

        assert facts["cik"] == 320193
        assert "apple" in facts["entityName"].lower()

    def test_get_company_facts_has_taxonomies(self) -> None:
        """Test that company facts include taxonomies"""
        facts: dict[str, Any] = edgars.get_company_facts("320193")

        assert "us-gaap" in facts["facts"]
        assert isinstance(facts["facts"]["us-gaap"], dict)

    def test_get_company_filings(self) -> None:
        """Test fetching company filings"""
        filings: dict[str, Any] = edgars.get_company_filings("320193")  # Apple

        assert isinstance(filings, dict)
        assert "cik" in filings
        assert "name" in filings
        assert "filings" in filings

        assert filings["cik"] == "0000320193"
        assert "apple" in filings["name"].lower()

    def test_get_company_filings_recent(self) -> None:
        """Test that recent filings are present"""
        filings: dict[str, Any] = edgars.get_company_filings("320193")

        recent: dict[str, Any] = filings["filings"]["recent"]
        assert "form" in recent
        assert "accessionNumber" in recent
        assert "filingDate" in recent

        assert len(recent["form"]) > 0
        assert "10-K" in recent["form"] or "10-Q" in recent["form"]

    def test_get_company_invalid_cik_raises(self) -> None:
        """Test that invalid CIK raises error"""
        with pytest.raises(ValueError):
            edgars.get_company_facts("9999999999")


# ============================================================================
# Parser Tests
# ============================================================================


class TestParsers:
    def test_parse_html_doc(self) -> None:
        """Test parsing HTML document"""
        html: str = """
<!DOCTYPE html>
<html>
<head><title>Apple Inc. 10-K</title></head>
<body>FORM 10-K Annual Report</body>
</html>
        """

        doc: edgars.Document = edgars.parse_html_doc(html)

        assert doc.form_type == "10-K"
        assert doc.format == "HTML"
        assert doc.title == "Apple Inc. 10-K"
        assert doc.size_bytes > 0

    def test_parse_json_doc(self) -> None:
        """Test parsing JSON document"""
        json_str: str = '{"submissionType": "8-K", "entityName": "Test Company"}'

        doc: edgars.Document = edgars.parse_json_doc(json_str)

        assert doc.form_type == "8-K"
        assert doc.format == "JSON"
        assert doc.title == "Test Company"

    def test_parse_document_auto_html(self) -> None:
        """Test auto-detection for HTML"""
        html: str = "<!DOCTYPE html><html><body>FORM 10-Q</body></html>"

        doc: edgars.Document = edgars.parse_document(html)

        assert doc.format == "HTML"
        assert doc.form_type == "10-Q"

    def test_parse_document_auto_json(self) -> None:
        """Test auto-detection for JSON"""
        json_str: str = '{"submissionType": "10-K"}'

        doc: edgars.Document = edgars.parse_document(json_str)

        assert doc.format == "JSON"
        assert doc.form_type == "10-K"

    def test_parse_document_auto_text(self) -> None:
        """Test auto-detection for plain text"""
        text: str = "CONFORMED SUBMISSION TYPE: 10-Q\nPUBLIC DOCUMENT COUNT: 50"

        doc: edgars.Document = edgars.parse_document(text)

        assert doc.format == "Text"
        assert doc.form_type == "10-Q"

    def test_parse_invalid_html_raises(self) -> None:
        """Test that HTML without form type raises error"""
        html: str = "<html><body>No form type here</body></html>"

        with pytest.raises(ValueError):
            edgars.parse_html_doc(html)

    def test_parse_invalid_json_raises(self) -> None:
        """Test that malformed JSON raises error"""
        invalid_json: str = '{"invalid": json'

        with pytest.raises(ValueError):
            edgars.parse_json_doc(invalid_json)


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    @pytest.mark.slow
    def test_full_workflow(self) -> None:
        """Test complete workflow: ticker -> CIK -> filings"""
        # Step 1: Look up ticker
        cik = edgars.lookup_ticker("AAPL")
        assert cik == "0000320193"

        # Step 2: Get company filings
        filings = edgars.get_company_filings(cik)
        assert "apple" in filings["name"].lower()

        # Step 3: Verify recent filings exist
        forms = filings["filings"]["recent"]["form"]
        assert len(forms) > 0

    @pytest.mark.slow
    def test_fetch_and_parse(self) -> None:
        """Test fetching and parsing a real filing"""
        client = edgars.Client()

        # Get Apple's filings
        filings = edgars.get_company_filings("320193")

        # Get first accession number
        accession = filings["filings"]["recent"]["accessionNumber"][0]

        # Build URL (simplified, in practice you'd use proper URL building)
        cik_no_padding = "320193"
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_padding}/{accession}.txt"

        # Fetch content
        content = client.fetch_text(url)
        assert len(content) > 0

        # Parse
        doc = edgars.parse_document(content)
        assert doc.size_bytes > 0


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    def test_normalize_cik_fast(self) -> None:
        """Test that CIK normalization is fast"""
        import time

        start = time.time()
        for i in range(10000):
            edgars.normalize_cik_str(str(i))
        elapsed = time.time() - start

        assert elapsed < 1.0, f"CIK normalization too slow: {elapsed}s"

    def test_parse_large_document(self) -> None:
        """Test parsing large documents"""
        # Create a large HTML document
        large_html = "<html><body>FORM 10-K\n" + ("x" * 1_000_000) + "</body></html>"

        doc = edgars.parse_html_doc(large_html)
        assert doc.form_type == "10-K"
        assert doc.size_bytes > 1_000_000


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    def test_error_messages_descriptive(self) -> None:
        """Test that error messages are descriptive"""
        with pytest.raises(Exception) as exc_info:
            edgars.lookup_ticker("INVALIDTICKER999")

        error_msg = str(exc_info.value)
        assert "INVALIDTICKER999" in error_msg or "not found" in error_msg.lower()

    def test_validation_errors(self) -> None:
        """Test validation errors are raised appropriately"""
        client = edgars.Client()

        with pytest.raises(Exception) as exc_info:
            client.fetch_text("https://example.com/test")

        # Should mention validation or domain restriction
        error_msg = str(exc_info.value).lower()
        assert "sec.gov" in error_msg or "validation" in error_msg


# ============================================================================
# Module Metadata Tests
# ============================================================================


class TestModuleMetadata:
    def test_module_has_version(self) -> None:
        """Test that module has __version__ attribute"""
        assert hasattr(edgars, "__version__")
        assert isinstance(edgars.__version__, str)

    def test_module_has_author(self) -> None:
        """Test that module has __author__ attribute"""
        assert hasattr(edgars, "__author__")
        assert isinstance(edgars.__author__, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
