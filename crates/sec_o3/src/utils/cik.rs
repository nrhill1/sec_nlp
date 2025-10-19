//! Retrieval of CIK based on ticker symbol
//!
//! This module uses an asynchronous cache to store
//! pairs of ticker symbols and Central Index Keys.
//!
//! Data is fetched from the SEC's ticker.txt file which has format:
//! ```text
//! ticker\tcik
//! aapl\t320193
//! msft\t789019
//! ```

use ahash::RandomState;
use futures::StreamExt;
use moka::future::Cache;
use once_cell::sync::Lazy;
use std::collections::HashMap;
use std::time::Duration;

use crate::{Client, Error, Result};

/// Simple ticker -> CIK cache
/// - Max 10,000 entries
/// - 24 hour TTL
/// - ahash for speed
static CACHE: Lazy<Cache<String, String, RandomState>> = Lazy::new(|| {
    Cache::builder()
        .max_capacity(10_000)
        .time_to_live(Duration::from_secs(3600 * 24))
        .build_with_hasher(RandomState::default())
});

/// Ticker entry from ticker.txt (tab-delimited: ticker\tcik)
#[derive(Debug, Clone)]
struct TickerEntry {
    ticker: String,
    cik: String,
}

/// Look up CIK by ticker symbol (case-insensitive).
///
/// Returns 10-digit zero-padded CIK string. Cache auto-invalidates after 24 hours.
///
/// # Examples
///
/// ```no_run
/// use sec_o3::cik::ticker_to_cik;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let cik = ticker_to_cik("AAPL").await?;
///     println!("CIK: {}", cik); // "0000320193"
///     Ok(())
/// }
/// ```
pub async fn ticker_to_cik(ticker: &str) -> Result<String> {
    let ticker_upper = ticker.to_uppercase();

    CACHE
        .try_get_with(
            ticker_upper.clone(),
            async move { fetch_cik_by_ticker(&ticker_upper).await },
        )
        .await
        .map_err(|e| Error::Custom(format!("Cache error: {}", e)))
}

/// Look up multiple companies by ticker symbol (case-insensitive).
///
/// Returns Vector of (ticker, CIK) tuples for successfully found tickers.
/// Silently skips tickers that aren't found.
///
/// # Examples
///
/// ```no_run
/// use sec_o3::cik::batch_ticker_lookup;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let tickers = vec!["AAPL", "MSFT", "GOOGL"];
///     let results = batch_ticker_lookup(&tickers).await?;

///     for (ticker, cik) in results {
///         println!("{}: {}", ticker, cik);
///     }
///     Ok(())
/// }
/// ```
pub async fn batch_ticker_lookup(tickers: &[&str]) -> Result<Vec<(String, String)>> {
    let mut results = Vec::with_capacity(tickers.len());

    for ticker in tickers {
        if let Ok(cik) = ticker_to_cik(ticker).await {
            results.push((ticker.to_uppercase(), cik));
        }
    }

    Ok(results)
}

/// Look up all tickers in parallel and populate the cache.
///
/// This pre-populates the cache with all company tickers from the SEC.
/// Useful for batch operations or to warm up the cache at startup.
/// Inserts are processed concurrently for maximum performance.
///
/// # Examples
///
/// ```no_run
/// use sec_o3::cik::populate_cache;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     populate_cache().await?;
///     println!("Cache populated with {} entries", cache_size());
///     Ok(())
/// }
/// ```
pub async fn populate_cache() -> Result<()> {
    let data = fetch_ticker_data().await?;

    // Process inserts concurrently without collecting into a Vec
    futures::stream::iter(data)
        .for_each_concurrent(None, |(ticker, entry)| async move {
            CACHE.insert(ticker, entry.cik).await;
        })
        .await;

    Ok(())
}

/// Fetch CIK for a single ticker from the SEC endpoint.
async fn fetch_cik_by_ticker(ticker: &str) -> Result<String> {
    let data = fetch_ticker_data().await?;

    // Lookup ticker
    data.get(&ticker.to_uppercase())
        .map(|entry| entry.cik.clone())
        .ok_or_else(|| Error::NotFound(format!("Ticker not found: {}", ticker)))
}

/// Fetch and parse the complete ticker-to-CIK mapping from SEC.
///
/// The SEC provides this as a tab-delimited text file with format:
/// ticker\tcik (e.g., "aapl\t320193")
async fn fetch_ticker_data() -> Result<HashMap<String, TickerEntry>> {
    let client = Client::from_env().unwrap_or_else(|_| Client::new("sec_o3", "default@example.com"));

    let url = "https://www.sec.gov/include/ticker.txt";

    let text = client
        .get_text(url)
        .await
        .map_err(|e| Error::Custom(format!("Failed to fetch ticker data: {}", e)))?;

    let mut data = HashMap::new();

    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        // Parse tab-delimited: ticker\tcik
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() != 2 {
            continue; // Skip malformed lines
        }

        let ticker = parts[0].trim().to_uppercase();
        let cik = parts[1].trim();

        // Parse CIK as number to validate, then format with leading zeros
        if let Ok(cik_num) = cik.parse::<u64>() {
            data.insert(
                ticker.clone(),
                TickerEntry {
                    ticker: ticker.clone(),
                    cik: format!("{:010}", cik_num),
                },
            );
        }
    }

    if data.is_empty() {
        return Err(Error::Custom("Empty ticker data received".to_string()));
    }

    Ok(data)
}

/// Get the current cache size (for debugging/monitoring).
pub fn cache_size() -> u64 {
    CACHE.entry_count()
}

/// Clear the cache (for testing or if you want to force a refresh).
pub async fn clear_cache() {
    CACHE.invalidate_all();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_ticker_to_cik() {
        let cik = ticker_to_cik("AAPL").await.unwrap();
        assert_eq!(cik, "0000320193");
    }

    #[tokio::test]
    async fn test_case_insensitive() {
        let cik1 = ticker_to_cik("AAPL").await.unwrap();
        let cik2 = ticker_to_cik("aapl").await.unwrap();
        assert_eq!(cik1, cik2);
    }

    #[tokio::test]
    async fn test_batch_lookup() {
        let tickers = vec!["AAPL", "MSFT", "GOOGL"];
        let results = batch_ticker_lookup(&tickers).await.unwrap();
        assert_eq!(results.len(), 3);

        for (_, cik) in results {
            assert_eq!(cik.len(), 10);
            assert!(cik.starts_with('0'));
        }
    }

    #[tokio::test]
    async fn test_populate_cache() {
        populate_cache().await.unwrap();
        assert!(cache_size() > 1000);
    }

    #[tokio::test]
    async fn test_invalid_ticker() {
        let result = ticker_to_cik("NOTREAL123456").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_cik_formatting() {
        // Apple's CIK should be zero-padded to 10 digits
        let cik = ticker_to_cik("AAPL").await.unwrap();
        assert_eq!(cik.len(), 10);
        assert!(cik.chars().all(|c| c.is_ascii_digit()));
    }
}
