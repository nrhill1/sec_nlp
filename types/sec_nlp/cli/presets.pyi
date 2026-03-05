from enum import StrEnum

from sec_nlp.prompts import ANALYZE_PROMPT_PATH as ANALYZE_PROMPT_PATH
from sec_nlp.types import ConfigData as ConfigData

class AnalyzePreset(StrEnum):
    quick = "quick"
    laptop = "laptop"
    thorough = "thorough"
    comprehensive = "comprehensive"
    rare_earths = "rare_earths"
    @property
    def description(self) -> str: ...

PRESET_DESCRIPTIONS: dict[AnalyzePreset, str]
PRESET_CONFIGS: dict[AnalyzePreset, ConfigData]

def get_preset_config(preset: AnalyzePreset) -> ConfigData: ...
def apply_preset_to_config(
    config_dict: ConfigData, preset: AnalyzePreset
) -> ConfigData: ...
def list_presets() -> list[tuple[str, str]]: ...
