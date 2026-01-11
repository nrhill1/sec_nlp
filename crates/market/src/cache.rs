// crates/market/src/cache.rs
//! LRU cache for market data with TTL support.

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use crate::types::{CachedPrice, CachedQuotes, MarketQuote};

/// Default cache TTL (5 minutes).
const DEFAULT_TTL_SECS: u64 = 300;

/// Maximum cache entries.
const MAX_PRICE_ENTRIES: usize = 1000;
const MAX_RANGE_ENTRIES: usize = 100;

/// Thread-safe price cache.
pub struct PriceCache {
    entries: Mutex<HashMap<String, CachedPrice>>,
    ttl: Duration,
}

impl PriceCache {
    /// Create a new price cache with default TTL.
    pub fn new() -> Self {
        Self {
            entries: Mutex::new(HashMap::new()),
            ttl: Duration::from_secs(DEFAULT_TTL_SECS),
        }
    }

    /// Create with custom TTL.
    pub fn with_ttl(ttl_secs: u64) -> Self {
        Self {
            entries: Mutex::new(HashMap::new()),
            ttl: Duration::from_secs(ttl_secs),
        }
    }

    /// Get cached price if valid.
    pub fn get(&self, ticker: &str) -> Option<f64> {
        let entries = self.entries.lock().ok()?;
        let entry = entries.get(ticker)?;
        if entry.cached_at.elapsed() < self.ttl {
            Some(entry.price)
        } else {
            None
        }
    }

    /// Insert or update a price.
    pub fn insert(&self, ticker: String, price: f64) {
        if let Ok(mut entries) = self.entries.lock() {
            // Evict oldest if at capacity
            if entries.len() >= MAX_PRICE_ENTRIES && !entries.contains_key(&ticker) {
                if let Some(oldest_key) = Self::find_oldest(&entries) {
                    entries.remove(&oldest_key);
                }
            }
            entries.insert(
                ticker,
                CachedPrice {
                    price,
                    cached_at: Instant::now(),
                },
            );
        }
    }

    /// Find the oldest entry key.
    fn find_oldest(entries: &HashMap<String, CachedPrice>) -> Option<String> {
        entries
            .iter()
            .min_by_key(|(_, v)| v.cached_at)
            .map(|(k, _)| k.clone())
    }

    /// Clear all entries.
    pub fn clear(&self) {
        if let Ok(mut entries) = self.entries.lock() {
            entries.clear();
        }
    }

    /// Get number of cached entries.
    pub fn len(&self) -> usize {
        self.entries.lock().map(|e| e.len()).unwrap_or(0)
    }

    /// Check if cache is empty.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl Default for PriceCache {
    fn default() -> Self {
        Self::new()
    }
}

/// Thread-safe quote range cache.
pub struct RangeCache {
    entries: Mutex<HashMap<String, CachedQuotes>>,
    ttl: Duration,
}

impl RangeCache {
    /// Create a new range cache with default TTL.
    pub fn new() -> Self {
        Self {
            entries: Mutex::new(HashMap::new()),
            ttl: Duration::from_secs(DEFAULT_TTL_SECS),
        }
    }

    /// Create cache key from ticker and date range.
    pub fn make_key(ticker: &str, date_range: &str) -> String {
        format!("{}:{}", ticker, date_range)
    }

    /// Get cached quotes if valid.
    pub fn get(&self, ticker: &str, date_range: &str) -> Option<Vec<MarketQuote>> {
        let key = Self::make_key(ticker, date_range);
        let entries = self.entries.lock().ok()?;
        let entry = entries.get(&key)?;
        if entry.cached_at.elapsed() < self.ttl {
            Some(entry.quotes.clone())
        } else {
            None
        }
    }

    /// Insert or update quotes.
    pub fn insert(&self, ticker: &str, date_range: &str, quotes: Vec<MarketQuote>) {
        let key = Self::make_key(ticker, date_range);
        if let Ok(mut entries) = self.entries.lock() {
            // Evict oldest if at capacity
            if entries.len() >= MAX_RANGE_ENTRIES && !entries.contains_key(&key) {
                if let Some(oldest_key) = Self::find_oldest(&entries) {
                    entries.remove(&oldest_key);
                }
            }
            entries.insert(
                key,
                CachedQuotes {
                    quotes,
                    cached_at: Instant::now(),
                },
            );
        }
    }

    fn find_oldest(entries: &HashMap<String, CachedQuotes>) -> Option<String> {
        entries
            .iter()
            .min_by_key(|(_, v)| v.cached_at)
            .map(|(k, _)| k.clone())
    }

    /// Clear all entries.
    pub fn clear(&self) {
        if let Ok(mut entries) = self.entries.lock() {
            entries.clear();
        }
    }
}

impl Default for RangeCache {
    fn default() -> Self {
        Self::new()
    }
}

/// Global caches.
static PRICE_CACHE: std::sync::OnceLock<PriceCache> = std::sync::OnceLock::new();
static RANGE_CACHE: std::sync::OnceLock<RangeCache> = std::sync::OnceLock::new();

/// Get the global price cache.
pub fn price_cache() -> &'static PriceCache {
    PRICE_CACHE.get_or_init(PriceCache::new)
}

/// Get the global range cache.
pub fn range_cache() -> &'static RangeCache {
    RANGE_CACHE.get_or_init(RangeCache::new)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread::sleep;

    #[test]
    fn price_cache_insert_and_get() {
        let cache = PriceCache::new();
        cache.insert("AAPL".to_string(), 150.0);
        assert_eq!(cache.get("AAPL"), Some(150.0));
        assert_eq!(cache.get("MSFT"), None);
    }

    #[test]
    fn price_cache_ttl_expiry() {
        let cache = PriceCache::with_ttl(0); // Immediate expiry
        cache.insert("AAPL".to_string(), 150.0);
        sleep(Duration::from_millis(10));
        assert_eq!(cache.get("AAPL"), None);
    }

    #[test]
    fn range_cache_key_format() {
        let key = RangeCache::make_key("AAPL", "2024-01-01..2024-01-31");
        assert_eq!(key, "AAPL:2024-01-01..2024-01-31");
    }

    #[test]
    fn price_cache_clear() {
        let cache = PriceCache::new();
        cache.insert("AAPL".to_string(), 150.0);
        cache.insert("MSFT".to_string(), 300.0);
        assert_eq!(cache.len(), 2);
        cache.clear();
        assert!(cache.is_empty());
    }
}
