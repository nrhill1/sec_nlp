//! # Data Retrieval and Company Information
//!
//! High-level interfaces for accessing structured SEC data such as company
//! identifiers, submission histories, and standardized financial facts.
//! This is the primary data access layer of the `edgars` crate.
//!
//! ## Overview
//!
//! The submodules wrap and normalize endpoints from the SEC’s EDGAR data APIs
//! and provide a consistent, ergonomic Rust interface:
//!
//! - [`cik`] — Fast, concurrent **ticker ↔ CIK** lookups backed by a SQLite cache
//!   and an in-process concurrent LRU. Also handles cache bootstrap/refresh.
//! - [`facts`] — Fetches and structures XBRL-reported company financial facts
//!   from the SEC’s `/company_facts` endpoint.
//! - [`submissions`] — Retrieves company filing submissions, including metadata
//!   and document indices.
//!
//! ## Exports
//!
//! Common types and functions re-exported for convenience:
//!
//! **From [`cik`]**
//! - [`open_or_refresh`] — Initialize or refresh the on-disk company index (ETag-aware).
//! - [`ticker_to_cik_db`] — Lookup CIK by ticker (cache → DB fallback).
//! - [`cik_to_detail_db`] — Lookup basic company details by CIK.
//! - [`CompanyDetail`] — Struct containing `cik`, `ticker`, and optional `title`.
//!
//! **From [`facts`]**
//! - [`fetch_company_facts`] — Download and parse structured financial (XBRL) facts.
//! - [`CompanyFacts`] — Container type for normalized facts.
//!
//! **From [`submissions`]**
//! - [`fetch_company_filings`] — Retrieve a company’s recent submission history.
//! - [`CompanySubmissions`] — Container type for recent filings.
//!
//! ## Example
//!
//! ```rust,no_run
//! use edgars::corp::{
//!     open_or_refresh, ticker_to_cik_db, cik_to_detail_db,
//!     fetch_company_facts, fetch_company_filings,
//! };
//!
//! # async fn run() -> Result<(), Box<dyn std::error::Error>> {
//! // 1) Open or refresh the local company index (SQLite).
//! let conn = open_or_refresh("./.cache/company_index.sqlite").await?;
//!
//! // 2) Resolve a ticker to its canonical 10-digit CIK.
//! let cik = ticker_to_cik_db(&conn, "AAPL")?;
//!
//! // 3) Get basic company details (ticker, title).
//! let detail = cik_to_detail_db(&conn, &cik)?;
//! println!("{} -> {} ({:?})", detail.ticker, detail.cik, detail.title);
//!
//! // 4) Pull structured XBRL facts and recent filings as needed.
//! let facts = fetch_company_facts(&detail.cik).await?;
//! let filings = fetch_company_filings(&detail.cik).await?;
//! # Ok(()) }
//! ```
//!
//! The `corp` layer is designed to be composable and efficient for read-heavy
//! multi-threaded workloads, using SQLite (WAL) for persistence and concurrent
//! in-memory caches for hot paths.

pub mod cik;
pub mod facts;
pub mod submissions;

// Re-exports: CIK index / company directory
pub use cik::{cik_to_detail_db, open_or_refresh, ticker_to_cik_db, normalize_cik, CompanyDetail};

// Re-exports: XBRL facts
pub use facts::{fetch_company_facts, CompanyFacts};

// Re-exports: submissions / filings
pub use submissions::{fetch_company_filings, CompanySubmissions};
