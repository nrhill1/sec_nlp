# Data Source Expansion Implementation
This plan covers three features in order: EFTS integration, filing cross-referencing, and additional filing type support.
## Current State
* Filings downloaded via `sec_edgar_downloader` library
* Local vector search via Qdrant for semantic retrieval
* `FilingMode` enum already defines `proxy` (DEF 14A) and `holdings` (13F-HR) but pipelines only fully support annual/quarterly/current
* No integration with SEC's EDGAR Full-Text Search API
* No mechanism to link related filings (e.g., 10-K to related 8-Ks)
## Feature 1: EDGAR Full-Text Search (EFTS) Integration
### Overview
Integrate with SEC's EFTS API (`https://efts.sec.gov/LATEST/search-index`) to expand search beyond locally-downloaded filings. This enables discovering relevant filings before downloading them.
### Implementation
**1.1 Create EFTS client module**
* Location: `src/sec_nlp/core/edgar/efts.py`
* Pydantic models for request/response payloads
* Async HTTP client with rate limiting (10 req/sec per SEC guidelines)
* Search parameters: keywords, form types, date range, CIK
**1.2 EFTS search result models**
* Location: `src/sec_nlp/core/edgar/efts_models.py`
* `EFTSSearchParams` - search input configuration
* `EFTSHit` - individual search result (accession, form, filed date, snippet)
* `EFTSSearchResponse` - paginated response wrapper
**1.3 Hybrid search integration**
* Location: `src/sec_nlp/pipelines/presets/analyze/steps/search/efts_search.py`
* Combine local vector search with EFTS for broader coverage
* Score fusion: normalize and merge results from both sources
* Automatic download trigger for high-scoring EFTS hits not yet local
**1.4 CLI integration**
* Add `--efts` / `--efts-enabled` flag to analyze pipeline
* Add `--efts-limit` for max EFTS results to fetch
* New standalone command: `sec-nlp efts <query>` for direct EFTS queries
**1.5 Configuration**
* Add `EFTSConfig` to `AnalyzeConfig` with enable flag, limits, score threshold
### Files to Create
* `src/sec_nlp/core/edgar/efts.py`
* `src/sec_nlp/core/edgar/efts_models.py`
* `src/sec_nlp/pipelines/presets/analyze/steps/search/efts_search.py`
* `src/sec_nlp/cli/commands/efts.py`
* `tests/core/edgar/test_efts.py`
### Files to Modify
* `src/sec_nlp/core/edgar/__init__.py` - export EFTS client
* `src/sec_nlp/pipelines/presets/analyze/config.py` - add EFTS config
* `src/sec_nlp/pipelines/presets/analyze/pipeline.py` - integrate EFTS search
* `src/sec_nlp/cli/main.py` - register efts command
## Feature 2: Cross-Referencing Filings
### Overview
Link related filings to build fuller timelines. E.g., connect a 10-K with 8-Ks filed in the same period, or link amendments (10-K/A) to originals.
### Implementation
**2.1 Filing relationship models**
* Location: `src/sec_nlp/core/edgar/relationships.py`
* `FilingRelationType` enum: `AMENDMENT`, `SAME_PERIOD`, `EXHIBIT_REFERENCE`, `SUPERSEDES`
* `FilingRelation` model linking two accession numbers with relationship type
**2.2 Relationship resolver**
* Location: `src/sec_nlp/core/edgar/relationship_resolver.py`
* Parse filing headers for references to other filings
* Use SEC EDGAR filing index to find same-period filings
* Detect amendments via form type suffix (10-K/A, 8-K/A)
**2.3 Cross-reference metadata enrichment**
* Add `related_filings` field to document metadata during loading
* Store relationship graph in run metadata for downstream use
**2.4 Timeline view**
* New output format showing filings grouped by relationship
* CLI flag `--show-timeline` to display related filings
### Files to Create
* `src/sec_nlp/core/edgar/relationships.py`
* `src/sec_nlp/core/edgar/relationship_resolver.py`
* `tests/core/edgar/test_relationships.py`
### Files to Modify
* `src/sec_nlp/core/edgar/__init__.py` - export relationship types
* `src/sec_nlp/core/ingest/loader.py` - enrich metadata with relationships
* `src/sec_nlp/pipelines/presets/analyze/io/outputs.py` - timeline output format
## Feature 3: Additional Filing Type Support
### Overview
`FilingMode` already defines `proxy` and `holdings`. Ensure full pipeline support and add S-1/S-3 registration statements.
### Implementation
**3.1 Extend FilingMode**
* Add `registration` mode for S-1/S-3 filings
* Update `form` property to return appropriate form type
**3.2 Filing-specific section patterns**
* Location: `src/sec_nlp/core/text/section_patterns.py`
* DEF 14A: executive compensation, proposal sections
* 13F-HR: holdings table extraction
* S-1/S-3: risk factors, use of proceeds, business description
**3.3 Pipeline preset support**
* Validate all pipelines handle new filing modes gracefully
* Add filing-mode-specific default topics/keywords where appropriate
**3.4 13F holdings parser**
* Location: `src/sec_nlp/core/edgar/holdings_parser.py`
* Parse 13F XML/HTML to extract structured holdings data
* Return as Documents with position metadata (CUSIP, shares, value)
### Files to Create
* `src/sec_nlp/core/text/section_patterns.py`
* `src/sec_nlp/core/edgar/holdings_parser.py`
* `tests/core/edgar/test_holdings_parser.py`
### Files to Modify
* `src/sec_nlp/core/edgar/filing_mode.py` - add registration mode
* `src/sec_nlp/core/text/filters.py` - add section patterns for new types
* `src/sec_nlp/pipelines/presets/analyze/config.py` - mode-specific defaults
## Implementation Order
1. Feature 1 (EFTS) - Provides foundation for discovering filings
2. Feature 2 (Cross-referencing) - Builds on EFTS to link discovered filings
3. Feature 3 (Filing types) - Extends coverage to more SEC forms
## Testing Strategy
* Unit tests for each new module with mocked HTTP responses
* Integration tests using sample SEC responses (fixtures)
* E2E test with real SEC API calls (marked slow, optional in CI)
