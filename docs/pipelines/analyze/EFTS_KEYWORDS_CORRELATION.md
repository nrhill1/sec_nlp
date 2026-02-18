# EFTS + Keyword Extraction & Market Correlation

## Overview

This document outlines ideas for integrating keyword extraction (YAKE!, TF-IDF, etc.) with EFTS search and correlating filing signals with market data.

## 1. Keyword Extraction Integration

### Problem
Current EFTS searches rely on user-provided queries. Chunks from filings may contain relevant signals that users don't think to search for.

### Solution: Automatic Keyword Extraction

#### YAKE! (Yet Another Keyword Extractor)
- **Pros**: Unsupervised, language-agnostic, doesn't require training data
- **Cons**: May extract overly generic terms

#### TF-IDF Based
- **Pros**: Simple, well-understood, good for corpus-specific terms
- **Cons**: Requires building a vocabulary from multiple documents

### Implementation Ideas

1. **Query Expansion**
   - Extract top-N keywords from user's initial search results
   - Automatically expand query: `"warranty" -> "warranty accrual liability provision reserve"`
   - Configurable via `efts.auto_expand_queries: true`

2. **Chunk Relevance Boosting**
   - After vector search, re-rank results by keyword density
   - Keywords extracted from the query topic
   - Higher boost for chunks containing multiple query-derived keywords

3. **Automatic Topic Discovery**
   - Run YAKE! on all chunks before indexing
   - Store extracted keywords as metadata
   - Enable keyword-based filtering in addition to semantic search

### Suggested Config

```yaml
efts:
  keyword_extraction:
    enabled: true
    algorithm: yake  # or tfidf
    max_keywords: 10
    query_expansion: true
    expand_limit: 5  # max terms to add to query
```

## 2. Market Correlation Analysis

### Problem
The pipeline outputs filing analysis and market data separately. Users want to understand how filing signals correlate with stock price movements.

### Correlation Types

#### A. Event-Based Correlation
- **Filing event window**: -5 to +30 days around filing date
- **Metrics**: Abnormal returns, volatility change, volume spike
- **Signals**: Sentiment score, risk factor novelty, warranty accrual change

#### B. Cross-Filing Correlation
- Compare filings across time for same company
- Track sentiment/signal trends vs. stock performance
- Detect leading indicators

#### C. Peer Correlation
- Compare filing signals across peer group
- Identify outliers (company with unusual risk disclosure)
- Correlate peer-relative signals with peer-relative returns

### Implementation Ideas

1. **Sentiment-Return Correlation**
   ```
   correlation(
     filing_sentiment_score[-30:+30 days],
     cumulative_abnormal_return[-30:+30 days]
   )
   ```

2. **Signal Event Study**
   - When warranty_accrual_change > threshold:
     - Measure CAR (Cumulative Abnormal Return) in event window
     - Output: "Warranty spike events correlate with -2.3% CAR (p<0.05)"

3. **Rolling Correlation in TUI**
   - Market panel shows 30-day rolling correlation with sentiment
   - Visual overlay on chart

### Data Requirements

- Need benchmark returns (S&P 500 or sector ETF) for abnormal return calculation
- Market extension already provides OHLCV data
- Need to store filing sentiment scores persistently for time-series analysis

### Suggested Output Schema

```yaml
market_correlation:
  filing_date: "2025-01-15"
  event_window: [-5, 30]
  metrics:
    car_pre5: -0.012  # Cumulative abnormal return, 5 days before
    car_post5: 0.034
    car_post30: 0.021
    volume_spike: 2.3  # Ratio to average volume
    volatility_change: 0.15  # Change in realized volatility
  signal_correlations:
    sentiment_score: 0.42
    risk_novelty_count: -0.31
    warranty_accrual_delta: -0.28
```

## 3. EFTS + Keywords for Filing Discovery

### Use Case
User runs `analyze AAPL --topics warranty` and wants to find similar filings from other companies.

### Flow
1. Analyze AAPL warranty disclosures
2. Extract keywords: `["warranty", "accrual", "liability", "product", "repair"]`
3. Run EFTS batch search with extracted keywords
4. Filter to peer companies or sector
5. Download and analyze matching filings

### Implementation

```python
# After local analysis completes
keywords = extract_keywords(analysis_results, algorithm="yake", n=10)
efts_queries = build_efts_queries(keywords, form_types=["10-K"])
discovered = await efts_runner.search_queries(efts_queries)
new_filings = efts_runner.get_accessions_to_download(discovered)
```

## 4. Priority and Complexity

| Feature | Priority | Complexity | Dependencies |
|---------|----------|------------|--------------|
| Keyword extraction (YAKE!) | High | Low | Add yake to deps |
| Query expansion | High | Low | Keyword extraction |
| Sentiment-return correlation | Medium | Medium | Persist sentiment scores |
| Event study metrics | Medium | High | Benchmark data source |
| Peer correlation | Low | High | Peer group detection |
| TUI correlation overlay | Low | Medium | Market correlation output |

## 5. Next Steps

1. Add `yake` to dependencies (`pyproject.toml`)
2. Create `sec_nlp/core/nlp/keywords.py` with extraction functions
3. Integrate keyword extraction into preprocessing step
4. Add `keyword_extraction` config section to AnalyzeConfig
5. For correlation: extend market_enrichment output with correlation metrics
