# src/sec_nlp/cli/presets.py
"""Preset configurations for the analyze pipeline."""

from collections.abc import Mapping
from enum import Enum
from typing import TypeGuard

from sec_nlp.prompts import ANALYZE_PROMPT_PATH, ANALYZE_SENTIMENT_PROMPT_PATH
from sec_nlp.types import ConfigData, ConfigObject, ConfigValue


class AnalyzePreset(str, Enum):
    """Available preset configurations for the analyze pipeline."""

    quick = "quick"
    laptop = "laptop"
    thorough = "thorough"
    comprehensive = "comprehensive"
    rare_earths = "rare_earths"
    deep = "deep"
    sentiment = "sentiment"

    @property
    def description(self) -> str:
        """Get human-readable description of the preset."""
        return PRESET_DESCRIPTIONS[self]


PRESET_DESCRIPTIONS: dict[AnalyzePreset, str] = {
    AnalyzePreset.quick: "Fast analysis: small model, 1 filing, no vector DB",
    AnalyzePreset.laptop: "Laptop-friendly analysis: small model, tighter caps, targeted search queries",
    AnalyzePreset.thorough: "Balanced analysis: better model, 3 filings, vector DB enabled",
    AnalyzePreset.comprehensive: "Full analysis: best model, 5 filings, all features enabled",
    AnalyzePreset.rare_earths: "Focus on rare earth miners (8-K/6-K current reports) with finance-tuned LLM and search queries",
    AnalyzePreset.deep: "Deep profile: verbose schema with full extraction fields",
    AnalyzePreset.sentiment: "Baseline production profile: compact sentiment/impact signal pack with faster inference",
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
        "collect_metrics": True,
        "include_raw_chunks": True,
        "export_format": "yaml_csv",
    },
    AnalyzePreset.rare_earths: {
        "symbols": ["LAC", "MP", "ALB", "SMMT", "IDR", "IPXX", "USAR", "UUUU"],
        "forms": [
            "8-K",
            "10-K",
            "10-Q",
        ],  # Search event filings and periodic reports
        "vdb": {
            "search_type": "mmr",  # Use MMR for diversity instead of pure similarity
            "embedding_model": "granite-embedding:278m",
        },
        "search": {
            "limit": 25,
            "analyze_limit": 12,
            "score_threshold": 0.40,  # Relaxed for cosine distance (lower is better, 0=identical)
            "query_term_min_hits": 0,
            "query_term_min_ratio": 0.0,
            "queries": [
                # Broader production & operations queries
                "production update",
                "operational results",
                "facility commissioning",
                "mining operations",
                "processing throughput",
                # Expanded mineral & material terms
                "rare earth elements",
                "critical minerals",
                "uranium yellowcake",
                "lithium carbonate",
                "strategic materials",
                # Supply chain & commercial
                "supply chain",
                "supply agreement",
                "offtake contract",
                "customer agreement",
                "sales contract",
                # Financial & capital
                "capital raise",
                "equity offering",
                "financing transaction",
                "debt financing",
                "liquidity position",
                "cash balance",
                # Strategic & regulatory
                "government funding",
                "Department of Energy",
                "export license",
                "regulatory approval",
                "environmental permit",
                # Corporate actions
                "acquisition",
                "joint venture",
                "partnership agreement",
                "board appointment",
                "executive change",
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
        "top_k_chunks": 80,  # More chunks to analyze
        "deduplicate_chunks": True,
        "topics": [
            # Core minerals & materials
            "rare earth",
            "REE",
            "neodymium",
            "praseodymium",
            "dysprosium",
            "critical minerals",
            "uranium",
            "U3O8",
            "yellowcake",
            "lithium",
            "titanium",
            "zirconium",
            "monazite",
            "bastnaesite",
            # Operations & production
            "production",
            "output",
            "throughput",
            "processing",
            "extraction",
            "separation",
            "refining",
            "beneficiation",
            "mining",
            "mine",
            "milling",
            "concentrate",
            "recovery rate",
            "grade",
            # Facilities & projects
            "facility",
            "plant",
            "site",
            "project",
            "operations",
            "commissioning",
            "ramp-up",
            "expansion",
            "brownfield",
            "greenfield",
            # Resources & reserves
            "reserves",
            "resources",
            "measured",
            "indicated",
            "inferred",
            "ore body",
            "deposit",
            "tonnage",
            # Commercial & supply
            "offtake",
            "supply agreement",
            "customer",
            "contract",
            "sales",
            "revenue",
            "shipment",
            "delivery",
            "pricing",
            "market price",
            # Financial & capital
            "financing",
            "capital",
            "capex",
            "liquidity",
            "cash",
            "debt",
            "equity",
            "offering",
            "ATM",
            "shelf",
            "convertible",
            "warrant",
            "dilution",
            "going concern",
            # Regulatory & strategic
            "permit",
            "approval",
            "license",
            "environmental",
            "regulatory",
            "compliance",
            "government",
            "Department of Energy",
            "DOE",
            "defense",
            "strategic",
            "stockpile",
            "national security",
            "export control",
            "trade",
            "geopolitical",
            # Corporate & M&A
            "acquisition",
            "merger",
            "joint venture",
            "partnership",
            "agreement",
            "MOU",
            "binding",
            "closing",
        ],
        "min_topic_hits": 0,  # Allow chunks with any topic match
        "prioritize_topics": False,
        "min_chunk_length": 200,  # Lower minimum to capture shorter 8-K content
        "max_chunk_length": 12000,  # Allow longer chunks
        "adaptive_top_k_cap": 120,  # Higher cap for adaptive selection
        "max_chunks_per_filing": 40,  # Allow more chunks per filing
        "collect_metrics": True,
        "export_format": "yaml",
    },
    AnalyzePreset.deep: {
        "analysis_fields": [
            "is_relevant",
            "confidence_score",
            "summary",
            "key_points",
            "reasoning",
            "query_match_terms",
            "missing_query_terms",
            "binding_status",
            "contingencies",
            "impact_channels",
            "impact_direction",
            "impact_magnitude",
            "impact_horizon",
            "impact_confidence",
            "impact_rationale",
            "extracted_entities",
            "tags",
            "evidence_spans",
            "source_excerpt",
            "severity",
            "sentiment",
            "forward_looking",
            "follow_up_questions",
        ],
        "analysis_instruction_style": "full",
        "compact_result_output": False,
    },
    AnalyzePreset.sentiment: {
        "llm": {
            "model_name": "llama3.2:1b",
            "temperature": 0.05,
            "max_new_tokens": 512,
            "prompt_file": ANALYZE_SENTIMENT_PROMPT_PATH,
            "ollama_kwargs": {
                "num_predict": 320,
            },
        },
        "analysis_fields": [
            "is_relevant",
            "confidence_score",
            "summary",
            "key_points",
            "sentiment",
            "impact_direction",
            "impact_magnitude",
            "forward_looking",
            "source_excerpt",
            "query_match_terms",
            "missing_query_terms",
        ],
        "analysis_instruction_style": "compact",
        "compact_result_output": True,
        "limit": 2,
        "batch_size": 12,
        "top_k_chunks": 24,
        "adaptive_top_k_cap": 24,
        "max_chunks_per_filing": 12,
        "min_chunk_length": 350,
        "deduplicate_chunks": True,
        "confidence_threshold": 0.55,
        "search": {
            "limit": 8,
            "analyze_limit": 6,
            "score_threshold": 0.55,
        },
        "export_format": "yaml",
        "aggregate_by_filing": True,
        "include_raw_chunks": False,
        "collect_metrics": True,
    },
}


def _is_config_object(value: ConfigValue) -> TypeGuard[ConfigObject]:
    """Return whether a preset value is a config-like object."""
    if not isinstance(value, Mapping):
        return False
    return all(isinstance(key, str) for key in value)


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
        if key in result and _is_config_object(value):
            existing = result[key]
            if _is_config_object(existing):
                # Merge nested dicts
                merged: dict[str, ConfigValue] = {**existing, **value}
                result[key] = merged
                continue
        result[key] = value

    return result


def list_presets() -> list[tuple[str, str]]:
    """List all available presets with descriptions.

    Returns:
        List of (name, description) tuples
    """
    return [(p.value, p.description) for p in AnalyzePreset]
