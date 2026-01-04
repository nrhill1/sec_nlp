# src/sec_nlp/cli/presets.py
"""Preset configurations for the analyze pipeline."""

from enum import Enum

from sec_nlp.prompts import ANALYZE_PROMPT_PATH
from sec_nlp.types import ConfigData


class AnalyzePreset(str, Enum):
    """Available preset configurations for the analyze pipeline."""

    quick = "quick"
    laptop = "laptop"
    thorough = "thorough"
    comprehensive = "comprehensive"
    rare_earths = "rare_earths"

    @property
    def description(self) -> str:
        """Get human-readable description of the preset."""
        return PRESET_DESCRIPTIONS[self]


PRESET_DESCRIPTIONS: dict[AnalyzePreset, str] = {
    AnalyzePreset.quick: "Fast analysis: small model, 1 filing, no vector DB",
    AnalyzePreset.laptop: "Laptop-friendly analysis: small model, tighter caps, targeted search queries",
    AnalyzePreset.thorough: "Balanced analysis: better model, 3 filings, vector DB enabled",
    AnalyzePreset.comprehensive: "Full analysis: best model, 5 filings, all features enabled",
    AnalyzePreset.rare_earths: "Focus on rare earth miners (8-K current reports) with finance-tuned LLM and search queries",
}


# Preset configuration overrides
# These values override the defaults when a preset is selected
PRESET_CONFIGS: dict[AnalyzePreset, ConfigData] = {
    AnalyzePreset.quick: {
        "llm": {
            "model_name": "llama3.2:1b",
            "temperature": 0.1,
        },
        "limit": 1,
        "batch_size": 16,
        "vector_mode": "off",
        "top_k_chunks": 30,
        "deduplicate_chunks": True,
        "confidence_threshold": 0.6,
        "validate_config": False,
        "collect_metrics": False,
    },
    AnalyzePreset.laptop: {
        "llm": {
            "model_name": "llama3.2:1b",
            "temperature": 0.1,
            "ollama_kwargs": {
                "num_ctx": 2048,
                "num_predict": 384,
            },
        },
        "limit": 1,
        "batch_size": 8,
        "loader_max_workers": 1,
        "chunk_size": 12,
        "chunk_overlap": 1,
        "min_chunk_length": 400,
        "max_chunk_length": 6000,
        "top_k_chunks": 30,
        "adaptive_top_k_cap": 30,
        "max_chunks_per_filing": 20,
        "deduplicate_chunks": True,
        "simhash_max_distance": 4,
        "confidence_threshold": 0.6,
        "vector_mode": "write",
        "vdb": {
            "qdrant_location": ":memory:",
            "embedding_model": "nomic-embed-text",
            "embedding_batch_size": 16,
            "vector_size": 768,
        },
        "search": {
            "enabled": True,
            "limit": 5,
            "score_threshold": 0.6,
            "analyze_limit": 5,
            "queries": [
                "rare earth price trends and demand shifts",
                "export controls or trade restrictions on critical minerals",
                "supply chain disruptions for rare earths",
                "quantum computing market demand or commercialization timeline",
                "quantum hardware roadmap, qubit scaling, or error correction",
                "government funding or strategic initiatives for quantum or critical minerals",
            ],
        },
        "topics": [
            "rare earth",
            "critical minerals",
            "magnet demand",
            "export controls",
            "trade restrictions",
            "price volatility",
            "supply chain disruption",
            "geopolitical risk",
            "strategic stockpile",
            "quantum computing",
            "quantum hardware",
            "qubit",
            "error correction",
            "commercialization",
            "government funding",
            "regulatory policy",
            "capacity expansion",
        ],
        "validate_config": True,
        "collect_metrics": True,
        "export_format": "yaml",
    },
    AnalyzePreset.thorough: {
        "llm": {
            "model_name": "qwen3:1.7b",
            "temperature": 0.2,
        },
        "limit": 3,
        "batch_size": 32,
        "vector_mode": "write",
        "top_k_chunks": 60,
        "deduplicate_chunks": True,
        "confidence_threshold": 0.5,
        "validate_config": True,
        "collect_metrics": True,
        "export_format": "yaml_csv",
    },
    AnalyzePreset.comprehensive: {
        "llm": {
            "model_name": "mychen76/Fin-R1:Q6",
            "temperature": 0.2,
        },
        "limit": 5,
        "batch_size": 48,
        "vector_mode": "write",
        "top_k_chunks": 100,
        "deduplicate_chunks": True,
        "confidence_threshold": 0.4,
        "validate_config": True,
        "collect_metrics": True,
        "include_raw_chunks": True,
        "export_format": "yaml_csv",
    },
    AnalyzePreset.rare_earths: {
        "symbols": ["LAC", "MP", "ALB", "SMMT"],
        "search": {
            "enabled": True,
            "queries": [
                "rare earth production",
                "lithium offtake agreement",
                "supply chain geopolitics",
                "mining permits and approvals",
                "processing capacity expansion",
                "material contract or purchase agreement",
                "capital raise or financing",
                "production halt or suspension",
            ],
        },
        "llm": {
            "model_name": "llama3.2:1b",
            "temperature": 0.2,
            "prompt_file": ANALYZE_PROMPT_PATH,
        },
        "mode": "current",
        "limit": 3,
        "batch_size": 24,
        "vector_mode": "write",
        "top_k_chunks": 50,
        "deduplicate_chunks": True,
        "topics": [
            "material contract",
            "offtake",
            "financing",
            "capital raise",
            "capex",
            "production halt",
            "supply disruption",
            "regulatory action",
            "guidance",
            "litigation",
        ],
        "validate_config": True,
        "collect_metrics": True,
        "export_format": "yaml",
    },
}


def get_preset_config(preset: AnalyzePreset) -> ConfigData:
    """Get configuration overrides for a preset.

    Args:
        preset: The preset to get configuration for

    Returns:
        Dictionary of configuration overrides
    """
    return PRESET_CONFIGS.get(preset, {})


def apply_preset_to_config(
    config_dict: ConfigData, preset: AnalyzePreset
) -> ConfigData:
    """Apply preset overrides to a configuration dictionary.

    Args:
        config_dict: Base configuration dictionary
        preset: Preset to apply

    Returns:
        Configuration dictionary with preset overrides applied
    """
    preset_config = get_preset_config(preset)

    # Deep merge preset config into base config
    result = config_dict.copy()
    for key, value in preset_config.items():
        if (
            isinstance(value, dict)
            and key in result
            and isinstance(result[key], dict)
        ):
            # Merge nested dicts
            result[key] = {**result[key], **value}
        else:
            result[key] = value

    return result


def list_presets() -> list[tuple[str, str]]:
    """List all available presets with descriptions.

    Returns:
        List of (name, description) tuples
    """
    return [(p.value, p.description) for p in AnalyzePreset]
