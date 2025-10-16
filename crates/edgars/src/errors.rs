// src/errors.rs - Simplified and unified error handling
use std::io;
use thiserror::Error;

/// Main error type for all operations
#[derive(Debug, Error)]
pub enum EdgarError {
    // Network errors
    #[error("network request failed: {0}")]
    Network(String),

    #[error("HTTP {status}: {message}")]
    HttpStatus { status: u16, message: String },

    #[error("request timed out after {0}s")]
    Timeout(u64),

    // Parsing errors
    #[error("failed to parse {format}: {reason}")]
    Parse { format: String, reason: String },

    #[error("invalid UTF-8 encoding: {0}")]
    Utf8(#[from] std::string::FromUtf8Error),

    // Validation errors
    #[error("invalid input: {0}")]
    Validation(String),

    #[error("unsupported format: {0}")]
    UnsupportedFormat(String),

    // I/O errors
    #[error("I/O error: {0}")]
    Io(#[from] io::Error),

    // Data errors
    #[error("not found: {0}")]
    NotFound(String),

    #[error("not implemented: {0}")]
    NotImplemented(String),
}

impl EdgarError {
    /// Check if this error is retryable
    pub fn is_retryable(&self) -> bool {
        matches!(
            self,
            EdgarError::Network(_) | EdgarError::Timeout(_) | EdgarError::HttpStatus { status: 500..=599, .. }
        )
    }

    /// Create HTTP status error
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
    fn from(e: tokio::time::error::Elapsed) -> Self {
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

/// Result type for all operations
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
