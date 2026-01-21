"""Interface specs and CLI argument helpers for the TUI."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from sec_nlp.types import ConfigScalar

FIELD_KIND_TEXT = "text"
FIELD_KIND_LIST = "list"
FIELD_KIND_BOOL = "bool"
FIELD_KIND_CHOICE = "choice"


@dataclass(frozen=True)
class FieldSpec:
    key: ConfigScalar
    label: ConfigScalar
    kind: ConfigScalar
    cli_flag: ConfigScalar | None = None
    placeholder: ConfigScalar | None = None
    default: ConfigScalar | None = None
    choices: tuple[ConfigScalar, ...] = ()
    help: ConfigScalar | None = None


@dataclass(frozen=True)
class FormSpec:
    pipeline_key: ConfigScalar
    fields: tuple[FieldSpec, ...]
    extra_args_label: ConfigScalar
    extra_args_placeholder: ConfigScalar


ANALYZE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        key="symbols",
        label="Symbols",
        kind=FIELD_KIND_LIST,
        cli_flag=None,
        placeholder="AAPL MSFT NVDA",
        help="Positional symbols",
    ),
    FieldSpec(
        key="preset",
        label="Preset",
        kind=FIELD_KIND_CHOICE,
        cli_flag="--preset",
        choices=(
            "",
            "quick",
            "laptop",
            "thorough",
            "comprehensive",
            "rare_earths",
        ),
        help="Optional preset profile",
    ),
    FieldSpec(
        key="mode",
        label="Mode",
        kind=FIELD_KIND_CHOICE,
        cli_flag="--mode",
        choices=(
            "annual",
            "quarterly",
            "current",
            "proxy",
            "holdings",
            "insider",
            "registration",
            "shelf",
        ),
        default="annual",
    ),
    FieldSpec(
        key="limit",
        label="Limit",
        kind=FIELD_KIND_TEXT,
        cli_flag="--limit",
        placeholder="5",
    ),
    FieldSpec(
        key="topics",
        label="Topics",
        kind=FIELD_KIND_LIST,
        cli_flag="--topics",
        placeholder="pricing power, margin pressure",
    ),
    FieldSpec(
        key="keywords",
        label="Keywords",
        kind=FIELD_KIND_LIST,
        cli_flag="--keywords",
        placeholder="recall, warranty, impairment",
    ),
    FieldSpec(
        key="queries",
        label="Queries",
        kind=FIELD_KIND_LIST,
        cli_flag="--queries",
        placeholder="supply chain constraints",
    ),
    FieldSpec(
        key="vector_mode",
        label="Vector mode",
        kind=FIELD_KIND_CHOICE,
        cli_flag="--vector-mode",
        choices=("off", "read", "write"),
        default="write",
    ),
    FieldSpec(
        key="market_enabled",
        label="Market enabled",
        kind=FIELD_KIND_BOOL,
        cli_flag="--market-enabled",
        default=True,
    ),
    FieldSpec(
        key="market_ticker",
        label="Market ticker",
        kind=FIELD_KIND_TEXT,
        cli_flag="--market-ticker",
        placeholder="SPY",
    ),
    FieldSpec(
        key="batch_size",
        label="Batch size",
        kind=FIELD_KIND_TEXT,
        cli_flag="--batch-size",
        placeholder="8",
    ),
    FieldSpec(
        key="top_k_chunks",
        label="Top K chunks",
        kind=FIELD_KIND_TEXT,
        cli_flag="--top-k-chunks",
        placeholder="20",
    ),
    FieldSpec(
        key="max_chunk_length",
        label="Max chunk length",
        kind=FIELD_KIND_TEXT,
        cli_flag="--max-chunk-length",
        placeholder="1000000",
    ),
)

EXB_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        key="symbols",
        label="Symbols",
        kind=FIELD_KIND_LIST,
        cli_flag=None,
        placeholder="DE CAT",
    ),
    FieldSpec(
        key="mode",
        label="Mode",
        kind=FIELD_KIND_CHOICE,
        cli_flag="--mode",
        choices=("annual", "quarterly", "current"),
        default="annual",
    ),
    FieldSpec(
        key="limit",
        label="Limit",
        kind=FIELD_KIND_TEXT,
        cli_flag="--limit",
        placeholder="5",
    ),
    FieldSpec(
        key="exhibit_categories",
        label="Exhibit categories",
        kind=FIELD_KIND_LIST,
        cli_flag="--exhibit-categories",
        placeholder="contracts, subsidiaries, consents",
    ),
    FieldSpec(
        key="exhibit_numbers",
        label="Exhibit numbers",
        kind=FIELD_KIND_LIST,
        cli_flag="--exhibit-numbers",
        placeholder="10 21 23",
    ),
    FieldSpec(
        key="search_only",
        label="Search only",
        kind=FIELD_KIND_BOOL,
        cli_flag="--search-only",
        default=False,
    ),
    FieldSpec(
        key="batch_size",
        label="Batch size",
        kind=FIELD_KIND_TEXT,
        cli_flag="--batch-size",
        placeholder="16",
    ),
    FieldSpec(
        key="contract_categories",
        label="Contract categories",
        kind=FIELD_KIND_LIST,
        cli_flag="--contract-categories",
        placeholder="supply, credit, employment",
    ),
)

WARRANTY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        key="symbols",
        label="Symbols",
        kind=FIELD_KIND_LIST,
        cli_flag=None,
        placeholder="AAPL MSFT",
    ),
    FieldSpec(
        key="limit",
        label="Limit",
        kind=FIELD_KIND_TEXT,
        cli_flag="--limit",
        placeholder="1",
    ),
    FieldSpec(
        key="keywords",
        label="Keywords",
        kind=FIELD_KIND_LIST,
        cli_flag="--keywords",
        placeholder="warranty, reserve",
    ),
    FieldSpec(
        key="xbrl_only",
        label="XBRL only",
        kind=FIELD_KIND_BOOL,
        cli_flag="--xbrl-only",
        default=True,
    ),
    FieldSpec(
        key="export_format",
        label="Export format",
        kind=FIELD_KIND_CHOICE,
        cli_flag="--export-format",
        choices=("json", "csv", "both"),
        default="both",
    ),
)

FORM_SPECS: tuple[FormSpec, ...] = (
    FormSpec(
        pipeline_key="analyze",
        fields=ANALYZE_FIELDS,
        extra_args_label="Extra args",
        extra_args_placeholder="--market-granularity daily --market-limit 60",
    ),
    FormSpec(
        pipeline_key="exb",
        fields=EXB_FIELDS,
        extra_args_label="Extra args",
        extra_args_placeholder="--search-terms exclusive aftermarket",
    ),
    FormSpec(
        pipeline_key="warranty",
        fields=WARRANTY_FIELDS,
        extra_args_label="Extra args",
        extra_args_placeholder="--loader-max-workers 4",
    ),
)


def get_form_specs() -> tuple[FormSpec, ...]:
    return FORM_SPECS


def get_form_spec(key: ConfigScalar) -> FormSpec | None:
    for spec in FORM_SPECS:
        if spec.pipeline_key == key:
            return spec
    return None


def _split_list(value: ConfigScalar) -> list[ConfigScalar]:
    if not isinstance(value, str):
        return []
    cleaned = value.replace(",", " ")
    return [part for part in cleaned.split() if part]


def _split_extra_args(value: ConfigScalar) -> list[ConfigScalar]:
    if not isinstance(value, str):
        return []
    try:
        return [part for part in shlex.split(value) if part]
    except ValueError:
        return [part for part in value.split() if part]


def _normalize_value(value: ConfigScalar | None) -> ConfigScalar | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def build_cli_args(
    form_spec: FormSpec,
    values: dict[ConfigScalar, ConfigScalar],
    extra_args: ConfigScalar | None = None,
) -> list[ConfigScalar]:
    positional: list[ConfigScalar] = []
    flags: list[ConfigScalar] = []

    for field in form_spec.fields:
        value = _normalize_value(values.get(field.key))
        if field.kind == FIELD_KIND_BOOL:
            if field.cli_flag is None:
                continue
            if bool(value):
                flags.append(field.cli_flag)
            elif field.default is True:
                flag = str(field.cli_flag).lstrip("-")
                flags.append(f"--no-{flag}")
            continue

        if field.kind == FIELD_KIND_LIST:
            if value is None:
                value = _normalize_value(field.default)
            items = _split_list(value)
            if not items:
                continue
            if field.cli_flag:
                flags.append(field.cli_flag)
                flags.extend(items)
            else:
                positional.extend(items)
            continue

        if value is None:
            value = _normalize_value(field.default)
        if value is None:
            continue

        if field.kind == FIELD_KIND_CHOICE:
            if isinstance(value, str) and not value.strip():
                continue

        if field.cli_flag:
            flags.append(field.cli_flag)
            flags.append(value)

    if extra_args is not None:
        flags.extend(_split_extra_args(extra_args))

    return [*positional, *flags]
