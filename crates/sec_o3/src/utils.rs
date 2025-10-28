//! Shared utility functions
//!
//! Common helpers used across multiple modules

use chrono::{DateTime, Utc};

use crate::errors::{Error, Result};

/// Parse a date string into a UTC DateTime
///
/// Accepts two formats:
/// - Full ISO 8601 datetime with timezone (e.g., "2023-11-03T18:30:00.000Z")
/// - Date only in YYYY-MM-DD format (e.g., "2023-11-03")
///
/// For date-only strings, the time is set to midnight UTC (00:00:00.000Z).
///
/// # Arguments
///
/// * `date_str` - A string slice containing either a full ISO 8601 datetime or a date in YYYY-MM-DD format
///
/// # Returns
///
/// Returns a `Result<DateTime<Utc>>` containing the parsed datetime on success,
/// or an error if the string format is invalid or cannot be parsed.
///
/// # Errors
///
/// Returns `Error::Custom` if:
/// - The string doesn't match either supported format
/// - The date/datetime values are invalid (e.g., "2023-13-45")
/// - The string cannot be parsed as a valid datetime
///
/// # Examples
///
/// ```
/// use chrono::{DateTime, Utc};
/// use sec_o3::utils::str_to_utc_datetime;
///
/// // Parse full ISO 8601 datetime
/// let dt = str_to_utc_datetime("2023-11-03T18:30:00.000Z").unwrap();
/// assert_eq!(dt.to_rfc3339(), "2023-11-03T18:30:00+00:00");
///
/// // Parse date only (time defaults to midnight UTC)
/// let dt = str_to_utc_datetime("2023-11-03").unwrap();
/// assert_eq!(dt.to_rfc3339(), "2023-11-03T00:00:00+00:00");
/// ```
pub fn str_to_utc_datetime(date_str: &str) -> Result<DateTime<Utc>> {
    if let Ok(dt) = DateTime::parse_from_rfc3339(date_str) {
        return Ok(dt.with_timezone(&Utc));
    }

    if date_str.len() == 10 && date_str.chars().filter(|&c| c == '-').count() == 2 {
        let full_datetime = format!("{}T00:00:00.000Z", date_str);
        return DateTime::parse_from_rfc3339(&full_datetime)
            .map(|dt| dt.with_timezone(&Utc))
            .map_err(|e| Error::Custom(format!("Failed to parse date '{}': {}", date_str, e)));
    }

    Err(Error::Custom(format!(
        "Invalid date format: '{}'. Expected ISO 8601 datetime or YYYY-MM-DD",
        date_str
    )))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_str_utc_datetime_full() {
        let dt = str_to_utc_datetime("2023-11-03T18:30:00.000Z").unwrap();
        assert_eq!(dt.to_rfc3339(), "2023-11-03T18:30:00+00:00");
    }

    #[test]
    fn test_str_utc_datetime_date_only() {
        let dt = str_to_utc_datetime("2023-11-03").unwrap();
        assert_eq!(dt.to_rfc3339(), "2023-11-03T00:00:00+00:00");
    }

    #[test]
    fn test_str_utc_datetime_invalid() {
        let result = str_to_utc_datetime("2023/11/31");
        assert!(result.is_err());
    }
}
