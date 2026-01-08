from collections.abc import Callable as Callable

from questionary import Style

from sec_nlp.cli.presets import (
    PRESET_DESCRIPTIONS as PRESET_DESCRIPTIONS,
    AnalyzePreset as AnalyzePreset,
)
from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.types import (
    ConfigData as ConfigData,
    JsonObject as JsonObject,
    JsonValue as JsonValue,
)

INTERACTIVE_STYLE: Style
DEFAULT_LLM_MODEL: str
DEFAULT_EMBEDDING_MODEL: str
MANUAL_MODEL_CHOICE: str

def run_interactive_setup() -> ConfigData | None: ...
def should_launch_interactive(symbols: list[str] | None) -> bool: ...
