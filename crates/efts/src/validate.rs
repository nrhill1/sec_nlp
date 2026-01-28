use reqwest::Url;

use crate::constants::SEC_HOST_SUFFIX;
use crate::error::EftsError;

pub(crate) fn validate_base_url(base_url: &str) -> Result<(), EftsError> {
    let allowed_hosts = vec![SEC_HOST_SUFFIX.to_string()];
    validate_base_url_with_allowlist(base_url, &allowed_hosts)
}

pub(crate) fn validate_base_url_with_allowlist(
    base_url: &str,
    allowed_hosts: &[String],
) -> Result<(), EftsError> {
    let url = Url::parse(base_url).map_err(|err| {
        EftsError::new(
            0,
            format!("base_url is invalid: {}", err),
            None,
            false,
        )
    })?;
    if url.scheme() != "https" {
        return Err(EftsError::new(0, "base_url must use https", None, false));
    }
    let host = url.host_str().ok_or_else(|| {
        EftsError::new(0, "base_url must include a host", None, false)
    })?;
    let host_lower = host.to_ascii_lowercase();
    let mut allowlisted = false;
    for allowed in allowed_hosts {
        let trimmed = allowed.trim().trim_start_matches('.');
        if trimmed.is_empty() {
            continue;
        }
        let allowed_lower = trimmed.to_ascii_lowercase();
        if host_lower == allowed_lower
            || host_lower.ends_with(&format!(".{}", allowed_lower))
        {
            allowlisted = true;
            break;
        }
    }
    if allowlisted {
        Ok(())
    } else {
        Err(EftsError::new(
            0,
            "base_url must use an allowed host",
            None,
            false,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::{validate_base_url, validate_base_url_with_allowlist};

    #[test]
    fn validate_base_url_allows_sec_domains() {
        assert!(validate_base_url(
            "https://efts.sec.gov/LATEST/search-index"
        )
        .is_ok());
        assert!(validate_base_url("https://www.sec.gov/Archives/edgar/data").is_ok());
    }

    #[test]
    fn validate_base_url_rejects_non_sec_domains() {
        assert!(validate_base_url("https://example.com").is_err());
        assert!(validate_base_url("http://efts.sec.gov/LATEST/search-index").is_err());
    }

    #[test]
    fn validate_base_url_uses_custom_allowlist() {
        let allowed = vec!["example.com".to_string()];
        assert!(validate_base_url_with_allowlist(
            "https://api.example.com/path",
            &allowed
        )
        .is_ok());
        assert!(validate_base_url_with_allowlist(
            "https://efts.sec.gov/LATEST/search-index",
            &allowed
        )
        .is_err());
    }
}
