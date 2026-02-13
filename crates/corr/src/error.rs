use pyo3::exceptions::PyValueError;
use pyo3::PyErr;

#[derive(Debug, Clone)]
pub enum CorrError {
    EmptyInput(&'static str),
    LengthMismatch { left: usize, right: usize },
    InsufficientData { needed: usize, got: usize },
    NonFiniteValue(&'static str),
    ZeroVariance(&'static str),
    InvalidWindow(&'static str),
    InvalidParameter(&'static str),
}

impl CorrError {
    pub fn to_py_err(&self) -> PyErr {
        PyValueError::new_err(self.to_string())
    }
}

impl std::fmt::Display for CorrError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CorrError::EmptyInput(label) => {
                write!(f, "{} input cannot be empty", label)
            }
            CorrError::LengthMismatch { left, right } => {
                write!(f, "length mismatch: {} vs {}", left, right)
            }
            CorrError::InsufficientData { needed, got } => {
                write!(f, "need at least {} values, got {}", needed, got)
            }
            CorrError::NonFiniteValue(label) => {
                write!(f, "{} contains non-finite values", label)
            }
            CorrError::ZeroVariance(label) => {
                write!(f, "{} variance is zero", label)
            }
            CorrError::InvalidWindow(label) => {
                write!(f, "invalid window: {}", label)
            }
            CorrError::InvalidParameter(label) => {
                write!(f, "invalid parameter: {}", label)
            }
        }
    }
}

impl std::error::Error for CorrError {}

pub type CorrResult<T> = Result<T, CorrError>;
