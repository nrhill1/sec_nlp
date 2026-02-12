# src/sec_nlp/cli/progress.py
"""CLI progress utilities.

The pipeline uses Rich Progress directly (see pipelines/presets/analyze/pipeline.py).
This module retains only the general-purpose format_duration helper.
"""


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "1h 23m 45s"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}h {minutes}m {secs}s"
