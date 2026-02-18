use std::fmt::{Display, Formatter};

use pyo3::exceptions::PyValueError;
use pyo3::PyErr;

#[derive(Debug, Clone)]
pub struct NewswatchError {
    message: String,
}

impl NewswatchError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }

    pub fn to_py_err(&self) -> PyErr {
        PyValueError::new_err(self.to_string())
    }
}

impl Display for NewswatchError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for NewswatchError {}

impl From<reqwest::Error> for NewswatchError {
    fn from(value: reqwest::Error) -> Self {
        Self::new(value.to_string())
    }
}

impl From<serde_json::Error> for NewswatchError {
    fn from(value: serde_json::Error) -> Self {
        Self::new(value.to_string())
    }
}

impl From<regex::Error> for NewswatchError {
    fn from(value: regex::Error) -> Self {
        Self::new(value.to_string())
    }
}

impl From<NewswatchError> for PyErr {
    fn from(value: NewswatchError) -> Self {
        PyValueError::new_err(value.to_string())
    }
}
