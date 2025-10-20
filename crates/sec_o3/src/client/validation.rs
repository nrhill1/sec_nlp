use crate::errors::{Error, Result};
/// Request and response validation for SEC API compliance.
///
/// Ensures requests meet SEC requirements and validates responses
/// before processing.
use hyper::{HeaderMap, StatusCode};

/// Validate that a User-Agent header meets SEC requirements.
///
/// The SEC requires User-Agent headers to include:
/// - Company/application name
/// - Contact information (email)
///
/// # Arguments
///
/// * `user_agent` - The User-Agent string to validate
///
/// # Returns
///
/// * `Ok(())` - If the User-Agent is valid
/// * `Err` - If the User-Agent is invalid or missing required information
///
/// # Examples
///
/// ```
/// use sec_o3::client::validation::validate_user_agent;
///
/// Valid User-Agent
/// assert!(validate_user_agent("MyApp contact@example.com").is_ok());
///
/// Invalid - missing email
/// assert!(validate_user_agent("MyApp").is_err());
/// ```
pub fn validate_user_agent(user_agent: &str) -> Result<()> {
    if user_agent.is_empty() {
        return Err(Error::Custom("User-Agent cannot be empty".to_string()));
    }

    // Check for email-like pattern (simple validation)
    if !user_agent.contains('@') {
        return Err(Error::Custom(
            "User-Agent must include contact email per SEC requirements".to_string(),
        ));
    }

    // Check minimum length
    if user_agent.len() < 10 {
        return Err(Error::Custom(
            "User-Agent must include company name and contact information".to_string(),
        ));
    }

    Ok(())
}

/// Validate response headers from SEC API.
///
/// Checks for rate limit information and other important headers.
///
/// # Arguments
///
/// * `headers` - HTTP response headers
///
/// # Returns
///
/// Information extracted from headers, if any.
pub fn validate_response_headers(headers: &HeaderMap) -> ResponseInfo {
    let mut info = ResponseInfo::default();

    // Check for rate limit headers
    if let Some(remaining) = headers.get("x-ratelimit-remaining") {
        if let Ok(value) = remaining.to_str() {
            info.rate_limit_remaining = value.parse().ok();
        }
    }

    if let Some(reset) = headers.get("x-ratelimit-reset") {
        if let Ok(value) = reset.to_str() {
            info.rate_limit_reset = value.parse().ok();
        }
    }

    // Check content type
    if let Some(content_type) = headers.get("content-type") {
        if let Ok(value) = content_type.to_str() {
            info.content_type = Some(value.to_string());
        }
    }

    info
}

/// Information extracted from response headers.
#[derive(Debug, Default)]
pub struct ResponseInfo {
    /// Number of requests remaining in rate limit window
    pub rate_limit_remaining: Option<u32>,
    /// Timestamp when rate limit resets
    pub rate_limit_reset: Option<u64>,
    /// Content-Type of the response
    pub content_type: Option<String>,
}

impl ResponseInfo {
    /// Check if rate limit is close to being exceeded.
    ///
    /// Returns true if fewer than 2 requests remain.
    pub fn is_rate_limit_low(&self) -> bool {
        self.rate_limit_remaining.is_some_and(|r| r < 2)
    }
}

/// Validate that a response status is acceptable.
///
/// # Arguments
///
/// * `status` - HTTP status code
///
/// # Returns
///
/// * `Ok(())` - If status indicates success
/// * `Err` - If status indicates an error
pub fn validate_status(status: StatusCode) -> Result<()> {
    match status {
        StatusCode::OK => Ok(()),
        StatusCode::TOO_MANY_REQUESTS => Err(Error::RateLimitExceeded("Rate limit exceeded (429)".to_string())),
        StatusCode::NOT_FOUND => Err(Error::NotFound("Resource not found (404)".to_string())),
        status if status.is_client_error() => Err(Error::InvalidStatus(status)),
        status if status.is_server_error() => Err(Error::InvalidStatus(status)),
        status => Err(Error::InvalidStatus(status)),
    }
}

/// Validate SEC API base URL.
///
/// Ensures URLs point to official SEC domains.
///
/// # Arguments
///
/// * `url` - The URL to validate
///
/// # Returns
///
/// * `Ok(())` - If the URL is valid
/// * `Err` - If the URL is not an SEC domain
pub fn validate_sec_url(url: &str) -> Result<()> {
    let valid_domains = ["sec.gov", "data.sec.gov", "www.sec.gov", "efts.sec.gov"];

    let url_lower = url.to_lowercase();

    if !valid_domains.iter().any(|domain| url_lower.contains(domain)) {
        return Err(Error::Custom(format!(
            "URL must be from an official SEC domain: {}",
            url
        )));
    }

    if !url.starts_with("https://") {
        return Err(Error::Custom("SEC API URLs must use HTTPS".to_string()));
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_user_agent_valid() {
        assert!(validate_user_agent("MyApp contact@example.com").is_ok());
        assert!(validate_user_agent("Company/1.0 admin@company.com").is_ok());
    }

    #[test]
    fn test_validate_user_agent_invalid() {
        assert!(validate_user_agent("").is_err());
        assert!(validate_user_agent("MyApp").is_err()); // Missing email
        assert!(validate_user_agent("a@b.c").is_err()); // Too short
    }

    #[test]
    fn test_validate_status() {
        assert!(validate_status(StatusCode::OK).is_ok());
        assert!(validate_status(StatusCode::TOO_MANY_REQUESTS).is_err());
        assert!(validate_status(StatusCode::NOT_FOUND).is_err());
        assert!(validate_status(StatusCode::INTERNAL_SERVER_ERROR).is_err());
    }

    #[test]
    fn test_validate_sec_url() {
        assert!(validate_sec_url("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json").is_ok());
        assert!(validate_sec_url("https://www.sec.gov/cgi-bin/browse-edgar").is_ok());

        assert!(validate_sec_url("http://data.sec.gov/api").is_err()); // Not HTTPS
        assert!(validate_sec_url("https://evil.com/fake").is_err()); // Wrong domain
    }

    #[test]
    fn test_response_info_rate_limit_low() {
        let mut info = ResponseInfo::default();

        info.rate_limit_remaining = Some(5);
        assert!(!info.is_rate_limit_low());

        info.rate_limit_remaining = Some(1);
        assert!(info.is_rate_limit_low());

        info.rate_limit_remaining = None;
        assert!(!info.is_rate_limit_low());
    }
}
