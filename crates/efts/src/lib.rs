//! Python extension module for SEC EDGAR Full-Text Search (EFTS).

use chrono::{NaiveDate, Utc};
use once_cell::sync::Lazy;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::IntoPyObjectExt;
use regex::Regex;
use reqwest::blocking::Client;
use reqwest::Url;
use serde::Serialize;
use serde_json::{Map, Value};
use std::sync::Mutex;
use std::time::{Duration, Instant};

const EFTS_BASE_URL: &str = "https://efts.sec.gov/LATEST/search-index";
const DEFAULT_USER_AGENT: &str = "SEC NLP Tool (contact@example.com)";
const DEFAULT_TIMEOUT_SECS: f64 = 30.0;
const DEFAULT_MAX_RETRIES: usize = 3;
const DEFAULT_RETRY_DELAY_SECS: f64 = 1.0;
const DEFAULT_RATE_LIMIT_SECS: f64 = 0.1;
const SEC_HOST_SUFFIX: &str = "sec.gov";

const INSIDER_FORMS: [&str; 6] = ["3", "3/A", "4", "4/A", "5", "5/A"];
const COMPANY_KEYWORDS: [&str; 24] = [
    " INC",
    " INC.",
    " CORP",
    " CORPORATION",
    " LTD",
    " LIMITED",
    " LLC",
    " PLC",
    " LP",
    " L.P.",
    " LLP",
    " CO",
    " COMPANY",
    " HOLDINGS",
    " GROUP",
    " TRUST",
    " FUND",
    " RESOURCES",
    " MINING",
    " MATERIALS",
    " ENERGY",
    " TECHNOLOGIES",
    " SYSTEMS",
    " ENTERPRISES",
];

static CIK_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)\bCIK\s*(\d{1,10})\b").expect("valid regex"));
static PAREN_PATTERN: Lazy<Regex> = Lazy::new(|| Regex::new(r"\(([^)]+)\)").expect("valid regex"));
static LAST_REQUEST: Lazy<Mutex<Instant>> =
    Lazy::new(|| Mutex::new(Instant::now() - Duration::from_secs(60)));

#[derive(Debug, Serialize)]
struct SearchHit {
    accession_number: String,
    cik: String,
    company_name: String,
    tickers: Vec<String>,
    form_type: String,
    filed_date: String,
    file_number: Option<String>,
    film_number: Option<String>,
    snippet: String,
    score: f64,
    filing_url: Option<String>,
}

#[derive(Debug, Serialize)]
struct SearchResponse {
    query: String,
    total: u64,
    hits: Vec<SearchHit>,
    start: u32,
    limit: u32,
}

impl SearchResponse {
    fn has_more(&self) -> bool {
        (self.start as u64) + (self.hits.len() as u64) < self.total
    }

    fn next_offset(&self) -> u32 {
        self.start + (self.hits.len() as u32)
    }
}

#[derive(Debug)]
pub struct EftsError {
    status: u16,
    message: String,
    detail: Option<String>,
    retryable: bool,
}

impl EftsError {
    fn new(
        status: u16,
        message: impl Into<String>,
        detail: Option<String>,
        retryable: bool,
    ) -> Self {
        Self {
            status,
            message: message.into(),
            detail,
            retryable,
        }
    }

    fn to_py_err(&self) -> PyErr {
        let mut message = format!("EFTS API Error ({}): {}", self.status, self.message);
        if let Some(detail) = &self.detail {
            if !detail.is_empty() {
                message.push_str("; ");
                message.push_str(detail);
            }
        }
        PyRuntimeError::new_err(message)
    }
}

impl std::fmt::Display for EftsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "EFTS API Error ({}): {}", self.status, self.message)
    }
}

impl std::error::Error for EftsError {}

#[pyclass(name = "EFTSClient")]
struct EftsClient {
    base_url: String,
    user_agent: String,
    timeout_seconds: f64,
    max_retries: usize,
    retry_delay_seconds: f64,
    rate_limit_delay_seconds: f64,
}

