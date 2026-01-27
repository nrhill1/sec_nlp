use reqwest::Url;

use crate::constants::SEC_HOST_SUFFIX;
use crate::error::EftsError;

pub(crate) fn validate_base_url(base_url: &str) -> Result<(), EftsError> {
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
    if host_lower == SEC_HOST_SUFFIX || host_lower.ends_with(".sec.gov") {
        Ok(())
    } else {
        Err(EftsError::new(
            0,
            "base_url must use a sec.gov host",
            None,
            false,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::validate_base_url;

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
}
