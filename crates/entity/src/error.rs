use std::fmt::{Display, Formatter};

use pyo3::exceptions::PyValueError;
use pyo3::PyErr;

#[derive(Debug)]
pub struct EntityError {
    message: String,
}

impl EntityError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl Display for EntityError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for EntityError {}

impl From<std::io::Error> for EntityError {
    fn from(value: std::io::Error) -> Self {
        Self::new(value.to_string())
    }
}

impl From<serde_json::Error> for EntityError {
    fn from(value: serde_json::Error) -> Self {
        Self::new(value.to_string())
    }
}

impl From<EntityError> for PyErr {
    fn from(value: EntityError) -> Self {
        PyValueError::new_err(value.to_string())
    }
}
