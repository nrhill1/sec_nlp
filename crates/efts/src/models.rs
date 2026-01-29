use pyo3::prelude::*;
use pyo3::types::PyDate;
use serde::Serialize;

/// Individual search result from EFTS API.
#[pyclass(name = "EFTSHit", frozen, module = "efts")]
#[derive(Debug, Clone, Serialize)]
pub struct SearchHit {
    #[pyo3(get)]
    pub accession_number: String,
    #[pyo3(get)]
    pub cik: String,
    #[pyo3(get)]
    pub company_name: String,
    #[pyo3(get)]
    pub tickers: Vec<String>,
    #[pyo3(get)]
    pub form_type: String,
    /// Filed date as ISO string (YYYY-MM-DD).
    /// Serializes as "filed_date" for JSON output.
    #[serde(rename = "filed_date")]
    pub filed_date_str: String,
    #[pyo3(get)]
    pub file_number: Option<String>,
    #[pyo3(get)]
    pub film_number: Option<String>,
    #[pyo3(get)]
    pub snippet: String,
    #[pyo3(get)]
    pub score: f64,
    #[pyo3(get)]
    pub filing_url: Option<String>,
}

#[pymethods]
impl SearchHit {
    /// Return filed_date as Python datetime.date object.
    #[getter]
    fn filed_date<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDate>> {
        // Parse "YYYY-MM-DD" string
        let parts: Vec<&str> = self.filed_date_str.split('-').collect();
        if parts.len() == 3 {
            let year: i32 = parts[0].parse().unwrap_or(2000);
            let month: u8 = parts[1].parse().unwrap_or(1);
            let day: u8 = parts[2].parse().unwrap_or(1);
            PyDate::new(py, year, month, day)
        } else {
            // Fallback to epoch
            PyDate::new(py, 2000, 1, 1)
        }
    }

    /// Generate EDGAR filing URL from accession number.
    #[getter]
    fn edgar_url(&self) -> String {
        let clean_accession = self.accession_number.replace('-', "");
        let cik_stripped = self.cik.trim_start_matches('0');
        format!(
            "https://www.sec.gov/Archives/edgar/data/{}/{}/",
            cik_stripped, clean_accession
        )
    }

    /// Return first ticker if available.
    #[getter]
    fn ticker(&self) -> Option<String> {
        self.tickers.first().cloned()
    }

    fn __repr__(&self) -> String {
        format!(
            "EFTSHit(accession={}, company={}, form={}, score={:.2})",
            self.accession_number, self.company_name, self.form_type, self.score
        )
    }
}

/// Paginated response from EFTS search API.
#[pyclass(name = "EFTSSearchResponse", frozen, module = "efts")]
#[derive(Debug, Clone, Serialize)]
pub struct SearchResponse {
    #[pyo3(get)]
    pub query: String,
    #[pyo3(get)]
    pub total: u64,
    #[pyo3(get)]
    pub start: u32,
    #[pyo3(get)]
    pub limit: u32,
    /// Hits stored internally; exposed via getter that returns list.
    /// Serializes as "hits" for JSON output.
    #[serde(rename = "hits")]
    pub hits_vec: Vec<SearchHit>,
}

#[pymethods]
impl SearchResponse {
    /// Return hits as a list of EFTSHit objects.
    #[getter]
    fn hits(&self, py: Python<'_>) -> PyResult<Vec<Py<SearchHit>>> {
        self.hits_vec
            .iter()
            .map(|hit| Py::new(py, hit.clone()))
            .collect()
    }

    /// Check if there are more results to fetch.
    #[getter]
    fn has_more(&self) -> bool {
        (self.start as u64) + (self.hits_vec.len() as u64) < self.total
    }

    /// Get the offset for the next page of results.
    #[getter]
    fn next_offset(&self) -> u32 {
        self.start + (self.hits_vec.len() as u32)
    }

    fn __repr__(&self) -> String {
        format!(
            "EFTSSearchResponse(query={}, total={}, hits={})",
            self.query,
            self.total,
            self.hits_vec.len()
        )
    }

    fn __len__(&self) -> usize {
        self.hits_vec.len()
    }
}

/// Result from a single query in a batch search.
#[pyclass(name = "EFTSBatchResult", frozen, module = "efts")]
#[derive(Debug, Clone, Serialize)]
pub struct BatchSearchResult {
    #[pyo3(get)]
    pub query: String,
    /// Hits from this query. Serializes as "hits".
    #[serde(rename = "hits")]
    pub hits_vec: Vec<SearchHit>,
    #[pyo3(get)]
    pub total: u64,
    /// Error message if this query failed.
    #[pyo3(get)]
    pub error: Option<String>,
}

#[pymethods]
 impl BatchSearchResult {
    /// Return hits as a list of EFTSHit objects.
    #[getter]
    fn hits(&self, py: Python<'_>) -> PyResult<Vec<Py<SearchHit>>> {
        self.hits_vec
            .iter()
            .map(|hit| Py::new(py, hit.clone()))
            .collect()
    }

    /// Check if this query succeeded.
    #[getter]
    fn success(&self) -> bool {
        self.error.is_none()
    }

    fn __repr__(&self) -> String {
        if let Some(ref err) = self.error {
            format!("EFTSBatchResult(query={}, error={})", self.query, err)
        } else {
            format!(
                "EFTSBatchResult(query={}, hits={}, total={})",
                self.query,
                self.hits_vec.len(),
                self.total
            )
        }
    }

    fn __len__(&self) -> usize {
        self.hits_vec.len()
    }
}

/// Progress information during paginated search.
#[pyclass(name = "EFTSProgress", frozen, module = "efts")]
#[derive(Debug, Clone)]
pub struct ProgressInfo {
    #[pyo3(get)]
    pub current_page: u32,
    #[pyo3(get)]
    pub total_pages: u32,
    #[pyo3(get)]
    pub hits_fetched: u32,
    #[pyo3(get)]
    pub total_hits: u64,
    #[pyo3(get)]
    pub query: String,
}

#[pymethods]
impl ProgressInfo {
    /// Progress as a fraction (0.0 to 1.0).
    #[getter]
    fn progress(&self) -> f64 {
        if self.total_pages == 0 {
            1.0
        } else {
            (self.current_page as f64) / (self.total_pages as f64)
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "EFTSProgress(page={}/{}, hits={}/{})",
            self.current_page, self.total_pages, self.hits_fetched, self.total_hits
        )
    }
}
