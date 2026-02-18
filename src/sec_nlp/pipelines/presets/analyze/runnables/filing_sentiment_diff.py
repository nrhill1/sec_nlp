"""Filing sentiment diff runnable for compare-over-time analysis."""

from __future__ import annotations

from collections import defaultdict

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.types import AnalysisResultDict
from sec_nlp.types import JsonValue

_SENTIMENT_WEIGHTS = {
    "positive": 1.0,
    "bullish": 1.0,
    "neutral": 0.0,
    "negative": -1.0,
    "bearish": -1.0,
}


class FilingSentimentDiffInput(BaseModel):
    """Runnable input for two filing result sets."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    current_results: list[AnalysisResultDict] = Field(default_factory=list)
    previous_results: list[AnalysisResultDict] = Field(default_factory=list)


class FilingSentimentDiffOutput(BaseModel):
    """Sentiment-delta output between two filing windows."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    per_topic_delta: dict[str, float] = Field(default_factory=dict)
    new_risk_factors: list[str] = Field(default_factory=list)
    removed_risk_factors: list[str] = Field(default_factory=list)
    overall_sentiment_change: float = 0.0
    direction: str = "stable"


class FilingSentimentDiffRunnable(
    RunnableSerializable[FilingSentimentDiffInput, FilingSentimentDiffOutput]
):
    """Compare filing sentiment and risk-factor mentions over time."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    def invoke(
        self,
        input: FilingSentimentDiffInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> FilingSentimentDiffOutput:
        _ = config
        _ = kwargs

        current_topic_scores = self._topic_sentiment_scores(
            input.current_results
        )
        previous_topic_scores = self._topic_sentiment_scores(
            input.previous_results
        )

        all_topics = sorted(
            set(current_topic_scores) | set(previous_topic_scores)
        )
        per_topic_delta = {
            topic: current_topic_scores.get(topic, 0.0)
            - previous_topic_scores.get(topic, 0.0)
            for topic in all_topics
        }

        current_risk_factors = self._extract_risk_factors(input.current_results)
        previous_risk_factors = self._extract_risk_factors(
            input.previous_results
        )

        overall_change = self._average_sentiment(
            input.current_results
        ) - self._average_sentiment(input.previous_results)

        return FilingSentimentDiffOutput(
            per_topic_delta=per_topic_delta,
            new_risk_factors=sorted(
                current_risk_factors - previous_risk_factors
            ),
            removed_risk_factors=sorted(
                previous_risk_factors - current_risk_factors
            ),
            overall_sentiment_change=overall_change,
            direction=self._direction(overall_change),
        )

    @staticmethod
    def _normalize_label(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip().lower()
        if not cleaned:
            return None
        return cleaned

    @staticmethod
    def _extract_topics(result: AnalysisResultDict) -> set[str]:
        topics: set[str] = set()

        tags = result.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                normalized = FilingSentimentDiffRunnable._normalize_label(tag)
                if normalized is not None:
                    topics.add(normalized)

        source_metadata = result.get("source_metadata")
        if isinstance(source_metadata, dict):
            topic_hits = source_metadata.get("topic_hits")
            if isinstance(topic_hits, list):
                for topic_hit in topic_hits:
                    normalized = FilingSentimentDiffRunnable._normalize_label(
                        topic_hit
                    )
                    if normalized is not None:
                        topics.add(normalized)

        if not topics:
            topics.add("overall")
        return topics

    @staticmethod
    def _topic_sentiment_scores(
        results: list[AnalysisResultDict],
    ) -> dict[str, float]:
        topic_scores: dict[str, list[float]] = defaultdict(list)
        for result in results:
            sentiment = FilingSentimentDiffRunnable._normalize_label(
                result.get("sentiment")
            )
            if sentiment is None:
                continue
            weight = _SENTIMENT_WEIGHTS.get(sentiment)
            if weight is None:
                continue
            for topic in FilingSentimentDiffRunnable._extract_topics(result):
                topic_scores[topic].append(weight)

        return {
            topic: sum(values) / len(values)
            for topic, values in sorted(topic_scores.items())
            if values
        }

    @staticmethod
    def _average_sentiment(results: list[AnalysisResultDict]) -> float:
        weights: list[float] = []
        for result in results:
            sentiment = FilingSentimentDiffRunnable._normalize_label(
                result.get("sentiment")
            )
            if sentiment is None:
                continue
            weight = _SENTIMENT_WEIGHTS.get(sentiment)
            if weight is not None:
                weights.append(weight)
        if not weights:
            return 0.0
        return sum(weights) / len(weights)

    @staticmethod
    def _extract_risk_factors(results: list[AnalysisResultDict]) -> set[str]:
        factors: set[str] = set()
        for result in results:
            tags = result.get("tags")
            if isinstance(tags, list):
                for tag in tags:
                    normalized = FilingSentimentDiffRunnable._normalize_label(
                        tag
                    )
                    if normalized is not None and "risk" in normalized:
                        factors.add(normalized)

            key_points = result.get("key_points")
            if isinstance(key_points, list):
                for point in key_points:
                    normalized = FilingSentimentDiffRunnable._normalize_label(
                        point
                    )
                    if normalized is not None and "risk" in normalized:
                        factors.add(normalized)

            source_metadata = result.get("source_metadata")
            if isinstance(source_metadata, dict):
                topic_hits = source_metadata.get("topic_hits")
                if isinstance(topic_hits, list):
                    for topic in topic_hits:
                        normalized = (
                            FilingSentimentDiffRunnable._normalize_label(topic)
                        )
                        if normalized is not None and "risk" in normalized:
                            factors.add(normalized)

        return factors

    @staticmethod
    def _direction(change: float) -> str:
        if change > 0.05:
            return "improving"
        if change < -0.05:
            return "declining"
        return "stable"
