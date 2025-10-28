//! SEC EDGAR filing downloads and metadata retrieval.
//!
//! This module provides functions to:
//! - Fetch company submission history
//! - Download specific filing documents (XML, HTML, text)
//! - Parse filing metadata and document URLs
use chrono::{DateTime, Datelike, Utc};
use serde::Deserialize;

/// Company submissions metadata from SEC API
///
/// Contains comprehensive information about a company including
/// identifying information and filing history.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Submissions {
    /// Company's Central Index Key (10-digit format)
    pub cik: String,
    /// Entity type (e.g., "operating", "foreign")
    pub entity_type: String,
    /// Standard Industrial Classification code
    pub sic: String,
    /// Human-readable description of the SIC code
    pub sic_description: String,
    /// Company name as registered with the SEC
    pub name: String,
    /// List of ticker symbols (can be multiple or empty)
    pub tickers: Vec<String>,
    /// List of exchanges where the company is listed
    pub exchanges: Vec<String>,
    /// Filing history for this company
    pub filings: Filings,
}

/// Filing history for a company
///
/// Contains recent filings and may include older filings
/// in the `files` field (not implemented here).
#[derive(Debug, Deserialize)]
pub struct Filings {
    /// Recent filings data
    pub recent: RecentFilings,
}

/// Recent filings data
///
/// All vectors have the same length, with indices corresponding
/// to individual filings. Each index represents one filing.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecentFilings {
    /// Accession numbers (e.g., "0000320193-23-000106")
    pub accession_number: Vec<String>,
    /// Filing dates in YYYY-MM-DD format
    #[serde(default)]
    pub filing_date: Vec<String>,
    /// Report period end dates in YYYY-MM-DD format
    #[serde(default)]
    pub report_date: Vec<String>,
    /// Acceptance timestamps (ISO 8601 format)
    #[serde(default)]
    pub acceptance_date_time: Vec<String>,
    /// Securities Act under which filed (e.g., "33", "34")
    #[serde(default)]
    pub act: Vec<String>,
    /// Form types (e.g., "10-K", "8-K", "DEF 14A")
    #[serde(default)]
    pub form: Vec<String>,
    /// SEC file numbers
    #[serde(default)]
    pub file_number: Vec<String>,
    /// Film numbers (legacy identifier)
    #[serde(default)]
    pub film_number: Vec<String>,
    /// Items disclosed (for 8-K filings)
    #[serde(default)]
    pub items: Vec<String>,
    /// Filing sizes in bytes
    #[serde(default)]
    pub size: Vec<i64>,
    /// Whether filing contains XBRL data (1 = yes, 0 = no)
    #[serde(rename(deserialize = "isXRBL"))]
    #[serde(default)]
    pub is_xbrl: Vec<i32>,
    /// Whether filing contains Inline XBRL (1 = yes, 0 = no)
    #[serde(rename(deserialize = "isInlineXRBL"))]
    #[serde(default)]
    pub is_inline_xbrl: Vec<i32>,
    /// Primary document filename (e.g., "aapl-20230930.htm")
    #[serde(default)]
    pub primary_document: Vec<String>,
    /// Description of primary document
    #[serde(default)]
    pub primary_doc_description: Vec<String>,
}

/// A specific filing document
///
/// Represents a single SEC filing with methods to construct
/// URLs for downloading documents.
#[derive(Debug, Clone)]
pub struct Filing {
    /// Company's Central Index Key
    pub cik: String,
    /// Unique filing identifier (e.g., "0000320193-23-000106")
    pub accession_number: String,
    /// Form type (e.g., "10-K", "8-K")
    pub form_type: String,
    /// Acceptance date as a chrono::DateTime
    pub acceptance_date: DateTime<Utc>,
    /// Primary document filename
    pub primary_document: String,
    /// Whether this filing contains XBRL data
    pub is_xbrl: bool,
}

