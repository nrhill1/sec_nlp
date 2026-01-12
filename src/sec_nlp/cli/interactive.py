# src/sec_nlp/cli/interactive.py
"""Interactive mode for the analyze pipeline using questionary."""

import sys
from collections.abc import Callable, Mapping, Sequence

import ollama
import questionary
from questionary import Style

from sec_nlp.cli.presets import PRESET_DESCRIPTIONS, AnalyzePreset
from sec_nlp.core.infra.logger import logger
from sec_nlp.types import ConfigData, JsonObject, JsonValue

# Custom style for questionary prompts
INTERACTIVE_STYLE: Style = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "fg:white bold"),
        ("answer", "fg:green bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
        ("separator", "fg:cyan"),
        ("instruction", "fg:gray"),
        ("text", "fg:white"),
    ]
)

DEFAULT_LLM_MODEL: str = "llama3.2:1b"
DEFAULT_EMBEDDING_MODEL: str = "mxbai-embed-large"
MANUAL_MODEL_CHOICE: str = "__manual_model__"


def run_interactive_setup() -> ConfigData | None:
    """Run interactive setup wizard for the analyze pipeline.

    Returns:
        Configuration dictionary if user completes setup, None if cancelled
    """
    if not sys.stdin.isatty():
        logger.warning("Interactive mode requires a terminal")
        return None

    print("\n" + "=" * 60)
    print("  SEC-NLP Interactive Setup")
    print("  Press Ctrl+C at any time to cancel")
    print("=" * 60 + "\n")

    try:
        config = _gather_config()
        if config is None:
            return None

        # Show summary and confirm
        if not _confirm_config(config):
            print("\nSetup cancelled.")
            return None

        return config

    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        return None


def _list_ollama_models() -> list[JsonObject]:
    """Get locally available Ollama models, handling failures gracefully."""
    try:
        response = ollama.list()
        models = response.get("models", [])
        if not isinstance(models, list):
            logger.warning(
                "Unexpected response from ollama.list(): %s", response
            )
            return []
        return models
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load Ollama models: %s", exc)
        return []


def _model_label(value: JsonValue) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def _get_model_name(model: JsonObject) -> str | None:
    """Extract the displayable model name from an Ollama model entry."""
    for key in ("model", "name", "digest", "id"):
        label = _model_label(model.get(key))
        if label:
            return label
    return None


def _model_details(model: JsonObject) -> dict[str, JsonValue]:
    details = model.get("details")
    if not isinstance(details, Mapping):
        return {}

    cleaned: dict[str, JsonValue] = {}
    for key, value in details.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
            continue
        if isinstance(value, Sequence) and not isinstance(value, str):
            items: list[JsonValue] = []
            ok = True
            for item in value:
                if isinstance(item, (str, int, float, bool)) or item is None:
                    items.append(item)
                else:
                    ok = False
                    break
            if ok:
                cleaned[key] = items
    return cleaned


def _is_embedding_model(model: JsonObject) -> bool:
    """Heuristically determine if a model is intended for embeddings."""
    name = (_get_model_name(model) or "").lower()
    if "embed" in name or "embedding" in name:
        return True

    details = _model_details(model)
    family = details.get("family") or details.get("families")
    families: list[str] = []
    if isinstance(family, str):
        families = [family]
    elif isinstance(family, list):
        families = [str(f) for f in family]
    if any("embed" in f.lower() for f in families):
        return True

    return False


def _build_model_choices(
    models: list[JsonObject],
    filter_fn: Callable[[JsonObject], bool] | None = None,
) -> list[questionary.Choice]:
    """Convert Ollama models into Questionary choices."""
    choices: list[questionary.Choice] = []
    for model in models:
        if filter_fn and not filter_fn(model):
            continue

        model_name = _get_model_name(model)
        if not model_name:
            continue

        details = _model_details(model)
        meta: list[str] = []
        for key in ("parameter_size", "quantization_level", "family"):
            value = details.get(key)
            if isinstance(value, str):
                meta.append(value)

        title = f"{model_name} ({', '.join(meta)})" if meta else model_name
        choices.append(questionary.Choice(title=title, value=model_name))

    # Sort for predictable display
    return sorted(choices, key=lambda c: str(c.value))