#[pymethods]
impl EftsClient {
    #[new]
    #[pyo3(
        signature = (
            user_agent=None,
            timeout=30.0,
            max_retries=3,
            retry_delay=1.0,
            rate_limit_delay=0.1,
            base_url=None
        )
    )]
    fn new(
        user_agent: Option<String>,
        timeout: f64,
        max_retries: usize,
        retry_delay: f64,
        rate_limit_delay: f64,
        base_url: Option<String>,
    ) -> PyResult<Self> {
        if timeout <= 0.0 {
            return Err(PyValueError::new_err("timeout must be > 0"));
        }
        if retry_delay < 0.0 {
            return Err(PyValueError::new_err("retry_delay must be >= 0"));
        }
        if rate_limit_delay < 0.0 {
            return Err(PyValueError::new_err("rate_limit_delay must be >= 0"));
        }
        let user_agent = user_agent.unwrap_or_else(|| DEFAULT_USER_AGENT.to_string());
        let base_url = base_url.unwrap_or_else(|| EFTS_BASE_URL.to_string());
        validate_base_url_py(&base_url)?;
        Ok(Self {
            base_url,
            user_agent,
            timeout_seconds: timeout,
            max_retries,
            retry_delay_seconds: retry_delay,
            rate_limit_delay_seconds: rate_limit_delay,
        })
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(
        signature = (
            query,
            forms=None,
            ciks=None,
            tickers=None,
            start_date=None,
            end_date=None,
            limit=10,
            start=0,
            sort_field="score".to_string(),
            sort_order="desc".to_string()
        )
    )]
    fn search(
        &self,
        py: Python<'_>,
        query: String,
        forms: Option<Vec<String>>,
        ciks: Option<Vec<String>>,
        tickers: Option<Vec<String>>,
        start_date: Option<String>,
        end_date: Option<String>,
        limit: u32,
        start: u32,
        sort_field: String,
        sort_order: String,
    ) -> PyResult<PyObject> {
        let forms = forms.unwrap_or_default();
        let ciks = ciks.unwrap_or_default();
        let tickers = tickers.unwrap_or_default();
        let response = py
            .allow_threads(move || {
                self.execute_search(
                    &query,
                    &forms,
                    &ciks,
                    &tickers,
                    start_date.as_deref(),
                    end_date.as_deref(),
                    limit,
                    start,
                    &sort_field,
                    &sort_order,
                )
            })
            .map_err(|err| err.to_py_err())?;
        let value = serde_json::to_value(response)
            .map_err(|err| PyRuntimeError::new_err(err.to_string()))?;
        json_to_py(py, &value)
    }

    #[pyo3(
        signature = (
            query,
            forms=None,
            ciks=None,
            tickers=None,
            start_date=None,
            end_date=None,
            max_results=100,
            sort_field="score".to_string(),
            sort_order="desc".to_string()
        )
    )]
    #[allow(clippy::too_many_arguments)]
    fn search_all(
        &self,
        py: Python<'_>,
        query: String,
        forms: Option<Vec<String>>,
        ciks: Option<Vec<String>>,
        tickers: Option<Vec<String>>,
        start_date: Option<String>,
        end_date: Option<String>,
        max_results: u32,
        sort_field: String,
        sort_order: String,
    ) -> PyResult<PyObject> {
        let forms = forms.unwrap_or_default();
        let ciks = ciks.unwrap_or_default();
        let tickers = tickers.unwrap_or_default();
        let hits = py
            .allow_threads(move || {
                self.execute_search_all(
                    &query,
                    &forms,
                    &ciks,
                    &tickers,
                    start_date.as_deref(),
                    end_date.as_deref(),
                    max_results,
                    &sort_field,
                    &sort_order,
                )
            })
            .map_err(|err| err.to_py_err())?;
        let value =
            serde_json::to_value(hits).map_err(|err| PyRuntimeError::new_err(err.to_string()))?;
        json_to_py(py, &value)
    }
}

