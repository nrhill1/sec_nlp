# src/sec_nlp/core/ingest/__init__.py
"""Ingestion helpers for SEC filings."""

from .downloader import download_filings
from .exhibit_downloader import (
    ExhibitDocument,
    ExhibitDownloader,
    create_exhibit_downloader,
)
from .filings import (
    filing_dir,
    get_cik_for_ticker,
    get_filing_date_from_dir,
    html_paths_for_symbol,
    load_xbrl_facts,
)
from .loader import Loader
from .parser import HtmlProcessor
from .types import DownloadResult, DownloadResults

__all__ = (
    "DownloadResult",
    "DownloadResults",
    "download_filings",
    "ExhibitDocument",
    "ExhibitDownloader",
    "create_exhibit_downloader",
    "filing_dir",
    "get_cik_for_ticker",
    "get_filing_date_from_dir",
    "html_paths_for_symbol",
    "load_xbrl_facts",
    "HtmlProcessor",
    "Loader",
)
