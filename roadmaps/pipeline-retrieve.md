# pipeline: `retrieve` — EFTS-to-Vector Retrieval Pipeline

## Purpose

Combine EFTS lexical search with embedding-based re-ranking to return the most relevant filing accessions and sections for arbitrary queries. Two-stage architecture: cheap EFTS first pass → embed surviving chunks → ANN search.

## Existing Implementations — Build vs. Reuse

**LlamaIndex** (PyPI) provides a complete RAG framework with document loaders, chunking, embedding, vector indexing, and retrieval. Supports many vector stores and embedding providers. However, it is a heavy dependency (~100+ transitive packages), opinionated about its own Document/Node model, and its EDGAR support is limited to a basic SEC loader.

**LangChain** (PyPI) provides similar RAG capabilities with a different abstraction layer. Same trade-offs: heavy, opinionated models, significant API churn.

**Haystack** (PyPI, `deepset-ai/haystack`) is another RAG framework with retriever/reader pipelines. Mature but heavyweight.

**Recommendation: Custom pipeline using our own components.** We already have `crates/efts` for lexical search, `crates/embed` for batch embedding, existing Qdrant integration (`sec_nlp.pipelines.vector`), and the chunking/section extraction modules. Pulling in LlamaIndex/LangChain would duplicate all of this and introduce model conflicts. The pipeline is a thin orchestration layer connecting our existing pieces. The two-stage EFTS→embed architecture is specifically designed for SEC filing scale (millions of documents) and cannot be replicated by off-the-shelf RAG frameworks that assume you embed everything upfront.

## Existing Code to Study

- `crates/efts/` — EFTS search, `batch_search_async`.
- `src/sec_nlp/pipelines/vector/` — existing Qdrant integration.
- `src/sec_nlp/core/text/chunking.py` — existing text chunking.
- `src/sec_nlp/core/text/section_extractor.py` — section extraction (Item 1A, Item 7, etc.).
- `src/sec_nlp/core/ingest/downloader.py` — filing download.

## File Structure

```
src/sec_nlp/pipelines/presets/retrieve/
├── __init__.py
├── config.py           # RetrieveSettings(BasePipelineSettings)
├── models.py           # RetrievalHit, RetrievalResult
├── pipeline.py         # RetrievePipeline(BasePipeline)
├── steps/
│   ├── __init__.py
│   ├── candidate_search.py  # EFTS queries to narrow candidates
│   ├── download_chunk.py    # Download filings, chunk by section
│   ├── embed.py             # Batch-embed chunks via crates/embed
│   ├── index.py             # Upsert into Qdrant
│   └── query.py             # Embed query, ANN search, return ranked hits
└── io/
    ├── __init__.py
    └── formats/
        ├── __init__.py
        └── ranked_results.py  # JSON/YAML ranked result list
```

## Pipeline Steps

### 1. `candidate_search`
Execute EFTS queries via `crates/efts` with broad filters (form types, date range, tickers). Use `batch_search_async` for multiple queries in parallel. Target: top 200–500 hits per query. Returns accession numbers + snippets.

### 2. `download_chunk`
For each candidate accession, download the filing (if not cached) and chunk using `sec_nlp.core.text.chunking`. Section extraction (`section_extractor.py`) limits to specific items (e.g., Item 1A, Item 7) to reduce chunk volume.

### 3. `embed`
Batch-embed all candidate chunks using `crates/embed` via the Python wrapper. If a persistent Qdrant collection already contains embeddings for a given `(accession, chunk_index)`, skip re-embedding (incremental indexing).

### 4. `index`
Upsert embeddings into Qdrant using `sec_nlp.pipelines.vector`. Payloads: accession_number, section, chunk_index, filing_date, ticker, form_type. Use existing Qdrant client configuration.

### 5. `query`
Embed user's query strings via `crates/embed`. Run ANN search against indexed chunks. Apply metadata filters (date range, form type) at query time via Qdrant payload filters. Return ranked `RetrievalHit` list.

### 6. `output`
Return matched accessions with per-chunk relevance scores, section references, and text snippets. Output: JSON/YAML ranked list, or feed into `analyze` pipeline as pre-filtered input.

## Config (Pydantic)

```python
class RetrieveSettings(BasePipelineSettings):
    model_config = SettingsConfigDict(env_prefix="SEC_NLP_RETRIEVE_")
    queries: list[str]
    tickers: list[str] = []
    form_types: list[str] = ["10-K", "10-Q"]
    date_start: str = ""
    date_end: str = ""
    sections: list[str] = []          # e.g. ["1A", "7"] — empty = all
    top_k: int = 20
    efts_candidates: int = 500        # Max EFTS hits per query
    embedding_model: str = "bge-small-en-v1.5"
    embedding_batch_size: int = 64
    qdrant_collection: str = "sec_retrieve"
    output_format: str = "json"
```

## CLI Command

```
sec-nlp retrieve "supply chain disruption" --tickers AAPL MSFT --forms 10-K 10-Q --top-k 20
```

## Scaling Strategies

**Incremental index build:** Each pipeline run adds new accessions to the persistent Qdrant collection. Chunks keyed by `(accession_number, chunk_index)` — re-runs are idempotent.

**Tiered storage:** Qdrant's on-disk index mode for collections exceeding RAM. HNSW params: m=16, ef_construct=128.

**Quantization:** Qdrant scalar quantization cuts memory ~4x for 384-dim BGE embeddings with minimal recall loss.

**Embedding cache:** Store computed embeddings as sidecar files alongside downloads (`downloads/.embeddings.bin`). The embed step checks for this file before calling ONNX.

## Implementation Steps

- [x] Create `retrieve/` directory with boilerplate.
- [x] Implement `RetrievalHit` and `RetrievalResult` Pydantic models.
- [x] Implement `candidate_search.py` — wrap EFTS batch search flow.
- [ ] Implement `download_chunk.py` — download + chunk, respecting section filters. (currently passthrough placeholder)
- [ ] Implement `embed.py` — call `crates/embed` wrapper, skip already-indexed chunks. (currently passthrough placeholder)
- [ ] Implement `index.py` — Qdrant upsert with payload metadata. (currently passthrough placeholder)
- [x] Implement `query.py` ranking step and top-k assembly from EFTS candidates.
- [x] Implement pipeline orchestration and output writing (JSON/YAML/CSV + run metadata headers).
- [x] Add `retrieve` CLI command, register in `root.py` and `__main__.py` arg normalization.
- [x] Write tests with mocked search/pipeline wiring and ranking behavior (no network).

## Dependencies

- `crates/efts` (existing)
- `crates/embed` (via `sec_nlp.core.embed.engine`)
- Existing Qdrant integration (`sec_nlp.pipelines.vector`)
- Existing chunking/section extraction
- No new PyPI dependencies