impl EftsClient {
    #[allow(clippy::too_many_arguments)]
    fn execute_search(
        &self,
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
    ) -> Result<SearchResponse, EftsError> {
        let limit = limit.clamp(1, 100);
        let params = build_params(
            query, forms, ciks, tickers, start_date, end_date, limit, start, sort_field, sort_order,
        );
        let client = build_client(self.timeout_seconds)?;
        let mut delay_seconds = self.retry_delay_seconds;
        for attempt in 0..=self.max_retries {
            enforce_rate_limit(self.rate_limit_delay_seconds);
            match make_request(&client, &self.base_url, &params, &self.user_agent) {
                Ok(data) => return Ok(parse_response(&data, query)),
                Err(err) => {
                    if attempt < self.max_retries && err.retryable {
                        if delay_seconds > 0.0 {
                            std::thread::sleep(Duration::from_secs_f64(delay_seconds));
                        }
                        delay_seconds *= 2.0;
                        continue;
                    }
                    return Err(err);
                }
            }
        }
        Err(EftsError::new(
            0,
            "Unknown error after retries",
            None,
            false,
        ))
    }

    #[allow(clippy::too_many_arguments)]
    fn execute_search_all(
        &self,
        query: &str,
        forms: &[String],
        ciks: &[String],
        tickers: &[String],
        start_date: Option<&str>,
        end_date: Option<&str>,
        max_results: u32,
        sort_field: &str,
        sort_order: &str,
    ) -> Result<Vec<SearchHit>, EftsError> {
        if max_results == 0 {
            return Ok(Vec::new());
        }
        let mut all_hits: Vec<SearchHit> = Vec::new();
        let mut offset = 0;
        let page_size = std::cmp::min(100, max_results);
        while (all_hits.len() as u32) < max_results {
            let remaining = max_results - (all_hits.len() as u32);
            let fetch_size = std::cmp::min(page_size, remaining);
            let response = self.execute_search(
                query, forms, ciks, tickers, start_date, end_date, fetch_size, offset, sort_field,
                sort_order,
            )?;
            let hit_count = response.hits.len();
            let has_more = response.has_more();
            let next_offset = response.next_offset();
            all_hits.extend(response.hits);
            if hit_count == 0 || !has_more {
                break;
            }
            offset = next_offset;
        }
        Ok(all_hits)
    }
}

#[pyfunction]
#[pyo3(signature = (email, company_name="SEC NLP Tool".to_string(), timeout=30.0))]
fn create_efts_client(email: String, company_name: String, timeout: f64) -> PyResult<EftsClient> {
    let user_agent = format!("{} ({})", company_name, email);
    EftsClient::new(
        Some(user_agent),
        timeout,
        DEFAULT_MAX_RETRIES,
        DEFAULT_RETRY_DELAY_SECS,
        DEFAULT_RATE_LIMIT_SECS,
        None,
    )
}

fn validate_base_url(base_url: &str) -> Result<(), EftsError> {
    let url = Url::parse(base_url)
        .map_err(|err| EftsError::new(0, format!("base_url is invalid: {}", err), None, false))?;
    if url.scheme() != "https" {
        return Err(EftsError::new(0, "base_url must use https", None, false));
    }
    let host = url
        .host_str()
        .ok_or_else(|| EftsError::new(0, "base_url must include a host", None, false))?;
    let host_lower = host.to_ascii_lowercase();
    if host_lower == SEC_HOST_SUFFIX || host_lower.ends_with(".sec.gov") {
        Ok(())
    } else {
        Err(EftsError::new(
            0,
            "base_url must use a sec.gov host",
            None,
            false,
        ))
    }
}

fn validate_base_url_py(base_url: &str) -> PyResult<()> {
    if let Err(err) = validate_base_url(base_url) {
        return Err(PyValueError::new_err(err.message));
    }
    Ok(())
}

pub fn search_raw(query: &str, user_agent: &str, limit: u32) -> Result<Value, EftsError> {
    if query.trim().is_empty() {
        return Err(EftsError::new(0, "query must be non-empty", None, false));
    }
    let user_agent = user_agent.trim();
    if user_agent.is_empty() {
        return Err(EftsError::new(
            0,
            "user_agent must be non-empty",
            None,
            false,
        ));
    }
    let base_url = EFTS_BASE_URL;
    validate_base_url(base_url)?;
    let client = EftsClient {
        base_url: base_url.to_string(),
        user_agent: user_agent.to_string(),
        timeout_seconds: DEFAULT_TIMEOUT_SECS,
        max_retries: DEFAULT_MAX_RETRIES,
        retry_delay_seconds: DEFAULT_RETRY_DELAY_SECS,
        rate_limit_delay_seconds: DEFAULT_RATE_LIMIT_SECS,
    };
    let response =
        client.execute_search(query, &[], &[], &[], None, None, limit, 0, "score", "desc")?;
    serde_json::to_value(response).map_err(|err| {
        EftsError::new(
            0,
            format!("Failed to serialize response: {}", err),
            None,
            false,
        )
    })
}

