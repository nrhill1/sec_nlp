# crate: `crates/embed` — ONNX-Based Batch Embedding Engine

## Purpose

Run embedding models locally via ONNX Runtime for high-throughput batch workloads, bypassing the Python/Ollama HTTP overhead. Feeds the `retrieve` pipeline's embed step and any future vector-search workflows.

## Existing Implementations — Build vs. Reuse

**`fastembed-rs`** (crates.io, ~23K downloads/month) is a complete Rust embedding library built on `ort` + HuggingFace `tokenizers`. It already supports BGE-small/base/large, MiniLM, GTE, mpnet, and more — including quantized variants. Batch embedding with configurable batch size is built in. Also provides reranking models. Apache-2.0 licensed.

**`ort`** (crates.io) is the canonical Rust wrapper for ONNX Runtime. Hardware-accelerated inference on CPU/CUDA/TensorRT/OpenVINO. Used by HuggingFace TEI, SurrealDB, Google Magika, and fastembed-rs itself.

**`rust-bert`** (crates.io) provides sentence embeddings via `SentenceEmbeddingsBuilder` using tch-rs or ONNX backend. Heavier than fastembed-rs and pulls in libtorch.

**Recommendation: Wrap `fastembed-rs`, don't rewrite.** `fastembed-rs` already implements the core functionality (model loading, tokenization, batch inference, normalization) with production-grade quality. This crate becomes a thin PyO3 wrapper that:
1. Exposes `EmbeddingEngine` as a `#[pyclass]` wrapping `fastembed::TextEmbedding`.
2. Adds model path configuration (support loading from a user-specified directory rather than only HuggingFace Hub).
3. Adds memory-mapped output for zero-copy access from Python (optional).
4. Adds the build.rs / Makefile plumbing to integrate with the sec-nlp build system.

Only fall back to raw `ort` + `tokenizers` if `fastembed-rs` proves insufficient (e.g., missing model architecture support or inflexible batching).

## Existing Code to Study

- `crates/efts/src/lib.rs` — reference PyO3 module structure.
- `crates/efts/build.rs` — Python linking setup.
- `crates/efts/Makefile` — maturin develop commands.
- `src/sec_nlp/pipelines/vector/` — existing Qdrant integration that consumes embeddings.

## File Structure

```
crates/embed/
├── Cargo.toml
├── Makefile
├── build.rs
├── src/
│   ├── lib.rs            # PyO3 module: register EmbeddingEngine class
│   ├── engine.rs         # EmbeddingEngine: wraps fastembed::TextEmbedding
│   ├── config.rs         # Model path, batch size, thread count config
│   └── error.rs          # EmbedError type
└── tests/
    └── test_engine.rs
```

## Key API (PyO3)

```rust
// engine.rs
#[pyclass]
struct EmbeddingEngine {
    model: TextEmbedding,
}

#[pymethods]
impl EmbeddingEngine {
    /// Create a new engine.
    /// `model_name`: one of "bge-small-en-v1.5", "all-MiniLM-L6-v2", etc.
    /// `model_dir`: optional local path to ONNX model directory (overrides HF Hub download).
    /// `threads`: ONNX Runtime intra-op thread count (default: num_cpus / 2).
    #[new]
    fn new(model_name: &str, model_dir: Option<String>, threads: Option<usize>) -> PyResult<Self>;

    /// Embed a batch of text strings. Returns list of float vectors.
    fn embed_batch(&self, texts: Vec<String>, batch_size: Option<usize>) -> PyResult<Vec<Vec<f32>>>;

    /// Embed a single text. Convenience wrapper.
    fn embed(&self, text: &str) -> PyResult<Vec<f32>>;

    /// Return the embedding dimension for the loaded model.
    fn dimension(&self) -> usize;
}
```

## Dependencies (Cargo.toml)

```toml
[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
fastembed = "4"         # Core embedding engine — wraps ort + tokenizers
```

`ort` and `tokenizers` are transitive dependencies via `fastembed`. No need to declare them directly unless customizing execution providers.

## Implementation Steps

1. **Scaffold the crate.** Copy boilerplate from `crates/efts/`: `Cargo.toml` (`crate-type = ["cdylib"]`), `build.rs`, `Makefile`. Add `fastembed` dependency.

2. **Implement `config.rs`.** Struct with `model_name: String`, `model_dir: Option<PathBuf>`, `batch_size: usize`, `threads: usize`. Map `model_name` strings to `fastembed::EmbeddingModel` enum variants.

3. **Implement `engine.rs`.** `EmbeddingEngine::new()` creates a `fastembed::TextEmbedding` via `TextEmbedding::try_new(InitOptions::new(model).with_cache_dir(dir))`. `embed_batch()` calls `model.embed(documents, Some(batch_size))`. Normalize is handled by fastembed internally.

4. **Implement `error.rs`.** `EmbedError` wrapping fastembed/ort errors, convertible to `PyErr`.

5. **Register in `lib.rs`.** `#[pymodule]` that adds `EmbeddingEngine` class.

6. **Add to root Makefile.** `EMBED_DIR`, `EMBED_MANIFEST`, `rs-embed-%` target, include in `build-ext`.

7. **Write Python wrapper** (`src/sec_nlp/core/embed/engine.py`). Lazy-import the `embed` module. Expose `get_embedding_engine(model_name, **kwargs) -> EmbeddingEngine`. Follow the `_load_market_module()` pattern from `src/sec_nlp/core/market.py`.

8. **Add type stubs** (`types/embed/__init__.pyi`).

9. **Write tests.** Rust: load a small model (MiniLM-L6-v2), embed a few strings, verify output shape and that cosine similarity between semantically similar strings is > threshold. Python: mock the extension, test wrapper layer. Note: tests that load ONNX models require model files — gate behind a `#[cfg(feature = "integration")]` flag or download fixture in CI.

## Testing Strategy

- Rust unit tests: verify config parsing, model name → enum mapping, error handling for invalid model names.
- Rust integration tests (gated): load actual ONNX model, embed known strings, verify dimension and approximate similarity.
- Python tests: mock the `embed` native module, verify wrapper passes correct arguments and handles errors.
- No network in unit tests — integration tests that download models should be opt-in.

## Performance Target

- 500–2,000 chunks/sec on CPU for 384-dim model (BGE-small) with batch_size=64.
- This is 10–40x faster than Ollama HTTP round-trips (~50–100/sec) observed in the current analyze pipeline.
