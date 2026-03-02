# src/sec_nlp/pipelines/base/pipeline.py
"""Abstract pipeline base providing lifecycle hooks, stage chain execution, and validation.

Every preset pipeline inherits from ``BasePipeline`` which combines a Pydantic
model (for frozen config validation) with a LangChain ``Runnable`` interface
(for composability). The class enforces subclass metadata (``pipeline_type``,
``description``), wires ``model_post_init`` to requirement checks and component
building, and exposes helpers for constructing and running stage chains.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ConfigDict, field_validator

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import ConfigValue, InitSubclassKwargs

from .config import BasePipelineSettings
from .result import BasePipelineResult
from .stages import PipelineStageRunnable

__all__: tuple[str, ...] = ("BasePipeline",)

_CLASSVAR_UNSET = "__UNSET__"


class BasePipeline(
    BaseModel,
    Runnable[ConfigValue | None, BasePipelineResult],
    ABC,
):
    """Abstract base for all pipeline types, combining Pydantic config with LangChain Runnable.

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
        self._build_components()

    def cli_cmd(self) -> BasePipelineResult:
        """Execute the pipeline as a CLI subcommand and return the result."""
        return self.run()

    def invoke(
        self,
        input: ConfigValue | None = None,
        config: RunnableConfig | None = None,
        **kwargs: ConfigValue,
    ) -> BasePipelineResult:
        """LangChain ``Runnable.invoke`` entrypoint delegating to ``run()``."""
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
        stages: Sequence[Runnable[StageStateT, StageStateT]],
    ) -> StageStateT:
        """Build a stage chain from *stages* and invoke it on *initial_state*."""
        chain = self.build_stage_chain(stages=stages)
        return self.run_stage_chain(
            initial_state=initial_state,
            stage_chain=chain,
        )

    def run_stage_chain[StageStateT](
        self,
        *,
        initial_state: StageStateT,
        stage_chain: Runnable[StageStateT, StageStateT],
    ) -> StageStateT:
        """Invoke a prebuilt stage chain against a single mutable state object."""
        return stage_chain.invoke(initial_state)

    def require_stage_chain[StageStateT](
        self,
        stage_chain: Runnable[StageStateT, StageStateT] | None,
    ) -> Runnable[StageStateT, StageStateT]:
        """Return *stage_chain* or raise ``RuntimeError`` if not yet built."""
        if stage_chain is None:
            raise RuntimeError(
                "Stage chain not initialized; _build_components() must set _stage_chain"
            )
        return stage_chain

    def build_stage_chain[StageStateT](
        self,
        *,
        stages: Sequence[Runnable[StageStateT, StageStateT]],
    ) -> Runnable[StageStateT, StageStateT]:
        """Pipe ordered stage runnables into a single composite ``Runnable``."""
        if not stages:
            raise ValueError("Stage chains require at least one stage")
        chain: Runnable[StageStateT, StageStateT] = stages[0]
        for stage in stages[1:]:
            chain = chain | stage
        return chain

    def configure_stage_runnables[StageStateT](
        self,
        *,
        stages: Sequence[PipelineStageRunnable[StageStateT]],
    ) -> tuple[Runnable[StageStateT, StageStateT], ...]:
        """Attach pipeline-type and run-id tracing metadata to each stage runnable."""
        run_id = str(self.config.run_id)
        return tuple(
            stage.configured(
                pipeline_type=self.pipeline_type,
                run_id=run_id,
            )
            for stage in stages
        )

    def build_configured_stage_chain[StageStateT](
        self,
        *,
        stages: Sequence[PipelineStageRunnable[StageStateT]],
    ) -> Runnable[StageStateT, StageStateT]:
        """Configure tracing metadata on *stages*, then pipe them into a chain."""
        return self.build_stage_chain(
            stages=self.configure_stage_runnables(stages=stages)
        )

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
