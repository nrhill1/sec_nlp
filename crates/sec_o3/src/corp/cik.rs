//! CIK (Central Index Key) utilities.
//!
//! The CIK is a unique identifier assigned by the SEC to entities that file
//! disclosures. CIKs are 10-digit numbers, but are often represented without
//! leading zeros in various contexts.
//!
//! This module provides normalization functionality to ensure CIKs are in the
//! standard 10-digit format required by SEC APIs.

use crate::errors::Result;

/// Normalize a CIK to the standard 10-digit format with leading zeros.
///
/// The SEC's CIK system uses 10-digit identifiers, but they are often represented
/// without leading zeros (e.g., "320193" for Apple Inc.). This function ensures
/// the CIK is properly zero-padded to 10 digits.
///
/// # Arguments
///
/// * `cik` - A CIK string, which may or may not have leading zeros
///
/// # Returns
///
/// * `Ok(String)` - A normalized 10-digit CIK with leading zeros
/// * `Err` - If the CIK is invalid (empty, non-numeric, or too long)
///
/// # Errors
///
/// Returns an error if:
/// - The CIK is empty
/// - The CIK contains non-numeric characters
/// - The CIK is longer than 10 digits
///
/// # Examples
///
/// ```
/// use sec_o3::corp::normalize_cik;
///
/// // Short CIK gets zero-padded
/// assert_eq!(normalize_cik("320193").unwrap(), "0000320193");
///
/// // Already normalized CIK is unchanged
/// assert_eq!(normalize_cik("0000320193").unwrap(), "0000320193");
///
/// // Invalid CIKs return errors
/// assert!(normalize_cik("").is_err());
/// assert!(normalize_cik("abc").is_err());
/// assert!(normalize_cik("12345678901").is_err()); // too long
/// ```
pub fn normalize_cik(cik: &str) -> Result<String> {
    // Validate input
    if cik.is_empty() {
        return Err(crate::errors::Error::InvalidCik("CIK cannot be empty".to_string()));
    }

    // Check if all characters are digits
    if !cik.chars().all(|c| c.is_ascii_digit()) {
        return Err(crate::errors::Error::InvalidCik(format!(
            "CIK must contain only digits: {}",
            cik
        )));
    }

    // Check length
    if cik.len() > 10 {
        return Err(crate::errors::Error::InvalidCik(format!(
            "CIK cannot be longer than 10 digits: {}",
            cik
        )));
    }

    // Pad with leading zeros to 10 digits
    Ok(format!("{:0>10}", cik))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_short_cik() {
        assert_eq!(normalize_cik("320193").unwrap(), "0000320193");
        assert_eq!(normalize_cik("1").unwrap(), "0000000001");
        assert_eq!(normalize_cik("123").unwrap(), "0000000123");
    }

    #[test]
    fn test_normalize_already_normalized() {
        assert_eq!(normalize_cik("0000320193").unwrap(), "0000320193");
        assert_eq!(normalize_cik("0000000001").unwrap(), "0000000001");
    }

    #[test]
    fn test_normalize_ten_digits() {
        assert_eq!(normalize_cik("1234567890").unwrap(), "1234567890");
    }

    #[test]
    fn test_invalid_empty() {
        assert!(normalize_cik("").is_err());
    }

    #[test]
    fn test_invalid_non_numeric() {
        assert!(normalize_cik("abc").is_err());
        assert!(normalize_cik("123abc").is_err());
        assert!(normalize_cik("12-34").is_err());
    }

    #[test]
    fn test_invalid_too_long() {
        assert!(normalize_cik("12345678901").is_err());
        assert!(normalize_cik("123456789012345").is_err());
    }

    #[test]
    fn test_common_ciks() {
        // Apple
        assert_eq!(normalize_cik("320193").unwrap(), "0000320193");
        // Microsoft
        assert_eq!(normalize_cik("789019").unwrap(), "0000789019");
        // Tesla
        assert_eq!(normalize_cik("1318605").unwrap(), "0001318605");
    }
}
