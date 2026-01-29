use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;
use std::time::Duration;

use crate::constants::{DEFAULT_USER_AGENT, EFTS_BASE_URL};
use crate::error::EftsError;
use crate::http::{build_client, build_params, enforce_rate_limit, make_request};
use crate::http_async::{build_async_client, enforce_rate_limit_async, make_request_async};
use crate::models::{BatchSearchResult, ProgressInfo, SearchHit, SearchResponse};
use crate::parse::parse_response;
use crate::validate::validate_base_url;

#[pyclass(name = "EFTSClient")]
pub struct EftsClient {
    base_url: String,
    user_agent: String,
    timeout_seconds: f64,
    max_retries: usize,
    retry_delay_seconds: f64,
    rate_limit_delay_seconds: f64,
}

impl EftsClient {
    pub(crate) fn new_internal(
        user_agent: Option<String>,
        timeout: f64,
        max_retries: usize,
        retry_delay: f64,
        rate_limit_delay: f64,
        base_url: Option<String>,
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
        validate_base_url(&base_url)?;
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

    /// Async version of execute_search.
    #[allow(clippy::too_many_arguments)]
    pub(crate) async fn execute_search_async(
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
        let client = build_async_client(self.timeout_seconds)?;
        let mut delay_seconds = self.retry_delay_seconds;
        for attempt in 0..=self.max_retries {
            enforce_rate_limit_async(self.rate_limit_delay_seconds).await;
            match make_request_async(&client, &self.base_url, &params, &self.user_agent).await {
                Ok(data) => return Ok(parse_response(&data, query)),
                Err(err) => {
                    if attempt < self.max_retries && err.retryable {
                        if delay_seconds > 0.0 {
                            tokio::time::sleep(Duration::from_secs_f64(delay_seconds)).await;
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
            let hit_count = response.hits_vec.len();
            let has_more = (response.start as u64) + (response.hits_vec.len() as u64) < response.total;
            let next_offset = response.start + (response.hits_vec.len() as u32);
            all_hits.extend(response.hits_vec);
            if hit_count == 0 || !has_more {
                break;
            }
            offset = next_offset;
        }
        Ok(all_hits)
    }

    /// Async version of execute_search_all.
    #[allow(clippy::too_many_arguments)]
    pub(crate) async fn execute_search_all_async(
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
            let response = self
                .execute_search_async(
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
                )
                .await?;
            let hit_count = response.hits_vec.len();
            let has_more =
                (response.start as u64) + (response.hits_vec.len() as u64) < response.total;
            let next_offset = response.start + (response.hits_vec.len() as u32);
            all_hits.extend(response.hits_vec);
            if hit_count == 0 || !has_more {
                break;
            }
            offset = next_offset;
        }
        Ok(all_hits)
    }

    /// Async batch search - run multiple queries concurrently.
    ///
    /// Executes multiple search queries with rate limiting between them.
    /// Results are returned in the same order as the input queries.
    #[allow(clippy::too_many_arguments)]
    pub(crate) async fn execute_batch_search_async(
        &self,
        queries: &[String],
        forms: &[String],
        ciks: &[String],
        tickers: &[String],
        start_date: Option<&str>,
        end_date: Option<&str>,
        limit_per_query: u32,
        sort_field: &str,
        sort_order: &str,
    ) -> Vec<BatchSearchResult> {
        let mut results = Vec::with_capacity(queries.len());

        for query in queries {
            let result = self
                .execute_search_async(
                    query,
                    forms,
                    ciks,
                    tickers,
                    start_date,
                    end_date,
                    limit_per_query,
                    0,
                    sort_field,
                    sort_order,
                )
                .await;

            match result {
                Ok(response) => {
                    results.push(BatchSearchResult {
                        query: query.clone(),
                        hits_vec: response.hits_vec,
                        total: response.total,
                        error: None,
                    });
                }
                Err(err) => {
                    results.push(BatchSearchResult {
                        query: query.clone(),
                        hits_vec: Vec::new(),
                        total: 0,
                        error: Some(err.message),
                    });
                }
            }
        }

        results
    }

    /// Async version of execute_search_all with progress callback support.
    #[allow(clippy::too_many_arguments)]
    pub(crate) async fn execute_search_all_with_progress_async<F>(
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
        mut on_progress: F,
    ) -> Result<Vec<SearchHit>, EftsError>
    where
        F: FnMut(ProgressInfo),
    {
        if max_results == 0 {
            return Ok(Vec::new());
        }
        let mut all_hits: Vec<SearchHit> = Vec::new();
        let mut offset = 0;
        let page_size = std::cmp::min(100, max_results);
        let mut current_page = 0u32;
        let mut total_hits = 0u64;
        let mut total_pages = 1u32; // Will be updated after first request

        while (all_hits.len() as u32) < max_results {
            let remaining = max_results - (all_hits.len() as u32);
            let fetch_size = std::cmp::min(page_size, remaining);
            let response = self
                .execute_search_async(
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
                )
                .await?;

            // Update totals on first page
            if current_page == 0 {
                total_hits = response.total;
                let effective_max = std::cmp::min(max_results as u64, total_hits);
                total_pages = ((effective_max + 99) / 100) as u32;
                if total_pages == 0 {
                    total_pages = 1;
                }
            }

            current_page += 1;
            let hit_count = response.hits_vec.len();
            let has_more =
                (response.start as u64) + (response.hits_vec.len() as u64) < response.total;
            let next_offset = response.start + (response.hits_vec.len() as u32);
            all_hits.extend(response.hits_vec);

            // Report progress
            on_progress(ProgressInfo {
                current_page,
                total_pages,
                hits_fetched: all_hits.len() as u32,
                total_hits,
                query: query.to_string(),
            });

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
            base_url=None
        )
    )]
    pub fn new(
        user_agent: Option<String>,
        timeout: f64,
        max_retries: usize,
        retry_delay: f64,
        rate_limit_delay: f64,
        base_url: Option<String>,
    ) -> PyResult<Self> {
        Self::new_internal(
            user_agent,
            timeout,
            max_retries,
            retry_delay,
            rate_limit_delay,
            base_url,
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
    /// Execute a search and return native EFTSSearchResponse.
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
    ) -> PyResult<Py<SearchResponse>> {
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
        // Return native PyO3 class directly - no JSON serialization!
        Py::new(py, response)
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
    /// Execute an async search and return a Python awaitable.
    ///
    /// This is the async version of `search()`. It returns a coroutine that
    /// can be awaited in Python async code.
    ///
    /// Example:
    ///     response = await client.search_async("warranty", limit=10)
    fn search_async<'py>(
        &self,
        py: Python<'py>,
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
    ) -> PyResult<Bound<'py, PyAny>> {
        let forms = forms.unwrap_or_default();
        let ciks = ciks.unwrap_or_default();
        let tickers = tickers.unwrap_or_default();

        // Clone self fields needed for the async closure
        let base_url = self.base_url.clone();
        let user_agent = self.user_agent.clone();
        let timeout_seconds = self.timeout_seconds;
        let max_retries = self.max_retries;
        let retry_delay_seconds = self.retry_delay_seconds;
        let rate_limit_delay_seconds = self.rate_limit_delay_seconds;

        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            // Recreate a temporary client struct for the async search
            let client = EftsClient {
                base_url,
                user_agent,
                timeout_seconds,
                max_retries,
                retry_delay_seconds,
                rate_limit_delay_seconds,
            };

            let response = client
                .execute_search_async(
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
                .await
                .map_err(|err| err.to_py_err())?;

            // Return native PyO3 class
            Python::with_gil(|py| Py::new(py, response))
        })
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
    /// Fetch all results up to max_results, returning list of EFTSHit.
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
    ) -> PyResult<Vec<Py<SearchHit>>> {
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
        // Return native PyO3 list of EFTSHit - no JSON serialization!
        hits.into_iter()
            .map(|hit| Py::new(py, hit))
            .collect()
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
            max_results=100,
            sort_field="score".to_string(),
            sort_order="desc".to_string()
        )
    )]
    /// Async version of search_all - fetch all results up to max_results.
    ///
    /// Returns a Python awaitable that resolves to a list of EFTSHit.
    ///
    /// Example:
    ///     hits = await client.search_all_async("warranty", max_results=200)
    fn search_all_async<'py>(
        &self,
        py: Python<'py>,
        query: String,
        forms: Option<Vec<String>>,
        ciks: Option<Vec<String>>,
        tickers: Option<Vec<String>>,
        start_date: Option<String>,
        end_date: Option<String>,
        max_results: u32,
        sort_field: String,
        sort_order: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let forms = forms.unwrap_or_default();
        let ciks = ciks.unwrap_or_default();
        let tickers = tickers.unwrap_or_default();

