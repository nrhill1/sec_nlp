use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::time::Duration;

use crate::constants::{DEFAULT_USER_AGENT, EFTS_BASE_URL, SEC_HOST_SUFFIX};
use crate::error::EftsError;
use crate::http::{build_client, build_params, enforce_rate_limit, make_request};
use crate::models::{SearchHit, SearchResponse};
use crate::parse::parse_response;
use crate::python::json_to_py;
use crate::validate::validate_base_url_with_allowlist;

#[pyclass(name = "EFTSClient")]
pub struct EftsClient {
    base_url: String,
    user_agent: String,
    timeout_seconds: f64,
    max_retries: usize,
    retry_delay_seconds: f64,
    rate_limit_delay_seconds: f64,
    allowed_hosts: Vec<String>,
}

impl EftsClient {
    pub(crate) fn new_internal(
        user_agent: Option<String>,
        timeout: f64,
        max_retries: usize,
        retry_delay: f64,
        rate_limit_delay: f64,
        base_url: Option<String>,
        allowed_hosts: Option<Vec<String>>,
    ) -> Result<Self, EftsError> {
        if timeout <= 0.0 {
            return Err(EftsError::new(
                0,
                "timeout must be > 0",
                None,
                false,
            ));
        }
        if retry_delay < 0.0 {
            return Err(EftsError::new(
                0,
                "retry_delay must be >= 0",
                None,
                false,
            ));
        }
        if rate_limit_delay < 0.0 {
            return Err(EftsError::new(
                0,
                "rate_limit_delay must be >= 0",
                None,
                false,
            ));
        }
        let user_agent =
            user_agent.unwrap_or_else(|| DEFAULT_USER_AGENT.to_string());
        let base_url = base_url.unwrap_or_else(|| EFTS_BASE_URL.to_string());
        let allowed_hosts = match allowed_hosts {
            Some(hosts) if !hosts.is_empty() => hosts,
            _ => vec![SEC_HOST_SUFFIX.to_string()],
        };
        validate_base_url_with_allowlist(&base_url, &allowed_hosts)?;
        Ok(Self {
            base_url,
            user_agent,
            timeout_seconds: timeout,
            max_retries,
            retry_delay_seconds: retry_delay,
            rate_limit_delay_seconds: rate_limit_delay,
            allowed_hosts,
        })
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn execute_search(
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
            query,
            forms,
            ciks,
            tickers,
            start_date,
            end_date,
            limit,
            start,
            sort_field,
            sort_order,
        );
        let client = build_client(self.timeout_seconds)?;
        let mut delay_seconds = self.retry_delay_seconds;
        for attempt in 0..=self.max_retries {
            enforce_rate_limit(self.rate_limit_delay_seconds);
            match make_request(&client, &self.base_url, &params, &self.user_agent)
            {
                Ok(data) => return Ok(parse_response(&data, query)),
                Err(err) => {
                    if attempt < self.max_retries && err.retryable {
                        if delay_seconds > 0.0 {
                            std::thread::sleep(Duration::from_secs_f64(
                                delay_seconds,
                            ));
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
    pub(crate) fn execute_search_all(
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
                query,
                forms,
                ciks,
                tickers,
                start_date,
                end_date,
                fetch_size,
                offset,
                sort_field,
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
            base_url=None,
            allowed_hosts=None
        )
    )]
    pub fn new(
        user_agent: Option<String>,
        timeout: f64,
        max_retries: usize,
        retry_delay: f64,
        rate_limit_delay: f64,
        base_url: Option<String>,
        allowed_hosts: Option<Vec<String>>,
    ) -> PyResult<Self> {
        Self::new_internal(
            user_agent,
            timeout,
            max_retries,
            retry_delay,
            rate_limit_delay,
            base_url,
            allowed_hosts,
        )
        .map_err(|err| PyValueError::new_err(err.message))
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
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
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
        let value = serde_json::to_value(hits)
            .map_err(|err| PyValueError::new_err(err.to_string()))?;
        json_to_py(py, &value)
    }

    #[getter]
    fn base_url(&self) -> &str {
        &self.base_url
    }

    #[getter]
    fn user_agent(&self) -> &str {
        &self.user_agent
    }

    #[getter]
    fn timeout(&self) -> f64 {
        self.timeout_seconds
    }

    #[getter]
    fn max_retries(&self) -> usize {
        self.max_retries
    }

    #[getter]
    fn retry_delay(&self) -> f64 {
        self.retry_delay_seconds
    }

    #[getter]
    fn rate_limit_delay(&self) -> f64 {
        self.rate_limit_delay_seconds
    }

    #[getter]
    fn allowed_hosts(&self) -> Vec<String> {
        self.allowed_hosts.clone()
    }
}
