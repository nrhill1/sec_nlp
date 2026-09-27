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

`NewsClient.fetch_async` returns a cancellable Python awaitable; cancellation
drops the native HTTP future. The synchronous `fetch` method releases Python's
interpreter lock while waiting. Native feeds use a five-second connection
timeout and a twenty-second total deadline including retries. Only connection,
timeout/body failures, HTTP 429, and HTTP 5xx permit one retry, after a half-second
delay. Invalid URLs, parsing failures, and other HTTP failures stop immediately.
The adapter awaits `wait_idle_async()` after cancellation to acknowledge native
request cleanup before reporting completion to the workspace.

`NewsRetriever.fetch_async` shares an existing `SecTransport` for SEC feeds.
Pulse owns the combined four-source concurrency limit and persists each source
outcome as soon as it completes, independently from the final report snapshot.