        // Clone self fields needed for the async closure
        let base_url = self.base_url.clone();
        let user_agent = self.user_agent.clone();
        let timeout_seconds = self.timeout_seconds;
        let max_retries = self.max_retries;
        let retry_delay_seconds = self.retry_delay_seconds;
        let rate_limit_delay_seconds = self.rate_limit_delay_seconds;

        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let client = EftsClient {
                base_url,
                user_agent,
                timeout_seconds,
                max_retries,
                retry_delay_seconds,
                rate_limit_delay_seconds,
            };

            let hits = client
                .execute_search_all_async(
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
                .await
                .map_err(|err| err.to_py_err())?;

            // Return native PyO3 list of EFTSHit
            Python::with_gil(|py| {
                hits.into_iter()
                    .map(|hit| Py::new(py, hit))
                    .collect::<PyResult<Vec<Py<SearchHit>>>>()
            })
        })
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(
        signature = (
            queries,
            forms=None,
            ciks=None,
            tickers=None,
            start_date=None,
            end_date=None,
            limit_per_query=10,
            sort_field="score".to_string(),
            sort_order="desc".to_string()
        )
    )]
    /// Execute multiple search queries asynchronously.
    ///
    /// Returns a Python awaitable that resolves to a list of EFTSBatchResult.
    /// Each result contains the query, hits, total count, and any error.
    ///
    /// Python Example:
    ///
    /// ```text
    /// results = await client.batch_search_async(
    ///     ["warranty accrual", "product liability"],
    ///     forms=["10-K"],
    ///     limit_per_query=20
    /// )
    /// for result in results:
    ///     print(f"{result.query}: {len(result.hits)} hits")
    /// ```
    fn batch_search_async<'py>(
        &self,
        py: Python<'py>,
        queries: Vec<String>,
        forms: Option<Vec<String>>,
        ciks: Option<Vec<String>>,
        tickers: Option<Vec<String>>,
        start_date: Option<String>,
        end_date: Option<String>,
        limit_per_query: u32,
        sort_field: String,
        sort_order: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let forms = forms.unwrap_or_default();
        let ciks = ciks.unwrap_or_default();
        let tickers = tickers.unwrap_or_default();

        // Clone self fields needed for the async closure
        let base_url = self.base_url.clone();
        let user_agent = self.user_agent.clone();
        let timeout_seconds = self.timeout_seconds;
        let max_retries = self.max_retries;
        let retry_delay_seconds = self.retry_delay_seconds;
        let rate_limit_delay_seconds = self.rate_limit_delay_seconds;

        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let client = EftsClient {
                base_url,
                user_agent,
                timeout_seconds,
                max_retries,
                retry_delay_seconds,
                rate_limit_delay_seconds,
            };

            let results = client
                .execute_batch_search_async(
                    &queries,
                    &forms,
                    &ciks,
                    &tickers,
                    start_date.as_deref(),
                    end_date.as_deref(),
                    limit_per_query,
                    &sort_field,
                    &sort_order,
                )
                .await;

            // Return native PyO3 list of BatchSearchResult
            Python::with_gil(|py| {
                results
                    .into_iter()
                    .map(|result| Py::new(py, result))
                    .collect::<PyResult<Vec<Py<BatchSearchResult>>>>()
            })
        })
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(
        signature = (
            query,
            on_progress,
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
    /// Async search_all with progress callback.
    ///
    /// The progress callback is called after each page is fetched with an
    /// EFTSProgress object containing current page, total pages, and hit counts.
    ///
    /// Python Example:
    ///
    /// ```text
    /// def on_progress(p):
    ///     print(f"Page {p.current_page}/{p.total_pages}")
    ///
    /// hits = await client.search_all_with_progress_async(
    ///     "warranty",
    ///     on_progress=on_progress,
    ///     max_results=500
    /// )
    /// ```
    fn search_all_with_progress_async<'py>(
        &self,
        py: Python<'py>,
        query: String,
        on_progress: PyObject,
        forms: Option<Vec<String>>,
        ciks: Option<Vec<String>>,
        tickers: Option<Vec<String>>,
        start_date: Option<String>,
        end_date: Option<String>,
        max_results: u32,
        sort_field: String,
        sort_order: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let forms = forms.unwrap_or_default();
        let ciks = ciks.unwrap_or_default();
        let tickers = tickers.unwrap_or_default();

        // Clone self fields needed for the async closure
        let base_url = self.base_url.clone();
        let user_agent = self.user_agent.clone();
        let timeout_seconds = self.timeout_seconds;
        let max_retries = self.max_retries;
        let retry_delay_seconds = self.retry_delay_seconds;
        let rate_limit_delay_seconds = self.rate_limit_delay_seconds;

        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let client = EftsClient {
                base_url,
                user_agent,
                timeout_seconds,
                max_retries,
                retry_delay_seconds,
                rate_limit_delay_seconds,
            };

            let hits = client
                .execute_search_all_with_progress_async(
                    &query,
                    &forms,
                    &ciks,
                    &tickers,
                    start_date.as_deref(),
                    end_date.as_deref(),
                    max_results,
                    &sort_field,
                    &sort_order,
                    |progress| {
                        // Call the Python callback with progress info
                        Python::with_gil(|py| {
                            if let Ok(progress_obj) = Py::new(py, progress) {
                                let _ = on_progress.call1(py, (progress_obj,));
                            }
                        });
                    },
                )
                .await
                .map_err(|err| err.to_py_err())?;

            // Return native PyO3 list of EFTSHit
            Python::with_gil(|py| {
                hits.into_iter()
                    .map(|hit| Py::new(py, hit))
                    .collect::<PyResult<Vec<Py<SearchHit>>>>()
            })
        })
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
        vec!["sec.gov".to_string()]
    }
}