impl Submissions {
    /// Get all recent filings as a Vec<Filing>
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///     let filings = submissions.recent_filings();
    ///     println!("Found {} filings", filings.len());
    ///     Ok(())
    /// }
    /// ```
    pub fn recent_filings(&self) -> Vec<Filing> {
        self.filings.recent.to_filings(&self.cik)
    }

    /// Get recent filings of a specific form type
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///     let ten_ks = submissions.recent_filings_by_form("10-K");
    ///     println!("Found {} 10-K filings", ten_ks.len());
    ///     Ok(())
    /// }
    /// ```
    pub fn recent_filings_by_form(&self, form_type: &str) -> Vec<Filing> {
        self.filings.recent.filter_by_form(&self.cik, form_type)
    }

    /// Get recent filings within a date range
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    /// use chrono::{TimeZone, Utc};
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///
    ///     let start = Utc.with_ymd_and_hms(2023, 1, 1, 0, 0, 0).unwrap();
    ///     let end = Utc.with_ymd_and_hms(2023, 12, 31, 23, 59, 59).unwrap();
    ///     let filings_2023 = submissions.recent_filings_by_date(start, end);
    ///
    ///     println!("Found {} filings in 2023", filings_2023.len());
    ///     Ok(())
    /// }
    /// ```
    pub fn recent_filings_by_date(&self, start: DateTime<Utc>, end: DateTime<Utc>) -> Vec<Filing> {
        self.filings.recent.filter_by_date_range(&self.cik, start, end)
    }
}

impl RecentFilings {
    /// Convert parallel vectors into a Vec of Filing objects
    ///
    /// # Arguments
    /// * `cik` - The company's CIK (needed for Filing construction)
    ///
    /// # Returns
    /// Vector of Filing objects, sorted by acceptance date (newest first)
    ///
    /// # Note
    /// Skips filings with invalid or missing data
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///     let filings = submissions.filings.recent.to_filings(&submissions.cik);
    ///     println!("Found {} filings", filings.len());
    ///     Ok(())
    /// }
    /// ```
    pub fn to_filings(&self, cik: &str) -> Vec<Filing> {
        let mut filings: Vec<Filing> = self
            .accession_number
            .iter()
            .enumerate()
            .filter_map(|(i, acc_no)| {
                // Get form type, skip if missing
                let form_type = self.form.get(i)?.clone();

                // Parse acceptance date, skip if invalid
                let acceptance_date_str = self.acceptance_date_time.get(i)?;
                let acceptance_date = DateTime::parse_from_rfc3339(acceptance_date_str)
                    .ok()?
                    .with_timezone(&Utc);

                // Get primary document, skip if missing
                let primary_document = self.primary_document.get(i)?.clone();

                // Check if this is an XBRL filing (default to false if missing)
                let is_xbrl = self.is_xbrl.get(i).copied().unwrap_or(0) == 1;

                Some(Filing {
                    cik: cik.to_string(),
                    accession_number: acc_no.clone(),
                    form_type,
                    acceptance_date,
                    primary_document,
                    is_xbrl,
                })
            })
            .collect();

        // Sort by acceptance date, newest first
        filings.sort_by(|a, b| b.acceptance_date.cmp(&a.acceptance_date));

        filings
    }

    /// Get filings filtered by form type
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///     let ten_ks = submissions.filings.recent.filter_by_form(&submissions.cik, "10-K");
    ///     println!("Found {} 10-K filings", ten_ks.len());
    ///     Ok(())
    /// }
    /// ```
    pub fn filter_by_form(&self, cik: &str, form_type: &str) -> Vec<Filing> {
        self.to_filings(cik)
            .into_iter()
            .filter(|f| f.form_type == form_type)
            .collect()
    }

