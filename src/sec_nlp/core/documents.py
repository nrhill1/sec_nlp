# src/sec_nlp/core/documents.py
"""Internal text records shared by deterministic filing services.

Records preserve the existing text and JSON metadata contract independently of
AI libraries. Each record owns its metadata dictionary; attribute replacement
is forbidden, while enrichment may update that owned dictionary in place.
"""

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.types import JsonDict


class DocumentRecord(BaseModel):
    """Represent source text and its filing provenance without an AI dependency.

    Deterministic parsers and specialist exports share this record. Optional AI
    and vector adapters convert it at their boundary without changing provenance.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_content: str = Field(
        description="Source text or serialized fact value."
    )
    metadata: JsonDict = Field(
        default_factory=dict,
        description="Owned JSON provenance and enrichment fields.",
    )
    id: str | None = Field(
        default=None, description="Optional stable document identifier."
    )
