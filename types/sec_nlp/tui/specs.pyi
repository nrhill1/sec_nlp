from dataclasses import dataclass

from sec_nlp.types import ConfigScalar

type PatternList = tuple[ConfigScalar, ...]

@dataclass(frozen=True)
class SegmentSpec:
    key: ConfigScalar
    label: ConfigScalar
    patterns: PatternList

@dataclass(frozen=True)
class PipelineSpec:
    key: ConfigScalar
    label: ConfigScalar
    description: ConfigScalar
    command: ConfigScalar
    segments: tuple[SegmentSpec, ...]
    preview_fields: tuple[ConfigScalar, ...]

ANALYZE_SEGMENTS: tuple[SegmentSpec, ...]
EXB_SEGMENTS: tuple[SegmentSpec, ...]
WARRANTY_SEGMENTS: tuple[SegmentSpec, ...]
PIPELINE_SPECS: tuple[PipelineSpec, ...]

def get_pipeline_specs() -> tuple[PipelineSpec, ...]: ...
def find_pipeline_spec(key: ConfigScalar) -> PipelineSpec | None: ...
