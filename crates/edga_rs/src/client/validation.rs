// src/client/validation.rs - URL validation for SEC requests
use crate::errors::ValidationError;

/// Validate that a URL is suitable for SEC API requests
pub fn validate_sec_url(url: &str) -> Result<(), ValidationError> {
    let parsed = url::Url::parse(url).map_err(|e| ValidationError::Invalid(format!("Invalid URL: {}", e)))?;

    // Enforce HTTPS
    if parsed.scheme() != "https" {
        return Err(ValidationError::Invalid(
            "Only HTTPS URLs allowed for SEC requests".into(),
        ));
    }

    // Enforce sec.gov domain (with subdomains)
    if let Some(host) = parsed.host_str() {
        if !host.ends_with("sec.gov") {
            return Err(ValidationError::Invalid(format!(
                "Only sec.gov URLs allowed, got: {}",
                host
            )));
        }
    } else {
        return Err(ValidationError::Invalid("URL missing host".into()));
    }

    Ok(())
}

/// Check if a URL is a valid sec.gov URL without returning an error
pub fn is_valid_sec_url(url: &str) -> bool {
    validate_sec_url(url).is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_sec_urls() {
        assert!(validate_sec_url("https://www.sec.gov/cgi-bin/browse-edgar").is_ok());
        assert!(validate_sec_url("https://data.sec.gov/submissions/CIK0000320193.json").is_ok());
        assert!(validate_sec_url("https://sec.gov/Archives/edgar/data/320193/0000320193-23-000077.txt").is_ok());
    }

    #[test]
    fn test_invalid_urls() {
        // HTTP not allowed
        assert!(validate_sec_url("http://www.sec.gov/test").is_err());

        // Wrong domain
        assert!(validate_sec_url("https://www.example.com/test").is_err());

        // Invalid URL format
        assert!(validate_sec_url("not a url").is_err());
    }
}
