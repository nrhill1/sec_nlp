"""Reusable LangChain tool wrappers for sec-nlp pipelines/core services."""

from langchain_core.tools import StructuredTool

from .market import market_context_tool
from .news import news_context_tool
from .retrieve import retrieve_hits_tool
from .vector import qdrant_search_tool

TOOL_REGISTRY: tuple[StructuredTool, ...] = (
    market_context_tool,
    retrieve_hits_tool,
    qdrant_search_tool,
    news_context_tool,
)

__all__: tuple[str, ...] = (
    "TOOL_REGISTRY",
    "market_context_tool",
    "news_context_tool",
    "qdrant_search_tool",
    "retrieve_hits_tool",
)
