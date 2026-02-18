# EFTS - SEC EDGAR Full-Text Search Extension

Rust/PyO3 extension module for SEC EDGAR Full-Text Search (EFTS) with integrated
keyword extraction and document ranking capabilities.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ANALYZE PIPELINE                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   Symbols   │───▶│ EFTS Search  │───▶│  Document   │───▶│     LLM     │  │
│  │   Topics    │    │   (Rust)     │    │   Ranking   │    │   Analysis  │  │
│  └─────────────┘    └──────────────┘    └─────────────┘    └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                              │                    │
                              ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EFTS RUST EXTENSION                                  │
│  ┌──────────────────────────────┐    ┌──────────────────────────────────┐   │
│  │       EFTS Client            │    │      Keyword Ranking             │   │
│  │  ┌────────────────────────┐  │    │  ┌────────────────────────────┐  │   │
│  │  │ search()               │  │    │  │ YakeExtractor              │  │   │
│  │  │ search_all()           │  │    │  │ RakeExtractor              │  │   │
│  │  │ search_async()         │  │    │  │ TextRankExtractor          │  │   │
│  │  │ batch_search_async()   │  │    │  │ TfIdfRanker                │  │   │
│  │  └────────────────────────┘  │    │  │ score_document_keywords()  │  │   │
│  │           │                  │    │  │ rank_documents_by_keywords │  │   │
│  │           ▼                  │    │  └────────────────────────────┘  │   │
│  │  ┌────────────────────────┐  │    └──────────────────────────────────┘   │
│  │  │ SEC EDGAR EFTS API     │  │                    │                      │
│  │  │ efts.sec.gov           │  │                    │                      │
│  │  └────────────────────────┘  │                    │                      │
│  └──────────────────────────────┘                    │                      │
└─────────────────────────────────────────────────────────────────────────────┘
                              │                        │
                              ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PYTHON LAYER                                         │
│  ┌──────────────────────────────┐    ┌──────────────────────────────────┐   │
│  │  sec_nlp.core.edgar.efts     │    │  sec_nlp.core.text.ranking       │   │
│  │  - EFTSSearcher              │    │  - KeywordExtractor              │   │
│  │  - search_filings()          │    │  - DocumentRanker                │   │
│  └──────────────────────────────┘    │  - rank_documents()              │   │
│                                      │  - score_document()              │   │
│  ┌──────────────────────────────┐    └──────────────────────────────────┘   │
│  │  topic_scoring.py            │                                           │
│  │  - score_documents()         │◀──────── Uses Rust backend when available │
│  │  - count_topics()            │                                           │
│  └──────────────────────────────┘                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How EFTS Integrates with Analyze Pipeline

### 1. Search Phase
The analyze pipeline accepts symbols (tickers) and topics as input. EFTS searches
SEC EDGAR for filings mentioning these topics:

```python
from efts import EFTSClient

client = EFTSClient(user_agent="SEC NLP Tool (me@example.com)")
hits = client.search_all(
    "warranty accrual",
    forms=["10-K", "10-Q"],
    tickers=["AAPL"],
    max_results=100
)
```

### 2. Document Ranking Phase
Retrieved documents are ranked by keyword relevance using the Rust-based
ranking algorithms:

```python
from efts import rank_documents_by_keywords, YakeExtractor

# Score documents by topic hits
scores = rank_documents_by_keywords(
    documents=[hit.snippet for hit in hits],
    keywords=["warranty", "accrual", "reserve"],
    case_insensitive=True,
    min_hits=1
)

# Or extract important keywords from results
extractor = YakeExtractor(ngram_size=3)
keywords = extractor.extract_keywords(document_text, top_n=10)
```

### 3. Topic Scoring Integration
The `topic_scoring.py` module automatically uses Rust when available:

```python
from sec_nlp.pipelines.presets.analyze.steps.preprocess.topic_scoring import (
    score_documents
)

ranked_docs = score_documents(
    docs,
    topics=["warranty", "liability"],
    min_hits=1,
    prioritize=True  # Sort by score descending
)
```

## Available Keyword Extraction Algorithms

| Algorithm | Best For | Score Interpretation |
|-----------|----------|----------------------|
| **YAKE** | Single documents, unsupervised | Lower = more important |
| **RAKE** | Phrase extraction | Higher = more important |
| **TextRank** | Graph-based ranking | Higher = more important |
| **TF-IDF** | Corpus comparison | Higher = more important |

## Build

```bash
# Development build
maturin develop -m crates/efts/Cargo.toml

# Or via make
make build-ext
```

## Usage Examples

### Basic Search
```python
from efts import EFTSClient, create_efts_client

# Using factory function
client = create_efts_client("me@example.com")

# Search with filters
response = client.search(
    "warranty accrual",
    forms=["10-K"],
    start_date="2023-01-01",
    end_date="2024-01-01",
    limit=10
)
print(f"Found {response.total} results")
for hit in response.hits:
    print(f"  {hit.company_name}: {hit.form_type} ({hit.filed_date})")
```

### Keyword Extraction
```python
from efts import YakeExtractor, RakeExtractor, TextRankExtractor

text = """The Company recorded warranty reserves of $10 million.
Warranty claims increased during the fiscal year."""

# YAKE - best for single documents
yake = YakeExtractor(ngram_size=2)
for kw in yake.extract_keywords(text, top_n=5):
    print(f"{kw.keyword}: {kw.score:.4f}")

# RAKE - best for phrase extraction
rake = RakeExtractor()
for kw in rake.extract_keywords(text, top_n=5):
    print(f"{kw.keyword}: {kw.score:.4f}")
```

### Document Ranking
```python
from efts import TfIdfRanker, rank_documents_by_keywords

docs = [
    "Warranty reserves increased significantly.",
    "Revenue growth was strong this quarter.",
    "Product liability claims declined.",
]

# Simple keyword matching
scores = rank_documents_by_keywords(docs, ["warranty", "liability"], min_hits=1)
for s in scores:
    print(f"Doc {s.index}: score={s.score}")

# TF-IDF corpus ranking
ranker = TfIdfRanker()
ranker.add_documents(docs)
keywords = ranker.extract_keywords(top_n=5)
```

## Smoke Check

```bash
EFTS_USER_AGENT="SEC NLP Tool (me@example.com)" make -C crates/efts smoke
```

## Module Exports

**Classes:**
- `EFTSClient` - Main search client
- `YakeExtractor` - YAKE keyword extraction
- `RakeExtractor` - RAKE keyword extraction
- `TextRankExtractor` - TextRank keyword extraction
- `TfIdfRanker` - TF-IDF document ranking
- `KeywordResult` - Extraction result (keyword, score)
- `DocumentScore` - Ranking result (index, score)

**Functions:**
- `create_efts_client(email, company_name, timeout)` - Factory function
- `score_document_keywords(text, keywords, case_insensitive)` - Score single doc
- `rank_documents_by_keywords(docs, keywords, case_insensitive, min_hits)` - Rank docs
