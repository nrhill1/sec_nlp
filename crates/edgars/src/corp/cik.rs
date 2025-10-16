//! Company index and CIK (Central Index Key) utilities.
//!
//! Provides fast, concurrent lookups between tickers and CIKs,
//! backed by a persistent SQLite cache and concurrent LRU in-memory caches.
//!
//! ## Exports
//!
//! **Structs**
//! - [`CompanyDetail`] — basic company record (CIK, ticker, title).
//!
//! **Constants**
//! - [`TICKER_CACHE_CAP`] — max in-memory entries for ticker → CIK cache.
//! - [`CIK_CACHE_CAP`] — max in-memory entries for CIK → detail cache.
//!
//! **Functions**
//! - [`open_or_refresh`] — opens/creates and refreshes the local SQLite cache (ETag-aware).
//! - [`ticker_to_cik_db`] — lookup CIK by ticker (cache + DB fallback).
//! - [`cik_to_detail_db`] — lookup company detail by CIK (cache + DB fallback).
//!
//! ## Notes
//! - Data source: <https://www.sec.gov/files/company_tickers.json>
//! - Uses `moka::Cache` for concurrent, auto-evicting LRU-like caching.
//! - Uses SQLite WAL mode for persistence and multi-thread read safety.
//! - Uses conditional GETs with ETag to minimize network and parsing overhead.
//!
//! This module is threadsafe when each thread uses its own SQLite connection
//! (e.g., via an r2d2 connection pool) and shares the in-process caches.

use std::fs;
use std::path::PathBuf;

use moka::sync::Cache;
use once_cell::sync::Lazy;
use rusqlite::{params, Connection, OptionalExtension, ToSql};
use serde::Deserialize;
use crate::errors::{EdgarError, Result};

const SEC_TICKERS_URL: &str = "https://www.sec.gov/files/company_tickers.json";

/// Cache capacities (number of entries).
pub const TICKER_CACHE_CAP: u64 = 32_000;
pub const CIK_CACHE_CAP: u64 = 32_000;

/// Core company details stored in cache and database.
#[derive(Debug, Clone)]
pub struct CompanyDetail {
    pub cik: String,           // 10-digit, zero-padded
    pub ticker: String,        // uppercased
    pub title: Option<String>, // company name
}

/// JSON entry in `company_tickers.json`.
#[derive(Debug, Deserialize)]
struct TickerEntry {
    cik_str: u64,
    ticker: String,
    title: Option<String>,
}

/// Concurrent, auto-evicting caches (Window-TinyLFU).
static TICKER_CACHE: Lazy<Cache<String, String>> =
    Lazy::new(|| Cache::builder().max_capacity(TICKER_CACHE_CAP).build());
static CIK_CACHE: Lazy<Cache<String, CompanyDetail>> =
    Lazy::new(|| Cache::builder().max_capacity(CIK_CACHE_CAP).build());

/// Open (or create) the SQLite cache, ensuring it is up to date.
/// Use this once during initialization.
pub async fn open_or_refresh(db_path: impl Into<PathBuf>) -> Result<Connection> {
    let db_path = db_path.into();
    if let Some(parent) = db_path.parent() {
        if !parent.exists() {
            fs::create_dir_all(parent)?;
        }
    }

    let mut conn = Connection::open(&db_path)?;
    conn.pragma_update(None, "journal_mode", &"WAL")?;
    conn.pragma_update(None, "synchronous", &"NORMAL")?;
    init_schema(&mut conn)?;

    let current_etag = get_meta(&conn, "etag")?;

    Ok(conn)
}

/// Lookup: ticker → CIK (case-insensitive).
/// Checks cache first, then database, then caches the result.
pub fn ticker_to_cik_db(conn: &Connection, ticker: &str) -> Result<String> {
    let t_up = ticker.to_ascii_uppercase();

    if let Some(hit) = TICKER_CACHE.get(&t_up) {
        return Ok(hit);
    }

    let cik: Option<String> = conn
        .query_row("SELECT cik FROM company WHERE ticker = ?1", params![t_up], |row| {
            row.get(0)
        })
        .optional()?;

    match cik {
        Some(cik) => {
            TICKER_CACHE.insert(t_up, cik.clone());
            Ok(cik)
        }
        None => Err(EdgarError::NotFound(format!("Unknown ticker: {ticker}"))),
    }
}

