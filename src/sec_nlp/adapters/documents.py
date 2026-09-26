# src/sec_nlp/adapters/documents.py
"""Convert internal filing records at optional LangChain integration boundaries.

Import this module only from AI or vector operations. Deterministic parsers and
output serializers never require LangChain to represent source documents.
"""

from langchain_core.documents import Document

from sec_nlp.core.documents import DocumentRecord
from sec_nlp.core.types import as_json_dict


def to_langchain(record: DocumentRecord) -> Document:
    """Return a LangChain document with copied filing metadata."""
    return Document(
        page_content=record.page_content,
        metadata=dict(record.metadata),
        id=record.id,
    )


def from_langchain(document: Document | DocumentRecord) -> DocumentRecord:
    """Return an internal record preserving text, identifier, and JSON metadata."""
    return DocumentRecord(
        page_content=document.page_content,
        metadata=as_json_dict(document.metadata) or {},
        id=document.id,
    )
