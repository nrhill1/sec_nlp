/// Error types for the SEC data downloader.
///
/// This module defines the error types that can occur when fetching and
/// processing SEC data using Hyper as the HTTP client.
use thiserror::Error as ThisError;

/// Result type alias using this crate's Error type.
pub type Result<T> = std::result::Result<T, Error>;

/// Errors that can occur when working with SEC data.
#[derive(ThisError, Debug)]
pub enum Error {
    /// Invalid CIK format or value.
    #[error("Invalid CIK: {0}")]
    InvalidCik(String),

    /// HTTP request failed.
    #[error("HTTP request failed: {0}")]
    HyperError(#[from] hyper::Error),

    /// HTTP-related error (e.g., invalid URI).
    #[error("HTTP error: {0}")]
    HttpError(#[from] hyper::http::Error),

    /// Failed to parse JSON response.
    #[error("JSON parsing failed: {0}")]
    JsonError(#[from] serde_json::Error),

    /// Failed to parse XML response.
    #[error("XML parsing failed: {0}")]
    XmlError(String),

    /// File I/O error.
    #[error("File I/O error: {0}")]
    IoError(#[from] std::io::Error),

    /// Rate limit exceeded.
    #[error("Rate limit exceeded: {0}")]
    RateLimitExceeded(String),

    /// Resource not found (404).
    #[error("Resource not found: {0}")]
    NotFound(String),

    /// Invalid response status code.
    #[error("Invalid response status: {0}")]
    InvalidStatus(hyper::StatusCode),

    /// Generic error with custom message.
    #[error("{0}")]
    Custom(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_display() {
        let err = Error::InvalidCik("test".to_string());
        assert_eq!(err.to_string(), "Invalid CIK: test");
    }

    #[test]
    fn test_error_from_conversion() {
        let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "file not found");
        let err: Error = io_err.into();
        assert!(matches!(err, Error::IoError(_)));
    }

    #[test]
    fn test_custom_error() {
        let err = Error::Custom("custom error message".to_string());
        assert_eq!(err.to_string(), "custom error message");
    }
}
