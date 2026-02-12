# Runnables — Composable Mini-Pipelines

## Overview

Lightweight, single-purpose runnables following the existing `RunnableSerializable` pattern in `sec_nlp/pipelines/presets/analyze/runnables/`. Each can run standalone or be composed into larger pipeline chains.

## Existing Implementations — Build vs. Reuse

**LangChain Runnables** provide a general-purpose `Runnable` protocol with `invoke()`, `batch()`, `stream()`, and chaining via `|` operator. However, this project already has its own `RunnableSerializable` pattern — introducing LangChain's version would create a parallel abstraction.

**No existing libraries provide SEC-specific composable runnables.** These are domain-specific compositions of the crates and modules described in the other roadmap documents.

**Recommendation: Build on the existing `RunnableSerializable` pattern.** Each runnable is a self-contained class with typed inputs/outputs. They compose via the existing chain mechanism.

---

## 1. `SectorCorrelationRunnable`

**Purpose:** Compute pairwise price-return correlation for symbols within a sector.

**Location:** `src/sec_nlp/pipelines/presets/analyze/runnables/sector_correlation.py`

**Input:**
```python
class SectorCorrelationInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbols: list[str]
    days: int = 252
    metric: str = "price_return"   # or "sentiment", "filing_frequency"
```

**Output:**
```python
class SectorCorrelationOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbols: list[str]
    correlation_matrix: dict[str, dict[str, float]]
    strongest_pair: tuple[str, str]
    strongest_correlation: float
```

**Implementation:** Fetch price data for each symbol via `sec_nlp.core.market`, compute returns, call `crates/corr` `pearson()` for each pair. O(n²) pairs — acceptable for sector-sized groups (typically 10–50 symbols).

**Dependencies:** `crates/corr`, `sec_nlp.core.market`

---

## 2. `FilingSentimentDiffRunnable`

**Purpose:** Compare LLM sentiment scores between two consecutive filings of the same type for a symbol. Detect new/removed risk factors and sentiment shifts.

**Location:** `src/sec_nlp/pipelines/presets/analyze/runnables/filing_sentiment_diff.py`

**Input:**
```python
class FilingSentimentDiffInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    current_results: list[AnalysisResultDict]
    previous_results: list[AnalysisResultDict]
```

**Output:**
```python
class FilingSentimentDiffOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    per_topic_delta: dict[str, float]      # topic → sentiment change
    new_risk_factors: list[str]
    removed_risk_factors: list[str]
    overall_sentiment_change: float
    direction: str                          # "improving", "declining", "stable"
```

**Implementation:** Compare `AnalysisResultDict` lists by topic. Compute sentiment score deltas. Identify risk factors present in current but not previous (new) and vice versa (removed). Threshold-based direction classification.

**Dependencies:** Existing analyze pipeline output types. No new crate dependencies.

---

## 3. `EarningsSurpriseRunnable`

**Purpose:** Compare XBRL-extracted EPS against analyst consensus and compute the surprise factor with post-earnings price impact.

**Location:** `src/sec_nlp/pipelines/presets/analyze/runnables/earnings_surprise.py`

**Input:**
```python
class EarningsSurpriseInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    period: str             # e.g., "2024-Q3"
    expected_eps: float     # Analyst consensus (user-provided or from market extension)
```

**Output:**
```python
class EarningsSurpriseOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    period: str
    reported_eps: float
    expected_eps: float
    surprise_pct: float           # (reported - expected) / |expected| * 100
    post_earnings_car_1d: float
    post_earnings_car_5d: float
```

**Implementation:**
1. Extract reported EPS from XBRL via `crates/xbrl` (EarningsPerShareBasic or EarningsPerShareDiluted).
2. Compute surprise: `(reported - expected) / abs(expected) * 100`.
3. Fetch post-earnings price data via `sec_nlp.core.market`.
4. Compute 1-day and 5-day CAR via `crates/corr`.

**Dependencies:** `crates/xbrl`, `crates/corr`, `sec_nlp.core.market`

---

## 4. `SupplyChainMapRunnable`

**Purpose:** Build a first-degree supplier/customer graph from exhibit documents (subsidiary lists) and entity extraction.

**Location:** `src/sec_nlp/pipelines/presets/analyze/runnables/supply_chain_map.py`

**Input:**
```python
class SupplyChainMapInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    include_exhibits: bool = True
    include_risk_factors: bool = True
```

**Output:**
```python
class RelatedEntity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    relationship: str       # "subsidiary", "supplier", "customer", "partner"
    source_filing: str      # accession number
    source_section: str     # e.g., "Exhibit 21", "Item 1A"
    confidence: float

class SupplyChainMapOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    entities: list[RelatedEntity]
    entity_count: int
```

**Implementation:**
1. Fetch Exhibit 21 (subsidiaries) via existing `exb` pipeline output or direct download.
2. Parse subsidiary list — typically a simple table of names and jurisdictions.
3. Optionally scan Item 1 (Business) and Item 1A (Risk Factors) text with `crates/entity` to extract ORG entities mentioned in supplier/customer context.
4. Use keyword proximity heuristics: ORG entity near "supplier", "customer", "vendor", "partner" → classify relationship type.
5. Deduplicate and return graph.

**Dependencies:** `crates/entity`, existing `exb` pipeline, download infrastructure

---

## 5. `RegulatoryExposureRunnable`

**Purpose:** Scan filing text for regulatory references and group by regulatory body/statute. Compare across filings for trend analysis.

**Location:** `src/sec_nlp/pipelines/presets/analyze/runnables/regulatory_exposure.py`

**Input:**
```python
class RegulatoryExposureInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    documents: list[Document]
    compare_with: list[Document] = []   # Previous filing's documents for trend comparison
```

**Output:**
```python
class RegulatoryReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    regulation: str              # e.g., "Section 13(a)", "Rule 10b-5", "Dodd-Frank"
    regulatory_body: str         # "SEC", "CFPB", "EPA", etc.
    mention_count: int
    sections: list[str]          # Filing sections where mentioned

class RegulatoryExposureOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    references: list[RegulatoryReference]
    total_mentions: int
    top_regulators: list[str]
    trend: dict[str, int] | None = None   # regulation → count change vs. previous filing
```

**Implementation:**
1. Call `crates/entity` `extract_entities()` on each document, filter for REGULATION entities.
2. Group by regulation name and regulatory body (inferred from regulation text, e.g., "Rule 10b-5" → "SEC").
3. Count mentions, identify which sections contain each reference.
4. If `compare_with` is provided, compute delta in mention counts per regulation.

**Dependencies:** `crates/entity` (via `sec_nlp.core.text.entity_extraction`)

---

## Implementation Steps (All Runnables)

1. Create each runnable file in `src/sec_nlp/pipelines/presets/analyze/runnables/`.
2. Define input/output Pydantic models (frozen, extra="forbid").
3. Implement the `RunnableSerializable` subclass with `invoke()` method.
4. Register in the runnables `__init__.py` for discoverability.
5. Write tests for each: mock crate wrappers and market data, verify computation logic. No network.

## Testing Strategy

- Each runnable tested independently with mocked dependencies.
- Sector correlation: known price series → verify correlation matrix values.
- Sentiment diff: known analysis results → verify delta computation and direction classification.
- Earnings surprise: known EPS values → verify surprise percentage and CAR pass-through.
- Supply chain map: fixture exhibit HTML → verify entity extraction and classification.
- Regulatory exposure: fixture filing text → verify reference counting and grouping.
