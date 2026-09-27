# Analyze Pipeline

The analyze pipeline performs semantic search and LLM-driven analysis over SEC filings. It loads filings, splits and filters content, indexes embeddings when enabled, retrieves search hits, analyzes only those hits with the LLM, and writes aggregated outputs plus optional search summaries.

## Visual Flow

```mermaid
flowchart TD
  A[AnalyzePipeline.run] --> B[Setup paths and run metadata]
  B --> C{For each symbol}
  C --> D[Load filings via Loader]
  D --> E[Chunk and preprocess]
  E --> F[Compute chunk stats]
  F --> G[Vector indexing - optional]
  G --> H{Search queries or topics}
  H -- no --> I[Skip analysis]
  H -- yes --> J[Vector search retrieval]
  J --> K[LLM analysis]
  K --> L[Filter relevant and build aggregates]
  I --> M[Write output files]
  L --> M
  C -->|after all symbols| N{Search queries or topics}
  N -- yes --> O[Export search summaries - optional]
```

Implementation layout:

- `run_stages.py` orders typed specialist steps through normal Python calls.
- `runnables/` retains the optional analysis/search integration helpers.
- `steps/` groups pipeline stages (preprocess, indexing, search, analysis).
- `io/` holds output formatting/export helpers.

## How to run

Prereqs:

- Set `SEC_NLP_ANALYZE_EMAIL` (required by SEC EDGAR).
- Env prefix: `SEC_NLP_ANALYZE_`.
- Install the `ai` and `vector` extras.
- Start Ollama and pull the LLM/embedding models you plan to use. The application does not start model or container services.

Examples:

```bash
sec-nlp research analyze
sec-nlp research analyze AAPL --preset quick
sec-nlp research analyze AAPL --preset deep
sec-nlp research analyze AAPL --topics warranty --topics recall
sec-nlp research analyze AAPL --section-type item --section-numbers 1A
sec-nlp research analyze AAPL --search.queries "supply chain disruption"
```

Run `sec-nlp research analyze --help` for full options.

By default, analyze emits a compact signal-pack result set (relevance, confidence, sentiment/impact, excerpts, and query-match terms). Use `--preset deep` for full-field extraction output.
For a stable one-click production profile, use `--preset sentiment`.

Production baseline example:

```bash
sec-nlp research analyze MP LAC UUUU --preset sentiment
```

Search runs automatically when `--search.queries` is provided. If it is omitted, the pipeline falls back to `--topics` as search queries.

Search summaries are exported after all symbols when `search.export_results` is enabled; the export reuses cached search results from the analysis pass when available.

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

`run()` creates output directories, logs run metadata, then processes each symbol through an ordinary ordered step sequence. The terminal owns progress and cancellation; the specialist does not install signal handlers or print its own panels. Per-symbol outputs and stats are collected into the run metadata. While one symbol is running, the pipeline can prefetch the next `symbol_prefetch_window` symbols with isolated loader/EFTS workers so document loading and chunk preparation overlap with the active symbol.

Code: `src/sec_nlp/pipelines/presets/analyze/pipeline.py`

### 3) Load filings

For each symbol, filings are loaded via `Loader.load_documents`, applying the configured filing mode, date range, limits, and optional section filter.

Code: `src/sec_nlp/pipelines/presets/analyze/pipeline.py`

### 4) Chunk and preprocess

Documents are split into chunks and filtered. Preprocessing handles:

- Section-based extraction, sentence splitting, or semantic splitting via LangChain Experimental `SemanticChunker`.
- Length filters and empty/oversized chunk drops.
- Topic scoring and prioritization.
- SimHash-based deduplication.
- Per-filing caps and top-K selection.

Code: `src/sec_nlp/pipelines/presets/analyze/steps/preprocess/preprocess.py`

### 5) Compute chunk stats

Chunk length stats are computed and logged per accession. These feed into run metadata and diagnostics.

Code: `src/sec_nlp/pipelines/presets/analyze/pipeline.py`

### 6) Vector indexing (optional)

Chunks are indexed into Qdrant when `vector_mode` is `read` or `write`. The indexer applies SimHash deduplication to avoid re-adding similar chunks.

Code: `src/sec_nlp/pipelines/presets/analyze/steps/indexing/vector_index.py`

### 7) Vector search retrieval

If search queries (or topics when queries are empty) are configured, the pipeline retrieves candidate chunks by similarity search and applies the score threshold. Search hits are de-duplicated by content/section/symbol and annotated with `matched_queries` (query + score). Per-query results are cached for the optional summary export after the symbol loop.

Code: `src/sec_nlp/pipelines/presets/analyze/runnables/search.py`

