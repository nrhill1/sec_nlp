# src/sec_nlp/app/flows/registry.py
"""Registry mapping flow pipeline names to settings model classes.

The compile layer uses this registry to resolve the one authoritative settings
model per pipeline. That keeps stage settings creation deterministic and avoids
hardcoding model-selection logic in the runner.
"""

from sec_nlp.app.flows.models import PipelineName
from sec_nlp.pipelines.presets.analyze import AnalyzeConfig
from sec_nlp.pipelines.presets.chat import ChatSettings
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings
from sec_nlp.pipelines.presets.warranty import WarrantyConfig

type CompiledStageSettings = (
    RetrieveSettings
    | ChatSettings
    | ExhibitConfig
    | AnalyzeConfig
    | WarrantyConfig
)
type StageSettingsModel = (
    type[RetrieveSettings]
    | type[ChatSettings]
    | type[ExhibitConfig]
    | type[AnalyzeConfig]
    | type[WarrantyConfig]
)

PIPELINE_SETTINGS_MODELS: dict[PipelineName, StageSettingsModel] = {
    "retrieve": RetrieveSettings,
    "chat": ChatSettings,
    "exhibit": ExhibitConfig,
    "analyze": AnalyzeConfig,
    "warranty": WarrantyConfig,
}


def resolve_settings_model(pipeline: PipelineName) -> StageSettingsModel:
    """Return the authoritative settings class for *pipeline*.

    Raises:
        ValueError: If *pipeline* is not in the registry.
    """
    model = PIPELINE_SETTINGS_MODELS.get(pipeline)
    if model is None:
        raise ValueError(f"Unsupported flow pipeline '{pipeline}'")
    return model
