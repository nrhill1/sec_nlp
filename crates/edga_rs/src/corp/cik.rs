// ============================================================================
// src/data/cik.rs - Ticker to CIK lookup
// ============================================================================
use std::collections::HashMap;
use std::sync::OnceLock;

use crate::client::SecClient;
use crate::errors::LookupError;

pub type Result<T> = std::result::Result<T, LookupError>;

const TICKER_URL: &str = "https://www.sec.gov/include/ticker.txt";

static TICKER_CACHE: OnceLock<HashMap<String, String>> = OnceLock::new();

/// Get the global cached ticker map (fetching if needed).
pub async fn get_ticker_cik_map() -> Result<&'static HashMap<String, String>> {
    if let Some(map) = TICKER_CACHE.get() {
        return Ok(map);
    }
    let fetched = fetch_ticker_cik_map().await?;
    Ok(TICKER_CACHE.get_or_init(|| fetched))
}

/// Fetch the SEC ticker→CIK file over HTTPS and parse it.
async fn fetch_ticker_cik_map() -> Result<HashMap<String, String>> {
    let client = SecClient::new();
    let text = client.fetch_text(TICKER_URL).await?;
    Ok(parse_ticker_cik_fast(&text))
}

fn parse_ticker_cik_fast(s: &str) -> HashMap<String, String> {
    let mut map = HashMap::with_capacity(9_000);

    let bytes = s.as_bytes();
    let mut start = 0;

    for (i, &b) in bytes.iter().enumerate() {
        if b == b'\n' || b == b'\r' {
            if i > start {
                parse_line(&bytes[start..i], &mut map);
            }
            start = i + 1;
        }
    }
    if start < bytes.len() {
        parse_line(&bytes[start..], &mut map);
    }

    map
}

fn parse_line(line: &[u8], map: &mut HashMap<String, String>) {
    if let Some(pos) = memchr::memchr(b'|', line) {
        let (ticker, rest) = line.split_at(pos);
        if let (Ok(ticker), Ok(cik_raw)) = (std::str::from_utf8(ticker), std::str::from_utf8(&rest[1..])) {
            let ticker = ticker.trim().to_ascii_uppercase();
            let cik = normalize_cik(cik_raw.trim());
            if !ticker.is_empty() && !cik.is_empty() {
                map.insert(ticker, cik);
            }
        }
    }
}

/// Normalize to a zero-padded 10-digit CIK.
pub fn normalize_cik(cik: &str) -> String {
    let digits: String = cik.chars().filter(|c| c.is_ascii_digit()).collect();
    format!("{:0>10}", digits)
}