/// Lookup: CIK → Company detail.
/// Checks cache first, then database, then caches the result.
pub fn cik_to_detail_db(conn: &Connection, cik: &str) -> Result<CompanyDetail> {
    let key = normalize_cik(cik);

    if let Some(hit) = CIK_CACHE.get(&key) {
        return Ok(hit);
    }

    let row: Option<(String, String, Option<String>)> = conn
        .query_row(
            "SELECT cik, ticker, title FROM company WHERE cik = ?1",
            params![key],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .optional()?;

    match row {
        Some((cik, ticker, title)) => {
            let detail = CompanyDetail {
                cik: cik.clone(),
                ticker,
                title,
            };
            CIK_CACHE.insert(cik, detail.clone());
            Ok(detail)
        }
        None => Err(EdgarError::NotFound(format!("Unknown CIK: {}", cik))),
    }
}

/// Initialize tables if not present.
fn init_schema(conn: &mut Connection) -> Result<()> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS company (
            cik    TEXT PRIMARY KEY,     -- 10-digit, zero-padded
            ticker TEXT UNIQUE,          -- uppercased
            title  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_company_ticker ON company(ticker);
        "#,
    )?;
    Ok(())
}

/// Store a meta key/value pair (for ETag, timestamps).
fn set_meta(conn: &Connection, key: &str, value: &str) -> Result<()> {
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?1, ?2)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        params![&key as &dyn ToSql, value],
    )?;
    Ok(())
}

/// Retrieve a meta value if available.
fn get_meta(conn: &Connection, key: &str) -> Result<Option<String>> {
    let v: Option<String> = conn
        .query_row("SELECT value FROM meta WHERE key = ?1", params![key], |r| r.get(0))
        .optional()?;
    Ok(v)
}

// /// TODO: Fetch the SEC `company_tickers.json` file, using a cached ETag when available.
// async fn fetch_company_tickers(cached_etag: &Option<String>) -> Result<&str> {
//     use hyper::header::{ETAG, IF_NONE_MATCH};
//     use hyper::StatusCode;
//     Ok("todo!")
// }



/// Parse and store the JSON into SQLite.
fn ingest_json(conn: &mut Connection, bytes: &[u8]) -> Result<()> {
    let raw: std::collections::HashMap<String, TickerEntry> = serde_json::from_slice(bytes)?;
    let tx = conn.transaction()?;
    tx.execute("DELETE FROM company", [])?;

    {
        let mut stmt = tx.prepare("INSERT INTO company(cik, ticker, title) VALUES (?1, ?2, ?3)")?;
        for entry in raw.into_values() {
            let cik = format!("{:010}", entry.cik_str);
            let ticker_up = entry.ticker.to_ascii_uppercase();
            stmt.execute(params![cik, ticker_up, entry.title])?;
        }
    }

    tx.commit()?;
    Ok(())
}

/// normalize any cik to 10-digit zero-padded numeric string.
#[inline]
pub fn normalize_cik(cik: &str) -> String {
    let digits: String = cik.chars().filter(|c| c.is_ascii_digit()).collect();
    format!("{:0>10}", digits)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;

    #[tokio::test]
    async fn test_lookup_and_cache() {
        let tmpdir = env::temp_dir().join("edgars_test_cik");
        let dbfile = tmpdir.join("company_index.sqlite");
        if dbfile.exists() {
            let _ = fs::remove_file(&dbfile);
        }
        let conn = open_or_refresh(&dbfile).await.unwrap();

        // Initial read (DB)
        let cik = ticker_to_cik_db(&conn, "AAPL").unwrap();
        assert_eq!(cik.len(), 10);

        // Cached read
        let cached = ticker_to_cik_db(&conn, "AAPL").unwrap();
        assert_eq!(cached, cik);

        // Reverse lookup
        let detail = cik_to_detail_db(&conn, &cik).unwrap();
        assert_eq!(detail.ticker, "AAPL");

        // Cached reverse lookup
        let detail2 = cik_to_detail_db(&conn, &cik).unwrap();
        assert_eq!(detail2.ticker, "AAPL");
    }
}
