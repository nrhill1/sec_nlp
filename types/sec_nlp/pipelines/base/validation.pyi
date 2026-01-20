from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.core.infra.logger import (
    color_text as color_text,
    logger as logger,
)
from sec_nlp.pipelines.exceptions import (
    InvalidDateException as InvalidDateException,
    InvalidEmailException as InvalidEmailException,
    InvalidLLMException as InvalidLLMException,
    InvalidPathException as InvalidPathException,
    InvalidSymbolException as InvalidSymbolException,
    LLMUnavailableException as LLMUnavailableException,
    MissingDependencyException as MissingDependencyException,
    VectorUnavailableException as VectorUnavailableException,
)
from sec_nlp.pipelines.utils import is_valid_email as is_valid_email
from sec_nlp.types import JsonValue as JsonValue

from .config import BasePipelineSettings as BasePipelineSettings

class ValidationResult(BaseModel):
    model_config: Incomplete
    passed: bool
    check_name: str
    message: str
    severity: str
    details: dict[str, JsonValue]

class ValidationReport(BaseModel):
    model_config: Incomplete
    all_passed: bool
    checks: list[ValidationResult]
    errors: int
    warnings: int
    def add_check(self, result: ValidationResult) -> None: ...
    def has_errors(self) -> bool: ...
    def print_report(self) -> None: ...

class PipelineValidator(BaseModel):
    model_config: Incomplete
    config: BasePipelineSettings
    report: ValidationReport
    def validate_all(self) -> ValidationReport: ...

def validate_pipeline(
    config: BasePipelineSettings, print_report: bool = True
) -> ValidationReport: ...
