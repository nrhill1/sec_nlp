from dataclasses import dataclass

from sec_nlp.types import ConfigScalar

FIELD_KIND_TEXT: ConfigScalar
FIELD_KIND_LIST: ConfigScalar
FIELD_KIND_BOOL: ConfigScalar
FIELD_KIND_CHOICE: ConfigScalar

@dataclass(frozen=True)
class FieldSpec:
    key: ConfigScalar
    label: ConfigScalar
    kind: ConfigScalar
    cli_flag: ConfigScalar | None
    placeholder: ConfigScalar | None
    default: ConfigScalar | None
    choices: tuple[ConfigScalar, ...]
    help: ConfigScalar | None
    section: ConfigScalar | None

@dataclass(frozen=True)
class SectionSpec:
    key: ConfigScalar
    label: ConfigScalar
    collapsed: bool

@dataclass(frozen=True)
class FormSpec:
    pipeline_key: ConfigScalar
    fields: tuple[FieldSpec, ...]
    extra_args_label: ConfigScalar
    extra_args_placeholder: ConfigScalar
    sections: tuple[SectionSpec, ...]

SECTION_CORE: ConfigScalar
SECTION_SEARCH: ConfigScalar
SECTION_MARKET: ConfigScalar
SECTION_PROCESSING: ConfigScalar
SECTION_OUTPUT: ConfigScalar

ANALYZE_SECTIONS: tuple[SectionSpec, ...]
ANALYZE_FIELDS: tuple[FieldSpec, ...]
EXB_FIELDS: tuple[FieldSpec, ...]
WARRANTY_FIELDS: tuple[FieldSpec, ...]
FORM_SPECS: tuple[FormSpec, ...]

def get_form_specs() -> tuple[FormSpec, ...]: ...
def get_form_spec(key: ConfigScalar) -> FormSpec | None: ...
def build_cli_args(
    form_spec: FormSpec,
    values: dict[ConfigScalar, ConfigScalar],
    extra_args: ConfigScalar | None = None,
) -> list[ConfigScalar]: ...
