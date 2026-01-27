use pyo3::exceptions::PyRuntimeError;
use pyo3::PyErr;

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

    pub fn to_py_err(&self) -> PyErr {
        let mut message = format!(
            "EFTS API Error ({}): {}",
            self.status, self.message
        );
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