def _prompt_model_selection(
    prompt: str,
    models: list[JsonObject],
    default_value: str,
    *,
    filter_fn: Callable[[JsonObject], bool] | None = None,
    fallback_message: str | None = None,
) -> str | None:
    """Prompt the user to select or enter a model name."""
    choices = _build_model_choices(models, filter_fn=filter_fn)

    # If a filter yields nothing but models exist, fall back to showing all
    if filter_fn and not choices and models:
        if fallback_message:
            print(fallback_message)
        choices = _build_model_choices(models)

    if choices:
        choices.append(
            questionary.Choice(
                title="Other (enter manually)", value=MANUAL_MODEL_CHOICE
            )
        )
        default_choice = (
            default_value
            if any(choice.value == default_value for choice in choices)
            else None
        )

        answer = questionary.select(
            prompt,
            choices=choices,
            default=default_choice,
            style=INTERACTIVE_STYLE,
        ).ask()
        if answer is None:
            return None
        if answer == MANUAL_MODEL_CHOICE:
            manual = questionary.text(
                "Enter model name:",
                default=default_value,
                style=INTERACTIVE_STYLE,
            ).ask()
            return manual if isinstance(manual, str) else None
        return answer if isinstance(answer, str) else None

    if fallback_message:
        print(fallback_message)

    manual = questionary.text(
        f"{prompt} (enter model name):",
        default=default_value,
        style=INTERACTIVE_STYLE,
    ).ask()
    return manual if isinstance(manual, str) else None


def _gather_config() -> ConfigData | None:
    """Gather configuration through interactive prompts."""
    config: ConfigData = {}

    # 1. Preset selection first (so we can skip other prompts if preset covers them)
    preset_choices = [
        questionary.Choice(
            title=f"{preset.value}: {PRESET_DESCRIPTIONS[preset]}",
            value=preset.value,
        )
        for preset in AnalyzePreset
    ]
    preset_choices.append(
        questionary.Choice(title="custom: Configure manually", value="custom")
    )

    preset_answer = questionary.select(
        "Select a preset configuration:",
        choices=preset_choices,
        style=INTERACTIVE_STYLE,
    ).ask()

    if preset_answer is None:
        return None

    if preset_answer != "custom":
        config["preset"] = preset_answer

    # 2. Symbols (skip if preset provides them)
    preset_symbols: list[str] = []
    if config.get("preset") and config["preset"] != "custom":
        try:
            preset_obj = AnalyzePreset(config["preset"])
            from sec_nlp.cli.presets import get_preset_config

            preset_symbols_val = get_preset_config(preset_obj).get("symbols")
            if isinstance(preset_symbols_val, list):
                preset_symbols = [str(s) for s in preset_symbols_val]
        except Exception:
            preset_symbols = []

    symbols: list[str] = []
    if not preset_symbols:
        symbols_input = questionary.text(
            "Enter ticker symbols (space or comma separated):",
            instruction="e.g., AAPL MSFT GOOGL",
            style=INTERACTIVE_STYLE,
        ).ask()

        if symbols_input is None:
            return None

        symbols = [
            s.strip().upper()
            for s in symbols_input.replace(",", " ").split()
            if s.strip()
        ]
        if not symbols:
            print("No symbols provided. Please enter at least one symbol.")
            return None
    else:
        symbols = preset_symbols

    config["symbols"] = symbols

    # 3. Topics (optional)
    add_topics = questionary.confirm(
        "Add topic keywords to filter content?",
        default=False,
        style=INTERACTIVE_STYLE,
    ).ask()

    if add_topics is None:
        return None

    if add_topics:
        topics_input = questionary.text(
            "Enter topics (space or comma separated):",
            instruction="e.g., warranty indemnity acquisition",
            style=INTERACTIVE_STYLE,
        ).ask()

        if topics_input is None:
            return None

        topics = [
            t.strip().lower()
            for t in topics_input.replace(",", " ").split()
            if t.strip()
        ]
        if topics:
            config["topics"] = topics

    # 4. Filing mode (skip prompt if preset provides it)
    preset_mode = None
    if config.get("preset") and config["preset"] != "custom":
        try:
            preset_obj = AnalyzePreset(config["preset"])
            from sec_nlp.cli.presets import get_preset_config

            preset_mode = get_preset_config(preset_obj).get("mode")
        except Exception:
            preset_mode = None

    if preset_mode:
        config["mode"] = preset_mode
    else:
        mode_answer = questionary.select(
            "Select filing type:",
            choices=[
                questionary.Choice(title="annual (10-K)", value="annual"),
                questionary.Choice(title="quarterly (10-Q)", value="quarterly"),
                questionary.Choice(title="current (8-K)", value="current"),
                questionary.Choice(title="proxy (DEF 14A)", value="proxy"),
                questionary.Choice(title="holdings (13F-HR)", value="holdings"),
                questionary.Choice(
                    title="registration (S-1)", value="registration"
                ),
                questionary.Choice(
                    title="shelf registration (S-3)", value="shelf"
                ),
            ],
            default="annual",
            style=INTERACTIVE_STYLE,
        ).ask()

        if mode_answer is None:
            return None

        config["mode"] = mode_answer

    # 5. Dry run option
    dry_run = questionary.confirm(
        "Run in dry-run mode (skip actual processing)?",
        default=False,
        style=INTERACTIVE_STYLE,
    ).ask()

    if dry_run is None:
        return None

    config["dry_run"] = dry_run

    return config


