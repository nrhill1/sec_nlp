# EFTS parsing and ranking

This Rust/PyO3 extension parses downloaded SEC EFTS responses and provides YAKE,
RAKE, TextRank, TF-IDF, and keyword document ranking. It does not issue HTTP
requests. Native `EFTSClient`, `create_efts_client`, and `search_raw` were retired.

All SEC search, discovery, submissions, and filing requests now pass through
`sec_nlp.core.edgar.transport` with one process-wide request budget. Use the
Python `sec_nlp.core.edgar.efts.create_efts_client` facade for async search:

```python
from sec_nlp.core.edgar.efts import create_efts_client

client = create_efts_client(email="researcher@example.com")
hits = await client.search_all("warranty accrual", forms=["10-K"], max_results=100)
```

The offline native parser is `efts.parse_response_json(content, query)`. It
returns normalized JSON and retains unknown CIK/date metadata without deriving
an issuer from the accession prefix or inserting the current date. The Python
facade validates the parsed response and preserves every explicit source CIK
association before returning typed records. Entity names are attached only when
their display text explicitly identifies the matching CIK; roles remain unknown.

Ranking functions and classes retain their existing APIs:
`rank_documents_by_keywords`, `score_document_keywords`, `YakeExtractor`,
`RakeExtractor`, `TextRankExtractor`, and `TfIdfRanker`.

Build all extensions with `make build-ext`. Run fixture-only native tests with
`make rs-sg-test`. The `efts_smoke` Rust example is an offline parser check.
