use once_cell::sync::Lazy;
use reqwest::blocking::Client;
use serde_json::Value;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use crate::constants::DEFAULT_TIMEOUT_SECS;
use crate::error::EftsError;

static LAST_REQUEST: Lazy<Mutex<Instant>> =
    Lazy::new(|| Mutex::new(Instant::now() - Duration::from_secs(60)));

pub(crate) fn build_client(timeout_seconds: f64) -> Result<Client, EftsError> {
    let timeout = if timeout_seconds > 0.0 {
        timeout_seconds
    } else {
        DEFAULT_TIMEOUT_SECS
    };
    Client::builder()
        .timeout(Duration::from_secs_f64(timeout))
        .build()
        .map_err(|err| {
            EftsError::new(
                0,
                format!("Failed to build HTTP client: {}", err),
                None,
                false,
            )
        })
}

pub(crate) fn enforce_rate_limit(rate_limit_delay_seconds: f64) {
    if rate_limit_delay_seconds <= 0.0 {
        return;
    }
    let delay = Duration::from_secs_f64(rate_limit_delay_seconds);
    let mut last_request = LAST_REQUEST
        .lock()
        .expect("rate limit mutex should be available");
    let elapsed = last_request.elapsed();
    if elapsed < delay {
        std::thread::sleep(delay - elapsed);
    }
    *last_request = Instant::now();
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn build_params(
    query: &str,
    forms: &[String],
    ciks: &[String],
    tickers: &[String],
    start_date: Option<&str>,
    end_date: Option<&str>,
    limit: u32,
    start: u32,
    sort_field: &str,
    sort_order: &str,
) -> Vec<(String, String)> {
    let mut params = Vec::new();
    params.push(("q".to_string(), query.to_string()));
    params.push(("from".to_string(), start.to_string()));
    params.push(("size".to_string(), limit.to_string()));
    params.push(("sort".to_string(), format!("{}:{}", sort_field, sort_order)));
    if !forms.is_empty() {
        params.push(("forms".to_string(), forms.join(",")));
    }
    if !ciks.is_empty() {
        params.push(("ciks".to_string(), ciks.join(",")));
    }
    if !tickers.is_empty() {
        params.push(("tickers".to_string(), tickers.join(",")));
    }
    if let Some(value) = start_date {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            params.push(("startdt".to_string(), trimmed.to_string()));
        }
    }
    if let Some(value) = end_date {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            params.push(("enddt".to_string(), trimmed.to_string()));
        }
    }
    params
}

pub(crate) fn make_request(
    client: &Client,
    base_url: &str,
    params: &[(String, String)],
    user_agent: &str,
) -> Result<Value, EftsError> {
    let response = client
        .get(base_url)
        .header("User-Agent", user_agent)
        .header("Accept", "application/json")
        .query(params)
        .send()
        .map_err(|err| {
            let retryable = err.is_timeout() || err.is_connect();
            EftsError::new(0, format!("Network error: {}", err), None, retryable)
        })?;

    let status = response.status();
    let body = response.text().unwrap_or_default();
    if !status.is_success() {
        let retryable = status.as_u16() == 429 || status.as_u16() >= 500;
        let message = format!(
            "HTTP {}: {}",
            status.as_u16(),
            status.canonical_reason().unwrap_or("error")
        );
        let detail = if body.is_empty() { None } else { Some(body) };
        return Err(EftsError::new(status.as_u16(), message, detail, retryable));
    }

    serde_json::from_str(&body)
        .map_err(|err| EftsError::new(0, format!("JSON parse error: {}", err), Some(body), false))
}

#[cfg(test)]
mod tests {
    use super::build_params;

    #[test]
    fn build_params_includes_query_and_paging() {
        let params = build_params(
            "warranty",
            &[],
            &[],
            &[],
            None,
            None,
            25,
            10,
            "score",
            "desc",
        );

        let mut map = std::collections::HashMap::new();
        for (key, value) in params {
            map.insert(key, value);
        }

        assert_eq!(map.get("q"), Some(&"warranty".to_string()));
        assert_eq!(map.get("from"), Some(&"10".to_string()));
        assert_eq!(map.get("size"), Some(&"25".to_string()));
        assert_eq!(map.get("sort"), Some(&"score:desc".to_string()));
    }

    #[test]
    fn build_params_optional_filters() {
        let params = build_params(
            "q",
            &["10-K".to_string(), "8-K".to_string()],
            &["0000123456".to_string()],
            &["AAPL".to_string(), "MSFT".to_string()],
            Some("2024-01-01"),
            Some("2024-12-31"),
            10,
            0,
            "filed",
            "asc",
        );

        let mut map = std::collections::HashMap::new();
        for (key, value) in params {
            map.insert(key, value);
        }

        assert_eq!(map.get("forms"), Some(&"10-K,8-K".to_string()));
        assert_eq!(map.get("ciks"), Some(&"0000123456".to_string()));
        assert_eq!(map.get("tickers"), Some(&"AAPL,MSFT".to_string()));
        assert_eq!(map.get("startdt"), Some(&"2024-01-01".to_string()));
        assert_eq!(map.get("enddt"), Some(&"2024-12-31".to_string()));
    }

    #[test]
    fn build_params_skips_blank_dates() {
        let params = build_params("q", &[], &[], &[], Some(" "), None, 10, 0, "score", "desc");

        let mut map = std::collections::HashMap::new();
        for (key, value) in params {
            map.insert(key, value);
        }

        assert!(!map.contains_key("startdt"));
    }
}
