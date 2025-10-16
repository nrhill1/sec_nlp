// src/corp/cik.rs - Optimized ticker to CIK lookup
use std::collections::HashMap;
use std::sync::OnceLock;

use crate::client::SecClient;
use crate::errors::Result;

const TICKER_URL: &str = "https://www.sec.gov/files/company_tickers.json";

static TICKER_CACHE: OnceLock<HashMap<String, String>> = OnceLock::new();

/// Get the global cached ticker-to-CIK map
///
/// This function fetches the map once and caches it for the lifetime of the program.
pub async fn get_ticker_map() -> Result<&'static HashMap<String, String>> {
    if let Some(map) = TICKER_CACHE.get() {
        return Ok(map);
    }

    let fetched = fetch_ticker_map().await?;
    Ok(TICKER_CACHE.get_or_init(|| fetched))
}

/// Look up CIK by ticker symbol
pub async fn ticker_to_cik(ticker: &str) -> Result<String> {
    let map = get_ticker_map().await?;
    let upper = ticker.to_uppercase();

    map.get(&upper)
        .cloned()
        .ok_or_else(|| crate::errors::EdgarError::NotFound(format!("Ticker not found: {}", ticker)))
}

/// Fetch ticker-to-CIK map from SEC
async fn fetch_ticker_map() -> Result<HashMap<String, String>> {
    let client = SecClient::new();

    // SEC provides a JSON file with all tickers
    let json: serde_json::Value = client.fetch_json(TICKER_URL).await?;

    let mut map = HashMap::with_capacity(10_000);

    // Parse the JSON structure: {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
    if let Some(obj) = json.as_object() {
        for (_key, value) in obj {
            if let Some(entry) = value.as_object() {
                if let (Some(ticker), Some(cik)) = (
                    entry.get("ticker").and_then(|v| v.as_str()),
                    entry.get("cik_str").and_then(|v| v.as_i64()),
                ) {
                    map.insert(ticker.to_uppercase(), normalize_cik(&cik.to_string()));
                }
            }
        }
    }

    Ok(map)
}

/// Normalize CIK to 10-digit zero-padded format
///
/// Examples:
/// - "320193" -> "0000320193"
/// - "1234567890" -> "1234567890"
/// - "AAPL" -> "0000000000" (invalid, returns zeros)
#[inline]
pub fn normalize_cik(cik: &str) -> String {
    let digits: String = cik.chars().filter(|c| c.is_ascii_digit()).collect();
    format!("{:0>10}", digits)
}

/// Check if a string is a valid CIK (contains only digits)
pub fn is_valid_cik(cik: &str) -> bool {
    !cik.is_empty() && cik.chars().all(|c| c.is_ascii_digit())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_cik() {
        assert_eq!(normalize_cik("320193"), "0000320193");
        assert_eq!(normalize_cik("0000320193"), "0000320193");
        assert_eq!(normalize_cik("1234567890"), "1234567890");
        assert_eq!(normalize_cik("1"), "0000000001");
    }

    #[test]
    fn test_normalize_cik_with_dashes() {
        assert_eq!(normalize_cik("0000-320193"), "0000320193");
        assert_eq!(normalize_cik("CIK0000320193"), "0000320193");
    }

    #[test]
    fn test_is_valid_cik() {
        assert!(is_valid_cik("320193"));
        assert!(is_valid_cik("0000320193"));
        assert!(!is_valid_cik("AAPL"));
        assert!(!is_valid_cik(""));
        assert!(!is_valid_cik("123-456"));
    }

    #[tokio::test]
    async fn test_fetch_ticker_map() {
        let map = fetch_ticker_map().await;
        assert!(map.is_ok());

        let map = map.unwrap();
        assert!(map.len() > 5000); // SEC has thousands of tickers
        assert!(map.contains_key("AAPL"));
        assert!(map.contains_key("MSFT"));
    }

    #[tokio::test]
    async fn test_ticker_to_cik() {
        // Test with common tickers
        let result = ticker_to_cik("AAPL").await;
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "0000320193");
    }

    #[tokio::test]
    async fn test_ticker_to_cik_case_insensitive() {
        let lower = ticker_to_cik("aapl").await;
        let upper = ticker_to_cik("AAPL").await;

        assert!(lower.is_ok());
        assert!(upper.is_ok());
        assert_eq!(lower.unwrap(), upper.unwrap());
    }

    #[tokio::test]
    async fn test_ticker_not_found() {
        let result = ticker_to_cik("NOTREALTICKER123").await;
        assert!(result.is_err());

        match result {
            Err(crate::errors::EdgarError::NotFound(msg)) => {
                assert!(msg.contains("NOTREALTICKER123"));
            }
            _ => panic!("Expected NotFound error"),
        }
    }

    #[tokio::test]
    async fn test_get_ticker_map_caches() {
        // First call should fetch
        let map1 = get_ticker_map().await.unwrap();

        // Second call should use cache (same pointer)
        let map2 = get_ticker_map().await.unwrap();

        assert!(std::ptr::eq(map1, map2));
    }
}
