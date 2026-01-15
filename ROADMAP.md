# Roadmap

Potential next steps and new features for sec-nlp.

## ~~Data Source Expansion~~
- ~~**Additional filing types**: Support for proxy statements (DEF 14A), S-1/S-3 registration statements, or 13F holdings reports~~
- ~~**Cross-referencing filings**: Link related filings (e.g., 10-K with related 8-Ks) to build fuller timelines~~
- ~~**EDGAR full-text search integration**: Combine local vector search with SEC's EFTS API for broader coverage~~

## ~~Analysis Enhancements~~
- ~~**Multi-filing comparative analysis**: Compare language changes between consecutive 10-Ks (diff analysis, risk factor evolution)~~
- ~~**Peer comparison**: Analyze the same topic/section across multiple companies in a sector~~
- ~~**Sentiment trend tracking**: Track sentiment shifts in risk disclosures or MD&A sections over time~~
- ~~**Entity extraction pipeline**: Dedicated pipeline for named entities (people, companies, contracts, dates)~~

## New Domain Pipelines
- **Insider transactions** (`Form 4`): Track insider buying/selling signals
- **Executive compensation** (proxy DEF 14A): Extract comp structures, peer benchmarks
- **Material contracts expansion**: Beyond Exhibit 10, analyze other exhibits (Exhibit 21 subsidiaries, Exhibit 23 consents)
- **Risk factor clustering**: Group and categorize risk factors across companies

## Technical Improvements
- **Incremental indexing**: Detect new filings and add only deltas to vector store
- **Multi-model ensemble**: Run multiple LLMs and aggregate/vote on results for higher confidence
- **RAG pipeline with chat interface**: Interactive Q&A over indexed filings
- **Caching layer**: Cache LLM responses for repeated queries on same content
- **Scheduled runs**: Cron/scheduler integration to auto-process new filings

## Output & Integration
- **Alerting system**: Notify when specific signals appear (e.g., new risk factor, warranty spike)
- **Dashboard/visualization**: Web UI for browsing run results and trends
- **Export to financial data formats**: Integration with pandas/Parquet for quantitative analysis
- **Webhook/API mode**: Expose analysis as a service for downstream apps
