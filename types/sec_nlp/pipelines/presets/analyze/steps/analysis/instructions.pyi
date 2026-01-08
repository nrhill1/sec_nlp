from pydantic import BaseModel

from sec_nlp.core.infra.logger import logger as logger

ANALYSIS_FIELD_ORDER: list[str]
ANALYSIS_FIELD_DESCRIPTIONS: dict[str, str]
REQUIRED_ANALYSIS_FIELDS: tuple[str, str]

class AnalysisInstructionBuilder(BaseModel):
    analysis_fields: list[str]
    def build(self) -> str: ...
