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

## Normalization boundary

Native retrieval preserves upstream URLs and publication strings, including
recurring headlines with the same title on different dates. The shared Python
`core.news.normalization` and `NewsRetriever` parse dates before ordering and
merge only canonical URLs or matching title/date identities. Undated articles
are retained and deduplicated only by URL. SEC-hosted news feeds use the shared
Python SEC transport; other feeds use the native client.
