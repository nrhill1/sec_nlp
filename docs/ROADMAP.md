# Roadmap

Potential next steps and new features for sec-nlp.

## ~~Data Source Expansion~~
- ~~**Additional filing types**: Support for proxy statements (DEF 14A), S-1/S-3 registration statements, or 13F holdings reports~~
- ~~Implementation: Added filing modes for proxy/holdings/registration with loader routing, proxy/holdings prompt defaults, and registration section patterns.~~
  - ~~Coverage: DEF 14A, 13F-HR, S-1, and S-3 supported via FilingMode mapping.~~
- ~~**Cross-referencing filings**: Link related filings (e.g., 10-K with related 8-Ks) to build fuller timelines~~
  - ~~Implementation: RelationshipResolver builds related-filing graphs and Loader attaches related_filings metadata.~~
  - ~~Outputs: Relationship timelines flow into analysis outputs and optional logs when enabled.~~
- ~~**EDGAR full-text search integration**: Combine local vector search with SEC's EFTS API for broader coverage~~
  - ~~Implementation: EFTS search merges with local vector search and supports score thresholds + date-range expansion.~~
  - ~~Auto-download: Optional download of new accessions with filtering to matching filings.~~

## ~~Analysis Enhancements~~
- ~~**Multi-filing comparative analysis**: Compare language changes between consecutive 10-Ks (diff analysis, risk factor evolution)~~
  - ~~Implementation: Symbol summaries include filing-to-filing deltas (tags, impact channels, sentiment shift).~~
  - ~~Utilities: Text diff helpers available for deeper comparisons.~~
- ~~**Peer comparison**: Analyze the same topic/section across multiple companies in a sector~~
  - ~~Implementation: Peer summary output highlights common tags and net sentiment ranking across symbols.~~
- ~~**Sentiment trend tracking**: Track sentiment shifts in risk disclosures or MD&A sections over time~~
  - ~~Implementation: Sentiment trend rows per accession in analysis summaries.~~
- ~~**Entity extraction pipeline**: Dedicated pipeline for named entities (people, companies, contracts, dates)~~
  - ~~Implementation: LLM outputs extracted_entities with entity rollups in symbol summaries.~~

## ~~New Domain Pipelines~~
- ~~**Insider trading info extraction** (`Form 3`/`Form 4`): Track insider buying/selling signals~~
  - ~~Sources: Forms 3/4 XML, issuer/insider identifiers, 10b5-1 flags~~
  - ~~Extract: transaction codes, dates, prices, shares, ownership type, initial holdings, direct vs indirect ownership, relationship to issuer, derivative vs non-derivative, nature of ownership, security title, conversion/exercise price, transaction type (open market vs grant), ownership footnotes, transaction ID~~
  - ~~Outputs: net-buying signals, cluster-buy detection, alert hooks~~
  - ~~Implementation: InsiderParser maps derivative/non-derivative tables into structured transaction docs with footnotes and role metadata.~~
  - ~~Modes: analyze pipeline supports insider mode (Forms 3/4) for search + analysis.~~
- ~~**Risk factor clustering**: Group and categorize risk factors across companies~~
  - ~~Sources: 10-K risk factors and 10-Q updates~~
  - ~~Extract: clause-level risk statements, themes, sector tags~~
  - ~~Outputs: taxonomy clusters, novelty signals, peer comparisons~~
  - ~~Implementation: SimHash-based clustering with labels, novelty flags, and example statements.~~
- ~~**Material contracts expansion**: Beyond Exhibit 10, analyze other exhibits (Exhibit 21 subsidiaries, Exhibit 23 consents)~~
  - ~~Sources: exhibit index and selected exhibits (21, 23, 99, 101)~~
  - ~~Extract: subsidiary lists, auditor consents, key obligations, counterparties~~
  - ~~Outputs: structured exhibit summaries, coverage gaps, change tracking~~
  - ~~Implementation: Exhibit pipeline pulls exhibits 10/21/23/99/101 and emits coverage gap summaries.~~
- ~~**Executive compensation** (proxy DEF 14A): Extract comp structures, peer benchmarks~~
  - ~~Sources: DEF 14A tables (SCT, grants, exercises) and CD&A narrative~~
  - ~~Extract: base/bonus/equity breakdown, performance metrics, peer sets~~
  - ~~Outputs: YoY comp changes, pay-for-performance flags, peer deltas~~
  - ~~Implementation: Executive comp summaries include YoY deltas and peer benchmark rollups.~~

## Technical Improvements
- ~~**Incremental indexing**: Detect new filings and add only deltas to vector store~~
  - ~~Implementation: `retrieve` indexing now checks existing Qdrant point IDs and skips already-indexed hits before embedding/upsert.~~
- **Multi-model ensemble**: Run multiple LLMs and aggregate/vote on results for higher confidence
- **RAG pipeline with chat interface**: Interactive Q&A over indexed filings
- **Caching layer**: Cache LLM responses for repeated queries on same content

## Output & Integration
- **Alerting system**: Notify when specific signals appear (e.g., new risk factor, warranty spike)
- **Dashboard/visualization**: Web UI for browsing run results and trends
- **Export to financial data formats**: Integration with pandas/Parquet for quantitative analysis
- **Webhook/API mode**: Expose analysis as a service for downstream apps
