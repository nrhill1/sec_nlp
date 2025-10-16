//! Error types for the edgars crate.
//!
//! This module provides a unified error type [`EdgarError`] that encompasses
//! all possible error conditions in the library.

use std::io;
use thiserror::Error;

/// Main error type for all operations in the edgars crate.
///
/// This enum represents all possible error conditions that can occur
/// when interacting with the SEC EDGAR API and parsing its data.
#[derive(Debug, Error)]
pub enum EdgarError {
    /// Network request failed.
    #[error("network request failed: {0}")]
    Network(String),

    /// HTTP error response received.
    #[error("HTTP {status}: {message}")]
    HttpStatus {
        /// HTTP status code
        status: u16,
        /// Error message
        message: String,
    },

    /// Request timed out.
    #[error("request timed out after {0}s")]
    Timeout(u64),

    /// Failed to parse content in the specified format.
    #[error("failed to parse {format}: {reason}")]
    Parse {
        /// Format being parsed (e.g., "JSON", "HTML")
        format: String,
        /// Reason for parse failure
        reason: String,
    },

    /// Invalid UTF-8 encoding encountered.
    #[error("invalid UTF-8 encoding: {0}")]
    Utf8(#[from] std::string::FromUtf8Error),

    /// Invalid input provided.
    #[error("invalid input: {0}")]
    Validation(String),

    /// Unsupported format encountered.
    #[error("unsupported format: {0}")]
    UnsupportedFormat(String),

    /// I/O error occurred.
    #[error("I/O error: {0}")]
    Io(#[from] io::Error),

    /// Requested resource not found.
    #[error("not found: {0}")]
    NotFound(String),

    /// Feature not implemented.
    #[error("not implemented: {0}")]
    NotImplemented(String),
}

impl EdgarError {
    /// Check if this error is retryable.
    ///
    /// Network errors, timeouts, and 5xx HTTP errors are considered retryable.
    ///
    /// # Examples
    ///
    /// ```
    /// use edgars::EdgarError;
    ///
    /// let err = EdgarError::Network("connection reset".into());
    /// assert!(err.is_retryable());
    ///
    /// let err = EdgarError::http_status(404);
    /// assert!(!err.is_retryable());
    /// ```
    pub fn is_retryable(&self) -> bool {
        matches!(
            self,
            EdgarError::Network(_) | EdgarError::Timeout(_) | EdgarError::HttpStatus { status: 500..=599, .. }
        )
    }

    /// Create an HTTP status error with appropriate message.
    ///
    /// # Arguments
    ///
    /// * `code` - HTTP status code
    ///
    /// # Examples
    ///
    /// ```
    /// use edgars::EdgarError;
    ///
    /// let err = EdgarError::http_status(404);
    /// assert_eq!(err.to_string(), "HTTP 404: Not Found");
    /// ```
    pub fn http_status(code: u16) -> Self {
        let message = match code {
            400 => "Bad Request",
            401 => "Unauthorized",
            403 => "Forbidden - check User-Agent header",
            404 => "Not Found",
            429 => "Too Many Requests - rate limited",
            500 => "Internal Server Error",
            502 => "Bad Gateway",
            503 => "Service Unavailable",
            _ => "HTTP Error",
        };
        EdgarError::HttpStatus {
            status: code,
            message: message.to_string(),
        }
    }
}

// Conversions for common error types
impl From<hyper::Error> for EdgarError {
    fn from(e: hyper::Error) -> Self {
        EdgarError::Network(e.to_string())
    }
}

impl From<tokio::time::error::Elapsed> for EdgarError {
    fn from(_e: tokio::time::error::Elapsed) -> Self {
        EdgarError::Timeout(30) // Default timeout
    }
}

impl From<serde_json::Error> for EdgarError {
    fn from(e: serde_json::Error) -> Self {
        EdgarError::Parse {
            format: "JSON".to_string(),
            reason: e.to_string(),
        }
    }
}

impl From<url::ParseError> for EdgarError {
    fn from(e: url::ParseError) -> Self {
        EdgarError::Validation(format!("Invalid URL: {}", e))
    }
}

impl From<rusqlite::Error> for EdgarError {
    fn from(e: rusqlite::Error) -> Self {
        EdgarError::Validation(format!("SQL cache error: {}", e))
    }
}

/// Result type alias for operations that can return [`EdgarError`].
///
/// This is a convenience type alias for `std::result::Result<T, EdgarError>`.
///
/// # Examples
///
/// ```
/// use edgars::Result;
///
/// fn parse_something() -> Result<String> {
///     Ok("parsed".to_string())
/// }
/// ```
pub type Result<T> = std::result::Result<T, EdgarError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_is_retryable() {
        assert!(EdgarError::Network("test".into()).is_retryable());
        assert!(EdgarError::Timeout(30).is_retryable());
        assert!(EdgarError::http_status(503).is_retryable());
        assert!(!EdgarError::http_status(404).is_retryable());
        assert!(!EdgarError::Validation("test".into()).is_retryable());
    }

    #[test]
    fn test_http_status_messages() {
        match EdgarError::http_status(403) {
            EdgarError::HttpStatus { status, message } => {
                assert_eq!(status, 403);
                assert!(message.contains("Forbidden"));
            }
            _ => panic!("Expected HttpStatus error"),
        }
    }
}
