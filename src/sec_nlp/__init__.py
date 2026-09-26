# src/sec_nlp/__init__.py
"""SEC filing research and terminal observation application."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sec-nlp")
except PackageNotFoundError:
    __version__ = "0+unknown"