fn build_client(timeout_seconds: f64) -> Result<Client, EftsError> {
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

fn enforce_rate_limit(rate_limit_delay_seconds: f64) {
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
fn build_params(
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

fn make_request(
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

fn parse_response(data: &Value, query: &str) -> SearchResponse {
    let empty = Map::new();
    let hits_data = data
        .get("hits")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let total = extract_total(hits_data);
    let raw_hits = hits_data
        .get("hits")
        .and_then(|v| v.as_array())
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let mut hits = Vec::new();
    for raw_hit in raw_hits {
        hits.push(parse_hit(raw_hit));
    }
    let query_data = data
        .get("query")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let start = get_u32(query_data, "from", 0);
    let limit = get_u32(query_data, "size", 10);
    SearchResponse {
        query: query.to_string(),
        total,
        hits,
        start,
        limit,
    }
}

fn parse_hit(raw: &Value) -> SearchHit {
    let empty = Map::new();
    let source = raw
        .get("_source")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let snippet = extract_snippet(raw);
    let filed_date = extract_filed_date(source);
    let accession = extract_accession(source);
    let company_name = extract_company_name(source);
    let tickers = extract_tickers(source, &company_name);
    let cik = extract_cik(source, &company_name, &accession);
    let form_type = get_str(source, "form", "");
    let file_number = get_optional_str(source, "file_num");
    let film_number = get_optional_str(source, "film_num");
    let score = get_f64(raw, "_score", 0.0);
    SearchHit {
        accession_number: accession,
        cik,
        company_name,
        tickers,
        form_type,
        filed_date,
        file_number,
        film_number,
        snippet,
        score,
        filing_url: None,
    }
}

fn get_str(data: &Map<String, Value>, key: &str, default: &str) -> String {
    data.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or(default)
        .to_string()
}

fn get_optional_str(data: &Map<String, Value>, key: &str) -> Option<String> {
    data.get(key)
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

fn get_u32(data: &Map<String, Value>, key: &str, default: u32) -> u32 {
    data.get(key)
        .and_then(|v| v.as_u64().or_else(|| v.as_f64().map(|f| f as u64)))
        .map(|v| v as u32)
        .unwrap_or(default)
}

fn get_f64(data: &Value, key: &str, default: f64) -> f64 {
    data.get(key)
        .and_then(|v| v.as_f64().or_else(|| v.as_i64().map(|i| i as f64)))
        .unwrap_or(default)
}

fn extract_total(hits_data: &Map<String, Value>) -> u64 {
    match hits_data.get("total") {
        Some(Value::Object(total)) => total
            .get("value")
            .and_then(|v| v.as_u64().or_else(|| v.as_f64().map(|f| f as u64)))
            .unwrap_or(0),
        Some(Value::Number(number)) => number
            .as_u64()
            .or_else(|| number.as_f64().map(|f| f as u64))
            .unwrap_or(0),
        _ => 0,
    }
}

fn extract_snippet(raw: &Value) -> String {
    let highlight = match raw.get("highlight").and_then(|v| v.as_object()) {
        Some(value) => value,
        None => return String::new(),
    };
    let snippets = match highlight.get("text").and_then(|v| v.as_array()) {
        Some(value) => value,
        None => return String::new(),
    };
    let mut parts = Vec::new();
    for item in snippets.iter().take(3) {
        if let Some(text) = item.as_str() {
            parts.push(text.to_string());
        } else {
            parts.push(item.to_string());
        }
    }
    parts.join(" ... ")
}

fn extract_filed_date(source: &Map<String, Value>) -> String {
    let filed = source
        .get("file_date")
        .and_then(|v| v.as_str())
        .or_else(|| source.get("filed").and_then(|v| v.as_str()));
    if let Some(value) = filed {
        let trimmed = if value.len() >= 10 {
            &value[..10]
        } else {
            value
        };
        if let Ok(date) = NaiveDate::parse_from_str(trimmed, "%Y-%m-%d") {
            return date.format("%Y-%m-%d").to_string();
        }
    }
    Utc::now().date_naive().format("%Y-%m-%d").to_string()
}

fn extract_accession(source: &Map<String, Value>) -> String {
    let raw = source
        .get("adsh")
        .or_else(|| source.get("accession_number"));
    let accession = raw.and_then(value_to_string).unwrap_or_default();
    if !accession.is_empty() && !accession.contains('-') && accession.len() == 18 {
        format!(
            "{}-{}-{}",
            &accession[0..10],
            &accession[10..12],
            &accession[12..]
        )
    } else {
        accession
    }
}

fn extract_company_name(source: &Map<String, Value>) -> String {
    let form_type = get_str(source, "form", "");
    let normalized_form = form_type.replace(' ', "").to_uppercase();
    let company_raw = source.get("company");
    let display_names = extract_display_names(source.get("display_names"));

    if is_insider_form(&normalized_form) {
        if let Some(Value::String(company_name)) = company_raw {
            let trimmed = company_name.trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
        if let Some(best) = best_display_name(&display_names) {
            return best;
        }
    }

    if let Some(first) = display_names.first() {
        return first.clone();
    }
    if let Some(raw) = company_raw.and_then(value_to_string) {
        return raw;
    }
    String::new()
}

fn extract_display_names(value: Option<&Value>) -> Vec<String> {
    match value.and_then(|v| v.as_array()) {
        Some(values) => values
            .iter()
            .filter_map(|item| item.as_str().map(|s| s.to_string()))
            .collect(),
        None => Vec::new(),
    }
}

fn best_display_name(display_names: &[String]) -> Option<String> {
    let mut best_score = -100;
    let mut best_name: Option<String> = None;
    for item in display_names {
        let name = item.trim();
        if name.is_empty() {
            continue;
        }
        let upper = name.to_uppercase();
        let mut score = 0;
        if !upper.contains("CIK") {
            score += 2;
        }
        if name.contains('(') && name.contains(')') && !upper.contains("CIK") {
            score += 1;
        }
        if name.contains(',') {
            score -= 1;
        }
        for keyword in COMPANY_KEYWORDS {
            if upper.contains(keyword) {
                score += 2;
                break;
            }
        }
        if score > best_score {
            best_score = score;
            best_name = Some(name.to_string());
        }
    }
    best_name
}

fn extract_tickers(source: &Map<String, Value>, company_name: &str) -> Vec<String> {
    let mut tickers = Vec::new();
    match source.get("tickers") {
        Some(Value::Array(items)) => {
            for item in items {
                if let Some(ticker) = item.as_str() {
                    append_ticker(&mut tickers, ticker);
                }
            }
        }
        Some(Value::String(value)) => {
            for item in value.split(|ch: char| ch == ',' || ch == '/' || ch.is_whitespace()) {
                append_ticker(&mut tickers, item);
            }
        }
        _ => {}
    }
    if let Some(Value::String(value)) = source.get("ticker") {
        append_ticker(&mut tickers, value);
    }
    if tickers.is_empty() {
        tickers = extract_tickers_from_company(company_name);
    }
    tickers
}

fn extract_tickers_from_company(company_name: &str) -> Vec<String> {
    let mut tickers = Vec::new();
    if company_name.is_empty() {
        return tickers;
    }
    for caps in PAREN_PATTERN.captures_iter(company_name) {
        if let Some(match_value) = caps.get(1).map(|m| m.as_str()) {
            for raw in match_value.split([',', '/']) {
                let cleaned = raw.trim();
                if cleaned.is_empty() {
                    continue;
                }
                if cleaned.to_uppercase().contains("CIK") {
                    continue;
                }
                append_ticker(&mut tickers, cleaned);
            }
        }
    }
    tickers
}

fn append_ticker(tickers: &mut Vec<String>, value: &str) {
    if let Some(cleaned) = normalize_ticker(value) {
        if !tickers.contains(&cleaned) {
            tickers.push(cleaned);
        }
    }
}

fn normalize_ticker(value: &str) -> Option<String> {
    let mut cleaned = value.trim().to_uppercase();
    cleaned = cleaned
        .trim_matches(|ch: char| matches!(ch, '(' | ')' | '[' | ']' | '{' | '}'))
        .to_string();
    if cleaned.is_empty() {
        return None;
    }
    if cleaned.contains("CIK") {
        return None;
    }
    if let Some(index) = cleaned.rfind(':') {
        let suffix = cleaned[index + 1..].trim();
        if !suffix.is_empty() {
            cleaned = suffix.to_string();
        }
    }
    if !cleaned.chars().any(|ch| ch.is_ascii_alphabetic()) {
        return None;
    }
    if cleaned.len() > 10 {
        return None;
    }
    Some(cleaned)
}

fn extract_cik(source: &Map<String, Value>, company_name: &str, accession: &str) -> String {
    if let Some(cik) = coerce_cik(source.get("cik")) {
        return cik;
    }
    if let Some(Value::Array(items)) = source.get("ciks") {
        for item in items {
            if let Some(cik) = coerce_cik(Some(item)) {
                return cik;
            }
        }
    }
    if let Some(cik) = extract_cik_from_company(company_name) {
        return cik;
    }
    if let Some(cik) = extract_cik_from_accession(accession) {
        return cik;
    }
    "0000000000".to_string()
}

fn coerce_cik(value: Option<&Value>) -> Option<String> {
    let value = value?;
    if value.is_null() || value.is_boolean() {
        return None;
    }
    if let Some(number) = value.as_i64() {
        return coerce_cik_str(&number.to_string());
    }
    if let Some(number) = value.as_u64() {
        return coerce_cik_str(&number.to_string());
    }
    if let Some(number) = value.as_f64() {
        return coerce_cik_str(&(number as i64).to_string());
    }
    if let Some(text) = value.as_str() {
        return coerce_cik_str(text.trim());
    }
    None
}

fn coerce_cik_str(raw: &str) -> Option<String> {
    let digits: String = raw.chars().filter(|ch| ch.is_ascii_digit()).collect();
    if digits.is_empty() {
        return None;
    }
    let trimmed = if digits.len() > 10 {
        digits[digits.len() - 10..].to_string()
    } else {
        digits
    };
    let cik = format!("{:0>10}", trimmed);
    if cik == "0000000000" {
        return None;
    }
    Some(cik)
}

fn extract_cik_from_company(company_name: &str) -> Option<String> {
    if company_name.is_empty() {
        return None;
    }
    let captures = CIK_PATTERN.captures(company_name)?;
    let raw = captures.get(1)?.as_str();
    coerce_cik_str(raw)
}

fn extract_cik_from_accession(accession: &str) -> Option<String> {
    if accession.is_empty() {
        return None;
    }
    let prefix = accession
        .split_once('-')
        .map(|(p, _)| p)
        .unwrap_or(accession);
    coerce_cik_str(prefix)
}

fn is_insider_form(form: &str) -> bool {
    INSIDER_FORMS.contains(&form)
}

fn value_to_string(value: &Value) -> Option<String> {
    match value {
        Value::String(text) => Some(text.to_string()),
        Value::Number(number) => Some(number.to_string()),
        Value::Bool(flag) => Some(flag.to_string()),
        _ => None,
    }
}

fn json_to_py(py: Python<'_>, value: &Value) -> PyResult<PyObject> {
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(value) => value.into_py_any(py),
        Value::Number(value) => {
            if let Some(number) = value.as_i64() {
                number.into_py_any(py)
            } else if let Some(number) = value.as_u64() {
                number.into_py_any(py)
            } else if let Some(number) = value.as_f64() {
                number.into_py_any(py)
            } else {
                Ok(py.None())
            }
        }
        Value::String(value) => value.into_py_any(py),
        Value::Array(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(json_to_py(py, item)?)?;
            }
            list.into_py_any(py)
        }
        Value::Object(items) => {
            let dict = PyDict::new(py);
            for (key, item) in items {
                dict.set_item(key, json_to_py(py, item)?)?;
            }
            dict.into_py_any(py)
        }
    }
}

#[doc(hidden)]
pub mod test_support {
    use super::parse_response;
    use serde_json::{to_value, Value};

    pub fn parse_response_value(data: &Value, query: &str) -> Result<Value, serde_json::Error> {
        to_value(parse_response(data, query))
    }
}

#[pymodule]
fn efts(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<EftsClient>()?;
    m.add_function(wrap_pyfunction!(create_efts_client, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parse_response_matches_sample() {
        let sample = json!({
            "query": {"from": 0, "size": 10, "q": "warranty accrual"},
            "hits": {
                "total": {"value": 42},
                "hits": [
                    {
                        "_score": 15.5,
                        "_source": {
                            "adsh": "0001234567-24-000001",
                            "cik": "1234567",
                            "display_names": ["Apple Inc."],
                            "form": "10-K",
                            "file_date": "2024-01-15"
                        },
                        "highlight": {"text": ["warranty <em>accrual</em> provisions"]}
                    },
                    {
                        "_score": 12.3,
                        "_source": {
                            "adsh": "0009876543-24-000002",
                            "cik": "9876543",
                            "display_names": ["Microsoft Corporation"],
                            "form": "10-Q",
                            "file_date": "2024-02-20"
                        },
                        "highlight": {"text": ["product <em>warranty</em> reserves"]}
                    }
                ]
            }
        });

        let response = parse_response(&sample, "warranty accrual");

        assert_eq!(response.total, 42);
        assert_eq!(response.hits.len(), 2);
        assert_eq!(response.hits[0].company_name, "Apple Inc.");
        assert_eq!(response.hits[0].form_type, "10-K");
        assert!((response.hits[0].score - 15.5).abs() < 1e-6);
        assert_eq!(response.hits[0].cik, "0001234567");
        assert_eq!(response.hits[0].filed_date, "2024-01-15");
        assert!(response.hits[0].snippet.contains("warranty"));
    }

    #[test]
    fn parse_empty_response() {
        let empty = json!({
            "query": {"from": 0, "size": 10, "q": "nonexistent term"},
            "hits": {"total": {"value": 0}, "hits": []}
        });

        let response = parse_response(&empty, "nonexistent term");

        assert_eq!(response.total, 0);
        assert!(response.hits.is_empty());
    }

    #[test]
    fn parse_hit_normalizes_accession_and_ticker() {
        let raw = json!({
            "_score": 15.5,
            "_source": {
                "adsh": "000123456724000001",
                "cik": "1234567",
                "display_names": ["Apple Inc. (AAPL)"],
                "form": "10-K",
                "file_date": "2024-01-15"
            },
            "highlight": {"text": ["warranty <em>accrual</em>"]}
        });

        let hit = parse_hit(&raw);

        assert_eq!(hit.accession_number, "0001234567-24-000001");
        assert_eq!(hit.tickers, vec!["AAPL"]);
        assert!(hit.snippet.contains("warranty"));
    }

    #[test]
    fn parse_hit_prefers_issuer_for_insider_forms() {
        let raw = json!({
            "_score": 12.1,
            "_source": {
                "adsh": "0001801368-24-000123",
                "cik": "0002006182",
                "company": "MP Materials Corp",
                "display_names": [
                    "Dhillon Mannik S. (CIK 0002006182)",
                    "MP Materials Corp (MP)"
                ],
                "form": "4",
                "file_date": "2024-01-15"
            }
        });

        let hit = parse_hit(&raw);

        assert_eq!(hit.company_name, "MP Materials Corp");
    }

    #[test]
    fn validate_base_url_allows_sec_domains() {
        assert!(validate_base_url("https://efts.sec.gov/LATEST/search-index").is_ok());
        assert!(validate_base_url("https://www.sec.gov/Archives/edgar/data").is_ok());
    }

    #[test]
    fn validate_base_url_rejects_non_sec_domains() {
        assert!(validate_base_url("https://example.com").is_err());
        assert!(validate_base_url("http://efts.sec.gov/LATEST/search-index").is_err());
    }
}
