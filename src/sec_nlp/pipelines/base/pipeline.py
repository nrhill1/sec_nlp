# src/sec_nlp/pipelines/base/pipeline.py
"""Abstract pipeline base providing lifecycle hooks, stage chain execution, and validation.

Every preset pipeline inherits from ``BasePipeline`` which combines a Pydantic
model for frozen configuration with explicit sequential execution. The class enforces subclass metadata (``pipeline_type``,
``description``), wires ``model_post_init`` to requirement checks and component
building, and exposes helpers for constructing and running stage chains.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import ConfigValue, InitSubclassKwargs

from .config import BasePipelineSettings
from .result import BasePipelineResult
from .stages import PipelineStage, RunContext, StageSequence

__all__: tuple[str, ...] = ("BasePipeline",)

_CLASSVAR_UNSET = "__UNSET__"


class BasePipeline(
    BaseModel,
    ABC,
):
    """Represent a configured specialist service with explicit execution steps.

    Subclasses define ``pipeline_type``, ``description``, ``config_model()``,
    ``result_model()``, and ``run()``. The base wires ``model_post_init`` so
    that requirement validation and component building happen automatically
    after config is frozen. Stage chains can be built via
    ``build_configured_stage_chain`` and executed via ``run_stage_chain``.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validation_error_cause=True,
        defer_build=True,
        frozen=True,
    )

    pipeline_type: ClassVar[str] = _CLASSVAR_UNSET
    description: ClassVar[str] = _CLASSVAR_UNSET

    requires_llm: ClassVar[bool] = False
    requires_vector_db: ClassVar[bool] = False

    name: str | None = None
    config: BasePipelineSettings

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: InitSubclassKwargs) -> None:
        """Enforce required ClassVars and frozen config on every pipeline subclass."""
        super().__pydantic_init_subclass__(**kwargs)

        if cls.model_config.get("frozen") is not True:
            raise TypeError(
                f"{cls.__name__} must not override frozen=True from BasePipeline"
            )

        if cls.pipeline_type == _CLASSVAR_UNSET:
            raise AttributeError(
                f"{cls.__name__} must define 'pipeline_type' ClassVar"
            )

        if cls.description == _CLASSVAR_UNSET:
            raise AttributeError(
                f"{cls.__name__} must define 'description' ClassVar"
            )

    @field_validator("config")
    @classmethod
    def validate_config(
        cls, value: BasePipelineSettings
    ) -> BasePipelineSettings:
        """Ensure config matches the pipeline's config_model."""
        config_model = cls.get_config_model()
        if not isinstance(value, config_model):
            raise ValueError(
                f"A config of type {type(value).__name__} was provided. "
                f"'config' should be of type {config_model.__name__}"
            )
        return value

    def model_post_init(self, __context: dict[str, ConfigValue] | None) -> None:
        """Run requirement checks and build reusable components after config freezes."""
        self._validate_requirements()
        self.config.start_run()
        self._build_components()

    def cli_cmd(self) -> BasePipelineResult:
        """Execute the pipeline as a CLI subcommand and return the result."""
        return self.run()

    def invoke(
        self,
        input: ConfigValue | None = None,
        config: dict[str, ConfigValue] | None = None,
        **kwargs: ConfigValue,
    ) -> BasePipelineResult:
        """Execute the configured specialist service."""
        _ = config
        _ = kwargs
        if input is not None:
            raise ValueError(
                f"{self.__class__.__name__}.invoke() does not accept input"
            )
        return self.run()

    def run_stages[StageStateT](
        self,
        *,
        initial_state: StageStateT,
        stages: Sequence[PipelineStage[StageStateT]],
    ) -> StageStateT:
        """Execute ordered steps with this service's run context."""
        return self.build_configured_stage_chain(stages=stages).invoke(
            initial_state
        )

    def run_stage_chain[StageStateT](
        self,
        *,
        initial_state: StageStateT,
        stage_chain: StageSequence[StageStateT],
    ) -> StageStateT:
        """Execute a prepared sequence through ordinary Python calls."""
        return stage_chain.invoke(initial_state)

    def require_stage_chain[StageStateT](
        self, stage_chain: StageSequence[StageStateT] | None
    ) -> StageSequence[StageStateT]:
        """Return an initialized sequence or raise a lifecycle error."""
        if stage_chain is None:
            raise RuntimeError("Specialist steps have not been initialized")
        return stage_chain

    def build_stage_chain[StageStateT](
        self, *, stages: Sequence[PipelineStage[StageStateT]]
    ) -> StageSequence[StageStateT]:
        """Build an ordered sequence retaining this run's identifiers."""
        if not stages:
            raise ValueError("Stage sequences require at least one step")
        return StageSequence(
            tuple(stages),
            RunContext(self.pipeline_type, str(self.config.run_id)),
        )

    def build_configured_stage_chain[StageStateT](
        self, *, stages: Sequence[PipelineStage[StageStateT]]
    ) -> StageSequence[StageStateT]:
        """Build a sequence of specialist steps with shared run context."""
        return self.build_stage_chain(stages=stages)

    def _validate_requirements(self) -> None:
        """Warn when declared LLM or vector-DB requirements lack config."""
        if self.requires_llm:
            llm_config = getattr(self.config, "llm", None)
            if llm_config is None:
                logger.warning(
                    "%s requires LLM configuration. Set the 'llm' value of the chosen config model to an LLMConfig object",
                    self.pipeline_type,
                )

        if self.requires_vector_db:
            vdb_config = getattr(self.config, "vdb", None)
            if vdb_config is None:
                logger.warning(
                    "%s requires vector DB configuration. Set the 'vdb' value of the chosen config model to a VectorConfig object",
                    self.pipeline_type,
                )

    @abstractmethod
    def run(self) -> BasePipelineResult:
        """Execute the pipeline and return a typed result with outputs and metadata."""

    def _build_components(self) -> None:
        """Build reusable pipeline components from frozen config (override in subclasses)."""
        return

    @classmethod
    @abstractmethod
    def config_model(cls) -> type[BasePipelineSettings]:
        """Return the Pydantic settings class for this pipeline."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def result_model(cls) -> type[BasePipelineResult]:
        """Return the result model class for this pipeline."""
        raise NotImplementedError

    @classmethod
    def get_config_model(cls) -> type[BasePipelineSettings]:
        """Resolve the config model via ``config_model()``."""
        return cls.config_model()

    @classmethod
    def get_result_model(cls) -> type[BasePipelineResult]:
        """Resolve the result model via ``result_model()``."""
        return cls.result_model()

    def __repr__(self) -> str:
        """Return concise debug representation for pipeline settings snapshot."""
        return f"<{self.__class__.__name__} type={self.pipeline_type}>"
