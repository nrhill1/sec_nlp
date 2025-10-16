// src/data/mod.rs - Data retrieval and company information
pub mod cik;
pub mod facts;
pub mod submissions;

pub use cik::{get_ticker_map, normalize_cik};
pub use facts::{fetch_company_facts, CompanyFacts};
pub use submissions::{fetch_company_filings, CompanySubmissions};
