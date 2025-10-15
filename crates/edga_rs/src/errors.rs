// ============================================================================
// src/errors.rs - Centralized error handling
// ============================================================================
use std::io;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum NetworkError {
    #[error("network error: {0}")]
    General(String),
    #[error("HTTP status: {code}")]
    Status { code: u16 },
    #[error("hyper error: {0}")]
    Hyper(#[from] hyper::Error),
    #[error("request timed out")]
    Timeout(#[from] tokio::time::error::Elapsed),
}

impl NetworkError {
    pub fn is_retryable(&self) -> bool {
        matches!(
            self,
            NetworkError::General(_)
                | NetworkError::Hyper(_)
                | NetworkError::Timeout(_)
                | NetworkError::Status { code: 500..=599 }
        )
    }

    pub fn from_status(code: u16) -> Self {
        NetworkError::Status { code }
    }
}

#[derive(Debug, Error)]
pub enum ParseError {
    #[error("utf8 error: {0}")]
    Utf8(#[from] std::string::FromUtf8Error),
    #[error("str utf8 error: {0}")]
    StrUtf8(#[from] std::str::Utf8Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("parse error: {0}")]
    Format(String),
    #[error("invalid selector: {0}")]
    Selector(String),
}

#[derive(Debug, Error)]
pub enum IoError {
    #[error("i/o error: {0}")]
    Io(#[from] io::Error),
}

#[derive(Debug, Error)]
pub enum ValidationError {
    #[error("invalid input: {0}")]
    Invalid(String),
    #[error("unknown format: {0}")]
    UnknownFormat(String),
}

/// Errors that can occur during HTTP fetch operations
#[derive(Debug, Error)]
pub enum FetchError {
    #[error(transparent)]
    Network(#[from] NetworkError),
    #[error(transparent)]
    Parse(#[from] ParseError),
    #[error(transparent)]
    Io(#[from] IoError),
    #[error(transparent)]
    Validation(#[from] ValidationError),
}

impl FetchError {
    pub fn is_retryable(&self) -> bool {
        matches!(self, FetchError::Network(ne) if ne.is_retryable())
    }
}

/// Errors that can occur during ticker/CIK lookup operations
#[derive(Debug, Error)]
pub enum LookupError {
    #[error(transparent)]
    Network(#[from] NetworkError),
    #[error(transparent)]
    Parse(#[from] ParseError),
    #[error(transparent)]
    Io(#[from] IoError),
    #[error(transparent)]
    Validation(#[from] ValidationError),
    #[error(transparent)]
    Fetch(#[from] FetchError),
}

/// Errors that can occur during document parsing
#[derive(Debug, Error)]
pub enum ParserError {
    #[error("parsing error: {0}")]
    Parse(String),
    #[error(transparent)]
    ParseDetail(#[from] ParseError),
    #[error(transparent)]
    Validation(#[from] ValidationError),
    #[error("not implemented: {0}")]
    NotImplemented(String),
}

/// Errors that can occur during data ingestion
#[derive(Debug, Error)]
pub enum IngestError {
    #[error(transparent)]
    Network(#[from] NetworkError),
    #[error(transparent)]
    Parse(#[from] ParseError),
    #[error(transparent)]
    Io(#[from] IoError),
    #[error(transparent)]
    Validation(#[from] ValidationError),
}

/// Errors related to decoding operations
#[derive(Debug, Error)]
pub enum DecodeError {
    #[error(transparent)]
    Parse(#[from] ParseError),
    #[error(transparent)]
    Validation(#[from] ValidationError),
}