### 8) LLM analysis

Only retrieved search hits are analyzed. The analyzer builds `AnalysisInput` items with matched query hints, context (section + topic hits), and analysis instructions, runs batched LLM calls with retries and fallback, and formats structured result dicts.

Code: `src/sec_nlp/pipelines/presets/analyze/runnables/analysis.py`

### 9) Filter relevant results + write outputs

Results are filtered by relevance and confidence threshold via `OutputFormatter`. Aggregates and diagnostics are computed and exported in the configured formats (YAML/JSON/CSV).

Code: `src/sec_nlp/pipelines/presets/analyze/io/outputs.py`, `src/sec_nlp/pipelines/presets/analyze/io/result_writer.py`

### 10) Export search results (optional)

After all symbols are processed, search results can be exported to consolidated YAML summaries with per-query sections and unique hits. The export reuses cached search results from the analysis pass when available and does not run LLM analysis.

Code: `src/sec_nlp/pipelines/presets/analyze/runnables/search.py`

### 11) Market correlation (optional)

If enabled, the pipeline computes market correlation metrics for relevant results and attaches them to the analysis output.

Code: `src/sec_nlp/pipelines/presets/analyze/runnables/market_correlation.py`

## Shared Semantic Chunking

All presets expose `semantic_chunking.*` nested settings from `BasePipelineSettings`.
Semantic chunking defaults to disabled; explicitly enable it only with the `vector`
extra and an available embedding model. Local sentence/section chunking requires no AI service.

Common CLI overrides:

- `--semantic-chunking.enabled true`
- `--semantic-chunking.embedding-model qwen3-embedding:4b`
- `--semantic-chunking.breakpoint-threshold-type gradient`
- `--semantic-chunking.max-chunk-tokens 384`

Pipelines that chunk filing text directly (`retrieve`, `exb`, `warranty`, and loader-backed `analyze`) apply these settings during chunk generation. Other presets keep the same config surface for research configuration consistency.

## Output Files

- Analysis outputs are written under:
  `<out_path>/<run_timestamp>/<pipeline_type>/<SYMBOL>/<accession>/analysis.{yaml,csv,json}`
- Search exports are written under:
  `<out_path>/<run_timestamp>/<pipeline_type>/<SYMBOL>/search/summary.yaml`

Paths are created by `AnalyzeConfig.get_symbol_output_dir` and `OutputFormatter.export`.

See also:

- `OUTPUTS_ANALYZE.md`
- `OUTPUTS_SEARCH_SUMMARY.md`

## Analyze vs Chat

`analyze` and `chat` are complementary, not competing. They serve different stages of a research workflow.

**`analyze`** is a batch, offline pipeline. It downloads filings, splits them into chunks, runs LLM analysis on every retrieved chunk, and writes structured output files (YAML/JSON/CSV) to disk. Because it calls the LLM once per chunk across many filings and symbols, it is compute-intensive and measured in minutes. The payoff is a persistent, structured record of what each filing says about your topics, with calibrated confidence scores and evidence excerpts.

**`chat`** is an interactive pipeline. It retrieves the most relevant pre-indexed chunks for a single question and calls the LLM once. It is fast (seconds) precisely because it assumes the vector index already exists.

**Recommended workflow:**

1. Run `analyze` once (or on a schedule) to download, preprocess, index, and LLM-analyze new filings.
2. Use `chat` for real-time, ad-hoc questions against the content that `analyze` already indexed.

If you find `analyze` too slow, consider:

- Enabling the LLM response cache (`--llm-response-cache`) so chunks analyzed in a previous run are served from disk on re-runs. This dramatically reduces inference time when filings overlap between runs.
- Increasing `--symbol-prefetch-window` when you run multi-symbol batches. This keeps the next symbols staged without making the full symbol stage chain concurrent.
- Using `--preset quick` or `--preset sentiment` to reduce the prompt and field set.
- Setting `OLLAMA_NUM_PARALLEL=2` (or higher) in your environment to allow Ollama to process multiple chunks concurrently.
- Running `analyze` in the background or overnight for large symbol sets, then using `chat` during the day.

## Key Config Gates

- `search.queries` (or `topics` when queries are empty) must be set to retrieve hits and run analysis.
- `vector_mode` must be `read` or `write` if search is enabled.
- `search.analyze_limit` caps the number of hits analyzed per query (search export can still include the full retrieved set).
- `search.export_results` controls whether search summaries are written after the run.
- `confidence_threshold` controls what is considered relevant in outputs.
- `analysis_fields` controls which fields are requested from the LLM prompt.
- `analysis_instruction_style=compact` reduces prompt token overhead for faster, sentiment-focused runs.
