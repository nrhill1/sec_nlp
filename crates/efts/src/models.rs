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
    /// Filed date as ISO string (YYYY-MM-DD)
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
    /// Hits stored internally; exposed via getter that returns list
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
