use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::PyErr;

// Create native Python exception: efts.EFTSAPIError
create_exception!(
    efts,
    EftsApiError,
    PyException,
    "Error from EFTS API request."
);

#[derive(Debug)]
pub struct EftsError {
    pub(crate) status: u16,
    pub(crate) message: String,
    pub(crate) detail: Option<String>,
    pub(crate) retryable: bool,
}

impl EftsError {
    pub fn new(
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

    /// Convert to native Python EFTSAPIError exception.
    /// The exception args are (status_code, message, detail).
    pub fn to_py_err(&self) -> PyErr {
        EftsApiError::new_err((self.status, self.message.clone(), self.detail.clone()))
    }

    /// Get formatted error message.
    pub fn formatted_message(&self) -> String {
        let mut message = format!("EFTS API Error ({}): {}", self.status, self.message);
        if let Some(detail) = &self.detail {
            if !detail.is_empty() {
                message.push_str("; ");
                message.push_str(detail);
            }
        }
        message
    }
}

impl std::fmt::Display for EftsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "EFTS API Error ({}): {}", self.status, self.message)
    }
}

impl std::error::Error for EftsError {}
