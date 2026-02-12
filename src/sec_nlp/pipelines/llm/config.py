# src/sec_nlp/pipelines/llm/config.py
"""LLM configuration for pipelines."""

import os
from functools import cached_property
from pathlib import Path

from langchain_ollama.llms import OllamaLLM
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.llm.ollama import OllamaKwargs


class LLMConfig(BaseModel):
    """Configuration for LLM settings."""

    model_config = ConfigDict(
        defer_build=True,
        frozen=True,
    )

    model_name: str = Field(
        default="llama3.2:1b",
        description="LLM model name (e.g., 'ollama:qwen-7b-instruct:latest')",
    )

    base_url: str | None = Field(
        default_factory=lambda: os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        ),
        description="Base URL for the Ollama server",
    )
    timeout: int = Field(
        default=5,
        ge=1,
        description="HTTP timeout (seconds) for LLM health checks",
    )

    prompt_file: Path | None = Field(
        default=None,
        description="Path to custom prompt YAML file",
    )

    max_new_tokens: int = Field(
        default=6144,
        ge=1,
        le=8192,
        description="Maximum number of tokens for LLM generation",
    )

    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM sampling",
    )

    require_json: bool = Field(
        default=True,
        description="Require JSON-formatted output from LLM",
    )

    keep_alive: int | str | None = Field(
        default=-1,
        description="How long to keep model in VRAM (-1 = forever, 0 = unload immediately, '5m' = 5 minutes)",
    )

    num_gpu: int | None = Field(
        default=-1,
        description="Number of GPU layers to offload (-1 = all layers)",
    )

    num_ctx: int | None = Field(
        default=None,
        description="Context window size in tokens (None = model default)",
    )

    ollama_kwargs: OllamaKwargs = Field(
        default_factory=dict,
        description="Additional keyword arguments for Ollama LLM",
    )

    @cached_property
    def _ollama_model_name(self) -> str:
        """Return model name without any provider prefix for Ollama."""
        if self.model_name.startswith("ollama:"):
            return self.model_name.split(":", 1)[1]
        return self.model_name

    @cached_property
    def prompt_path(self) -> Path:
        """
        Get resolved prompt file path (cached).

        Returns:
            Path to the prompt file

        Raises:
            ValueError: If no prompt file is specified
        """
        if self.prompt_file is None:
            raise ValueError(
                "Prompt file not specified. Provide --llm.prompt-file."
            )

        if not self.prompt_file.exists():
            raise ValueError(f"Prompt file not found: {self.prompt_file}")

        return self.prompt_file

    def setup_ollama_model(self) -> OllamaLLM:
        """Initialize Ollama LLM model."""
        try:
            if self.model_name.startswith(("openai:", "anthropic:", "azure:")):
                raise RuntimeError(
                    f"Model '{self.model_name}' is not supported; only Ollama models are supported"
                )

            from sec_nlp.core.llm import build_ollama_llm

            ollama_kwargs = dict(self.ollama_kwargs)
            base_url = self.base_url
            if "base_url" in ollama_kwargs:
                if base_url is None:
                    base_url = str(ollama_kwargs["base_url"])
                ollama_kwargs.pop("base_url", None)

            if "num_predict" not in ollama_kwargs:
                ollama_kwargs["num_predict"] = self.max_new_tokens
            if (
                "keep_alive" not in ollama_kwargs
                and self.keep_alive is not None
            ):
                ollama_kwargs["keep_alive"] = self.keep_alive
            if "num_gpu" not in ollama_kwargs and self.num_gpu is not None:
                ollama_kwargs["num_gpu"] = self.num_gpu
            if "num_ctx" not in ollama_kwargs and self.num_ctx is not None:
                ollama_kwargs["num_ctx"] = self.num_ctx

            return build_ollama_llm(
                model_name=self._ollama_model_name,
                base_url=base_url,
                temperature=self.temperature,
                format="json" if self.require_json else "",
                **ollama_kwargs,
            )

        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize LLM '{self.model_name}': {e}\n"
                f"Check that the model is available and properly configured."
            ) from e
