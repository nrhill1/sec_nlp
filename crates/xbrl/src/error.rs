use pyo3::exceptions::PyValueError;
use pyo3::PyErr;

#[derive(Debug)]
pub enum XbrlError {
    Io(String),
}

impl XbrlError {
    pub fn to_py_err(&self) -> PyErr {
        PyValueError::new_err(self.to_string())
    }
}

impl std::fmt::Display for XbrlError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            XbrlError::Io(message) => write!(f, "I/O error: {}", message),
        }
    }
}

impl std::error::Error for XbrlError {}

impl From<std::io::Error> for XbrlError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value.to_string())
    }
}
