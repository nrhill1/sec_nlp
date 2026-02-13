"""Thin wrapper around the Rust `xbrl` extension."""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

from pydantic import BaseModel, ConfigDict


class XbrlExtensionError(RuntimeError):
    """Raised when the Rust `xbrl` extension is unavailable."""


class XbrlFact(BaseModel):
    """Normalized XBRL fact returned by the wrapper."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str
    namespace: str
    local_name: str
    value: float
    raw_value: str
    scale: int
    decimals: int | None
    unit: str | None
    context_ref: str
    period_start: str | None
    period_end: str | None
    period_instant: str | None
    entity_id: str | None
    segment: str | None


@lru_cache(maxsize=1)
def _load_xbrl_module() -> ModuleType:
    try:
        return import_module("xbrl")
    except Exception as exc:  # pragma: no cover - depends on extension install
        raise XbrlExtensionError(
            "xbrl extension is not available; build it with `make rs-xbrl-dev` "
            "or `make build-ext`."
        ) from exc


def _field(raw_fact: object, name: str) -> Any:
    if isinstance(raw_fact, dict):
        return raw_fact.get(name)
    return getattr(raw_fact, name, None)


def _to_fact(raw_fact: object) -> XbrlFact:
    return XbrlFact(
        tag=str(_field(raw_fact, "tag") or ""),
        namespace=str(_field(raw_fact, "namespace") or ""),
        local_name=str(_field(raw_fact, "local_name") or ""),
        value=float(_field(raw_fact, "value") or 0.0),
        raw_value=str(_field(raw_fact, "raw_value") or ""),
        scale=int(_field(raw_fact, "scale") or 0),
        decimals=_field(raw_fact, "decimals"),
        unit=_field(raw_fact, "unit"),
        context_ref=str(_field(raw_fact, "context_ref") or ""),
        period_start=_field(raw_fact, "period_start"),
        period_end=_field(raw_fact, "period_end"),
        period_instant=_field(raw_fact, "period_instant"),
        entity_id=_field(raw_fact, "entity_id"),
        segment=_field(raw_fact, "segment"),
    )


def _to_facts(raw_facts: list[object]) -> list[XbrlFact]:
    return [_to_fact(raw_fact) for raw_fact in raw_facts]


class XbrlParser:
    """Adapter around the native `xbrl.PyXbrlParser` class."""

    def __init__(self, module: ModuleType | None = None) -> None:
        self._module = module or _load_xbrl_module()
        self._parser = self._module.PyXbrlParser()

    def parse_ixbrl(self, html: str) -> list[XbrlFact]:
        """Parse inline XBRL (iXBRL) content."""
        return _to_facts(self._parser.parse_ixbrl(html))

    def parse_instance(self, xml: str) -> list[XbrlFact]:
        """Parse a traditional XBRL instance document."""
        return _to_facts(self._parser.parse_instance(xml))

    def parse_auto(self, content: str) -> list[XbrlFact]:
        """Auto-detect content type (iXBRL vs. instance) and parse facts."""
        return _to_facts(self._parser.parse_auto(content))

    def parse_file(self, path: str | Path) -> list[XbrlFact]:
        """Parse facts from a file path."""
        return _to_facts(self._parser.parse_file(str(path)))


def create_xbrl_parser() -> XbrlParser:
    """Create a parser instance backed by the Rust extension."""
    return XbrlParser()


def extract_facts(content: str) -> list[XbrlFact]:
    """Extract facts from XBRL content using auto-detection."""
    module = _load_xbrl_module()
    raw_facts = module.extract_facts(content)
    return _to_facts(raw_facts)


def extract_facts_from_file(path: str | Path) -> list[XbrlFact]:
    """Extract facts from a file path using auto-detection."""
    module = _load_xbrl_module()
    raw_facts = module.extract_facts_from_file(str(path))
    return _to_facts(raw_facts)
