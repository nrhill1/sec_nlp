# crates/xbrl/xbrl.pyi
"""Manual stub for the `xbrl` native extension."""

from __future__ import annotations

class XbrlFact:
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

class PyXbrlParser:
    def parse_ixbrl(self, html: str) -> list[XbrlFact]: ...
    def parse_instance(self, xml: str) -> list[XbrlFact]: ...
    def parse_auto(self, content: str) -> list[XbrlFact]: ...
    def parse_file(self, path: str) -> list[XbrlFact]: ...

def extract_facts(content: str) -> list[XbrlFact]: ...
def extract_facts_from_file(path: str) -> list[XbrlFact]: ...
