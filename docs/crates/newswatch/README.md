# newswatch

Rust/PyO3 extension for news ingestion and filtering utilities used by the news pipeline.

## Exported Python API

Classes:
- `NewsClient`
- `NewsItem`

## Build

```bash
maturin develop -m crates/newswatch/Cargo.toml
```

Or from repo root:

```bash
make build-ext
```
