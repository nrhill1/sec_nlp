# Analyze Pipeline

The analyze pipeline performs semantic search + LLM-driven analysis over SEC filings. It loads filings, chunks and filters content, optionally indexes embeddings, retrieves search hits, runs LLM analysis, and writes aggregated outputs.

## Visual Flow

```mermaid
flowchart TD
  A[AnalyzePipeline.run] --> B[Setup paths + run metadata]
  B --> C{For each symbol}
  C --> D[Load filings (Loader)]
  D --> E[Chunk + preprocess]
  E --> F[Vector indexing (optional)]
  F --> G{Search enabled + queries}
  G -- no --> H[Skip analysis]
  G -- yes --> I[Vector search retrieval]
  I --> J[LLM analysis]
  J --> K[Filter relevant + compute stats]
  K --> L[Write output files]
  C -->|after all symbols| M{Search enabled}
  M --> N[Export search results]
```

## How to run

Prereqs:
- Set `ANALYZE_EMAIL` (required by SEC EDGAR).
- Start Ollama and pull the LLM/embedding models you plan to use.

Examples:
```
sec-nlp analyze
sec-nlp analyze AAPL --preset quick
sec-nlp analyze AAPL --topics warranty --topics recall
sec-nlp analyze AAPL --section-type item --section-numbers 1A
sec-nlp analyze AAPL --search.queries "supply chain disruption"
```

Run `sec-nlp analyze --help` for full options.

Search runs automatically when `--search.queries` is provided.

## Major Steps

### 1) Build components
The pipeline constructs all required components from config in `_build_components`.
- Loader with filing download settings and keyword filtering.
- Optional section filter + extractor for targeted sections.
- Prompt template and analysis instructions based on `analysis_fields`.
- LLM graph runnable and tracing callbacks.
- Vector store (Qdrant) initialization and collection checks.
- Preprocessor, vector indexer, search runner, analysis runner, and output formatter.

Code: `src/sec_nlp/pipelines/presets/analyze/pipeline.py`

### 2) Run setup and symbol loop
`run()` creates output directories, logs run metadata, then processes each symbol sequentially with a progress bar. Per-symbol outputs and stats are collected into the run metadata.

Code: `src/sec_nlp/pipelines/presets/analyze/pipeline.py`

### 3) Load filings
For each symbol, filings are loaded via `Loader.load_documents`, applying the configured filing mode, date range, limits, and optional section filter.

Code: `src/sec_nlp/pipelines/presets/analyze/pipeline.py`

### 4) Chunk and preprocess
Documents are split into chunks and filtered. Preprocessing handles:
- Section-based extraction or sentence splitting.
- Length filters and empty/oversized chunk drops.
- Topic scoring and prioritization.
- SimHash-based deduplication.
- Per-filing caps and top-K selection.

Code: `src/sec_nlp/pipelines/presets/analyze/preprocess.py`

### 5) Compute chunk stats
Chunk length stats are computed and logged per accession. These feed into run metadata and diagnostics.

Code: `src/sec_nlp/pipelines/presets/analyze/pipeline.py`

### 6) Vector indexing (optional)
Chunks are indexed into Qdrant when `vector_mode` is `read` or `write`. The indexer applies SimHash deduplication to avoid re-adding similar chunks.

Code: `src/sec_nlp/pipelines/presets/analyze/vector_index.py`

### 7) Vector search retrieval
If search is enabled and queries are configured, the pipeline retrieves candidate chunks by similarity search and applies the score threshold. Search hits are de-duplicated by content/section/symbol and annotated with `search_query` and `search_score` metadata.

Code: `src/sec_nlp/pipelines/presets/analyze/vector_search.py`

### 8) LLM analysis
Only retrieved search hits are analyzed. The analyzer builds `AnalysisInput` items with context (section + topic hits), runs batched LLM calls with retries and fallback, and formats structured result dicts.

Code: `src/sec_nlp/pipelines/presets/analyze/analysis_runner.py`

### 9) Filter relevant results + write outputs
Results are filtered by relevance and confidence threshold via `OutputFormatter`. Aggregates and diagnostics are computed and exported in the configured formats (YAML/JSON/CSV).

Code: `src/sec_nlp/pipelines/presets/analyze/outputs.py`, `src/sec_nlp/pipelines/presets/analyze/result_writer.py`

### 10) Export search results (optional)
After all symbols are processed, search results can be exported to YAML summaries (this export does not run LLM analysis).

Code: `src/sec_nlp/pipelines/presets/analyze/vector_search.py`

## Output Files

- Analysis outputs are written under:
  `<out_path>/<SYMBOL>/<pipeline_type>/<run_id>/<accession>/analysis.{yaml,csv,json}`
- Search exports are written under:
  `<out_path>/<SYMBOL>/<pipeline_type>/<run_id>/search/<query_slug>.yaml`

Paths are created by `AnalyzeConfig.get_symbol_output_dir` and `OutputFormatter.export`.

## Key Config Gates

- `search.queries` must be set to retrieve hits and run analysis.
- `vector_mode` must be `read` or `write` if search is enabled.
- `confidence_threshold` controls what is considered relevant in outputs.
- `analysis_fields` controls which fields are requested from the LLM prompt.