    /// Get filings within a date range (inclusive)
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    /// use chrono::{TimeZone, Utc};
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///
    ///     let start = Utc.with_ymd_and_hms(2023, 1, 1, 0, 0, 0).unwrap();
    ///     let end = Utc.with_ymd_and_hms(2023, 12, 31, 23, 59, 59).unwrap();
    ///     let filings_2023 = submissions.filings.recent
    ///         .filter_by_date_range(&submissions.cik, start, end);
    ///
    ///     println!("Found {} filings in 2023", filings_2023.len());
    ///     Ok(())
    /// }
    /// ```
    pub fn filter_by_date_range(&self, cik: &str, start: DateTime<Utc>, end: DateTime<Utc>) -> Vec<Filing> {
        self.to_filings(cik)
            .into_iter()
            .filter(|f| f.acceptance_date >= start && f.acceptance_date <= end)
            .collect()
    }

    /// Get filings by form type within a date range
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    /// use chrono::{TimeZone, Utc};
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///
    ///     let start = Utc.with_ymd_and_hms(2023, 1, 1, 0, 0, 0).unwrap();
    ///     let end = Utc.with_ymd_and_hms(2023, 12, 31, 23, 59, 59).unwrap();
    ///     let ten_ks_2023 = submissions.filings.recent
    ///         .filter_by_form_and_date(&submissions.cik, "10-K", start, end);
    ///
    ///     println!("Found {} 10-K filings in 2023", ten_ks_2023.len());
    ///     Ok(())
    /// }
    /// ```
    pub fn filter_by_form_and_date(
        &self,
        cik: &str,
        form_type: &str,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
    ) -> Vec<Filing> {
        self.to_filings(cik)
            .into_iter()
            .filter(|f| f.form_type == form_type && f.acceptance_date >= start && f.acceptance_date <= end)
            .collect()
    }

    /// Get only XBRL filings
    pub fn filter_xbrl(&self, cik: &str) -> Vec<Filing> {
        self.to_filings(cik).into_iter().filter(|f| f.is_xbrl).collect()
    }

    /// Number of recent filings
    pub fn len(&self) -> usize {
        self.accession_number.len()
    }

    /// Check if there are no recent filings
    pub fn is_empty(&self) -> bool {
        self.accession_number.is_empty()
    }
}

impl Filing {
    /// Get the base URL for this filing's documents
    pub fn base_url(&self) -> String {
        let acc_no_dashes = self.accession_number.replace("-", "");
        format!(
            "https://www.sec.gov/Archives/edgar/data/{}/{}/",
            self.cik, acc_no_dashes
        )
    }

    /// Get the URL for the primary document
    pub fn primary_document_url(&self) -> String {
        format!("{}{}", self.base_url(), self.primary_document)
    }

    /// Get the URL for the full submission text file
    pub fn submission_text_url(&self) -> String {
        let acc_no_dashes = self.accession_number.replace("-", "");
        format!(
            "https://www.sec.gov/Archives/edgar/data/{}/{}/{}.txt",
            self.cik, acc_no_dashes, self.accession_number
        )
    }

    /// Get the year from the acceptance date
    pub fn year(&self) -> i32 {
        self.acceptance_date.year()
    }

    /// Check if this filing matches a specific form type
    pub fn is_form(&self, form_type: &str) -> bool {
        self.form_type == form_type
    }

    /// Check if this is an annual report (10-K)
    pub fn is_annual_report(&self) -> bool {
        self.form_type == "10-K"
    }

    /// Check if this is a quarterly report (10-Q)
    pub fn is_quarterly_report(&self) -> bool {
        self.form_type == "10-Q"
    }

    /// Check if this is a current report (8-K)
    pub fn is_current_report(&self) -> bool {
        self.form_type == "8-K"
    }

    /// Check if this filing is from a specific year
    pub fn is_from_year(&self, year: i32) -> bool {
        self.acceptance_date.year() == year
    }

    /// Check if acceptance date falls within a date range (inclusive)
    pub fn is_in_date_range(&self, start: DateTime<Utc>, end: DateTime<Utc>) -> bool {
        self.acceptance_date >= start && self.acceptance_date <= end
    }
}