def _gather_custom_config() -> ConfigData | None:
    """Gather custom configuration options."""
    config: ConfigData = {}
    available_models = _list_ollama_models()
    if not available_models:
        print(
            "No local models detected via Ollama; enter model names manually if needed."
        )

    # Model selection
    model_answer = _prompt_model_selection(
        "Select LLM model:",
        available_models,
        DEFAULT_LLM_MODEL,
    )

    if model_answer is None:
        return None

    config["llm"] = {"model_name": model_answer}

    # Filing limit
    limit_answer = questionary.text(
        "Maximum filings per symbol:",
        default="3",
        validate=lambda x: x.isdigit() and int(x) > 0,
        style=INTERACTIVE_STYLE,
    ).ask()

    if limit_answer is None:
        return None

    config["limit"] = int(limit_answer)

    # Vector DB
    vector_mode = questionary.select(
        "Vector database mode:",
        choices=[
            questionary.Choice(title="off (no vector storage)", value="off"),
            questionary.Choice(title="write (store for search)", value="write"),
            questionary.Choice(title="read (search existing)", value="read"),
        ],
        default="write",
        style=INTERACTIVE_STYLE,
    ).ask()

    if vector_mode is None:
        return None

    config["vector_mode"] = vector_mode

    # Embedding model (only when vector DB is used)
    if vector_mode != "off":
        embedding_model = _prompt_model_selection(
            "Select embedding model:",
            available_models,
            DEFAULT_EMBEDDING_MODEL,
            filter_fn=_is_embedding_model,
            fallback_message=(
                "No embedding-specific models detected; showing all Ollama models."
            ),
        )

        if embedding_model is None:
            return None

        config["vdb"] = {"embedding_model": embedding_model}

    # Export format
    export_format = questionary.select(
        "Output format:",
        choices=[
            questionary.Choice(title="json", value="json"),
            questionary.Choice(title="csv", value="csv"),
            questionary.Choice(title="yaml", value="yaml"),
            questionary.Choice(title="both (json + csv)", value="both"),
        ],
        default="json",
        style=INTERACTIVE_STYLE,
    ).ask()

    if export_format is None:
        return None

    config["export_format"] = export_format

    return config


def _confirm_config(config: ConfigData) -> bool:
    """Show configuration summary and confirm."""
    print("\n" + "-" * 40)
    print("Configuration Summary:")
    print("-" * 40)

    for key, value in config.items():
        if isinstance(value, list):
            print(f"  {key}: {', '.join(str(v) for v in value)}")
        elif isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")

    print("-" * 40 + "\n")

    return (
        questionary.confirm(
            "Proceed with this configuration?",
            default=True,
            style=INTERACTIVE_STYLE,
        ).ask()
        or False
    )


def should_launch_interactive(symbols: list[str] | None) -> bool:
    """Check if interactive mode should be launched.

    Args:
        symbols: List of symbols from CLI args

    Returns:
        True if interactive mode should be launched
    """
    # Launch interactive if no symbols provided and running in a terminal
    return (not symbols or len(symbols) == 0) and sys.stdin.isatty()
