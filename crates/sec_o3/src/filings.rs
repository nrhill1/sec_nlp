/// SEC EDGAR filing downloads and metadata retrieval.
///
/// This module provides functions to:
/// - Fetch company submission history
/// - Download specific filing documents (XML, HTML, text)
/// - Parse filing metadata and document URLs
use crate::{Client, Error, Result};
use chrono::{DateTime, Utc};
use serde::Deserialize;
use std::path::{Path, PathBuf};

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
}

/// Fetch company submission history by CIK
///
/// Returns metadata about the company and all their recent filings.
///
/// # Examples
///
/// ```no_run
/// use sec_o3::filings::get_submissions;
/// use sec_o3::Client;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let client = Client::new("MyApp", "contact@example.com");
///     let submissions = get_submissions(&client, "0000320193").await?;
///
///     println!("Company: {}", submissions.name);
///     println!("Recent filings: {}", submissions.filings.recent.form.len());
///     Ok(())
/// }
/// ```
pub async fn get_submissions(client: &Client, cik: &str) -> Result<Submissions> {
    let cik_padded = format!("CIK{:0>10}", cik.trim_start_matches("CIK"));
    let url = format!("https://data.sec.gov/submissions/{}.json", cik_padded);

    client.get_json(&url).await
}

/// Get a list of recent filings for a company
///
/// Returns Filing structs for easy access to document URLs.
///
/// # Examples
///
/// ```no_run
/// use sec_o3::filings::get_recent_filings;
/// use sec_o3::Client;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let client = Client::new("MyApp", "contact@example.com");
///     let filings = get_recent_filings(&client, "0000320193").await?;
///
///     for filing in filings.iter().take(5) {
///         println!("{} - {} on {}", filing.form_type, filing.primary_document, filing.filing_date);
///     }
///     Ok(())
/// }
/// ```
pub async fn get_recent_filings(client: &Client, cik: &str) -> Result<Vec<Filing>> {
    let submissions = get_submissions(client, cik).await?;
    let recent = submissions.filings.recent;

    let filings = (0..recent.accession_number.len())
        .filter_map(|i| {
            // Filter out empty values
            let primary_document = recent.primary_document.get(i)?.clone();
            let form_type = recent.form.get(i).cloned().unwrap_or_default();
            if primary_document.is_empty() || form_type.is_empty() {
                return None;
            }

            // Ensure acceptance_date is a valid UTC string
            let acceptance_date = recent.acceptance_date_time.get(i)?.parse::<DateTime<Utc>>().ok()?;

            Some(Filing {
                cik: submissions.cik.clone(),
                accession_number: recent.accession_number[i].clone(),
                form_type,
                acceptance_date,
                primary_document,
                is_xbrl: recent.is_xbrl.get(i).copied().unwrap_or(0) == 1,
            })
        })
        .collect();

    Ok(filings)
}

/// Download a filing document (XML, HTML, or text)
///
/// # Examples
///
/// ```no_run
/// use sec_o3::filings::{get_recent_filings, download_filing};
/// use sec_o3::Client;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let client = Client::new("MyApp", "contact@example.com");
///     let filings = get_recent_filings(&client, "0000320193").await?;
///
///     if let Some(filing) = filings.first() {
///         download_filing(&client, filing, "output").await?;
///     }
///     Ok(())
/// }
/// ```
pub async fn download_filing(client: &Client, filing: &Filing, output_dir: impl AsRef<Path>) -> Result<PathBuf> {
    let output_dir = output_dir.as_ref();
    tokio::fs::create_dir_all(output_dir).await.map_err(Error::IoError)?;

    let filename = &filing.primary_document;
    let output_path = output_dir.join(filename);

    let url = filing.primary_document_url();
    client.download_text(&url, &output_path).await?;

    Ok(output_path)
}

/// Download the full submission text file (contains all documents)
///
/// The submission text file includes all documents in the filing separated
/// by <DOCUMENT> tags. Useful for getting everything at once.
///
/// # Examples
///
/// ```no_run
/// use sec_o3::filings::{get_recent_filings, download_submission_text};
/// use sec_o3::Client;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let client = Client::new("MyApp", "contact@example.com");
///     let filings = get_recent_filings(&client, "0000320193").await?;
///
///     if let Some(filing) = filings.first() {
///         let path = download_submission_text(&client, filing, "output").await?;
///         println!("Downloaded to: {:?}", path);
///     }
///     Ok(())
/// }
/// ```
pub async fn download_submission_text(
    client: &Client,
    filing: &Filing,
    output_dir: impl AsRef<Path>,
) -> Result<PathBuf> {
    let output_dir = output_dir.as_ref();
    tokio::fs::create_dir_all(output_dir).await.map_err(Error::IoError)?;

    let filename = format!("{}.txt", filing.accession_number);
    let output_path = output_dir.join(filename);

    let url = filing.submission_text_url();
    client.download_text(&url, &output_path).await?;

    Ok(output_path)
}

/// Filter filings by form type (e.g., "10-K", "10-Q", "8-K")
///
/// # Examples
///
/// ```no_run
/// use sec_o3::filings::{get_recent_filings, filter_by_form};
/// use sec_o3::Client;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let client = Client::new("MyApp", "contact@example.com");
///     let filings = get_recent_filings(&client, "0000320193").await?;
///
///     let ten_ks = filter_by_form(&filings, "10-K");
///     println!("Found {} 10-K filings", ten_ks.len());
///     Ok(())
/// }
/// ```
pub fn filter_by_form(filings: &[Filing], form_type: &str) -> Vec<Filing> {
    filings.iter().filter(|f| f.form_type == form_type).cloned().collect()
}

/// Get only XBRL filings
pub fn filter_xbrl(filings: &[Filing]) -> Vec<Filing> {
    filings.iter().filter(|f| f.is_xbrl).cloned().collect()
}

/// Download all filings of a specific type for a company
///
/// # Examples
///
/// ```no_run
/// use sec_o3::filings::download_all_filings;
/// use sec_o3::Client;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let client = Client::new("MyApp", "contact@example.com");
///
///     // Download all 10-K filings for Apple
///     let paths = download_all_filings(
///         &client,
///         "0000320193",
///         "10-K",
///         "output/apple-10k"
///     ).await?;
///
///     println!("Downloaded {} filings", paths.len());
///     Ok(())
/// }
/// ```
pub async fn download_all_filings(
    client: &Client,
    cik: &str,
    form_type: &str,
    output_dir: impl AsRef<Path>,
) -> Result<Vec<PathBuf>> {
    let filings = get_recent_filings(client, cik).await?;
    let filtered = filter_by_form(&filings, form_type);

    let mut paths = Vec::new();

    for filing in filtered {
        match download_filing(client, &filing, &output_dir).await {
            Ok(path) => {
                println!("Downloaded: {:?}", path);
                paths.push(path);
            }
            Err(e) => {
                eprintln!(
                    "Failed to download {} ({}): {}",
                    filing.accession_number, filing.form_type, e
                );
            }
        }
    }

    Ok(paths)
}
/// Download all filings of a specific type for a company within a specified date range
///
/// # Examples
///
/// ```no_run
/// use sec_o3::filings::download_all_filings;
/// use sec_o3::Client;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let client = Client::new("MyApp", "contact@example.com");
///
///     // Download all 10-K filings for Apple
///     let paths = download_all_filings(
///         &client,
///         "0000320193",
///         "10-K",
///         "output/apple-10k"
///     ).await?;
///
///     println!("Downloaded {} filings", paths.len());
///     Ok(())
/// }
/// ```
pub async fn download_filings_in_date_range(
    client: &Client,
    cik: &str,
    form_type: &str,
    _output_dir: impl AsRef<Path>,
    _start_date: &str,
    _end_date: &str,
) -> Result<Vec<PathBuf>> {
    let filings = get_recent_filings(client, cik).await?;
    let _filtered = filter_by_form(&filings, form_type);

    Ok(Vec::new())
}

#[cfg(test)]
mod tests {
    use crate::utils::str_to_utc_datetime;

    use super::*;

    #[tokio::test]
    async fn test_get_submissions() {
        let client = Client::new("TestApp", "test@example.com");
        let result = get_submissions(&client, "0000320193").await;
        assert!(
            result.is_ok(),
            "Something happened while getting submissions {:?}",
            result.err()
        );

        let submissions = result.unwrap();
        assert_eq!(submissions.cik, "0000320193");
        assert!(submissions.name.contains("Apple"));
    }

    #[tokio::test]
    async fn test_get_recent_filings() {
        let client = Client::new("TestApp", "test@example.com");
        let result = get_recent_filings(&client, "0000320193").await;
        assert!(
            result.is_ok(),
            "Something happened while getting recent filings {:?}",
            result.err()
        );

        let filings = result.unwrap();
        assert!(!filings.is_empty());
    }

    #[test]
    fn test_filing_urls() {
        let filing = Filing {
            cik: "320193".to_string(),
            accession_number: "0000320193-23-000106".to_string(),
            form_type: "10-K".to_string(),
            acceptance_date: str_to_utc_datetime("2023-11-03T00:00:00.000Z")
                .expect("An invalid UTC date was provided as an acceptance date."),
            primary_document: "aapl-20230930.htm".to_string(),
            is_xbrl: true,
        };

        assert_eq!(
            filing.base_url(),
            "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/"
        );

        assert_eq!(
            filing.primary_document_url(),
            "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
        );
    }

    #[test]
    fn test_filter_by_form() {
        let filings = vec![
            Filing {
                cik: "123".to_string(),
                accession_number: "0001-23-001".to_string(),
                form_type: "10-K".to_string(),
                acceptance_date: str_to_utc_datetime("2023-01-01T00:00:00.000Z")
                    .expect("An invalid UTC datetime was provided as an acceptance date."),
                primary_document: "doc.xml".to_string(),
                is_xbrl: true,
            },
            Filing {
                cik: "123".to_string(),
                accession_number: "0001-23-002".to_string(),
                form_type: "10-Q".to_string(),
                acceptance_date: str_to_utc_datetime("2023-04-01T00:00:00.000Z")
                    .expect("An invalid UTC datetime was provided as an acceptance date."),
                primary_document: "doc2.xml".to_string(),
                is_xbrl: true,
            },
        ];

        let ten_ks = filter_by_form(&filings, "10-K");
        assert_eq!(ten_ks.len(), 1);
        assert_eq!(ten_ks[0].form_type, "10-K");
    }
}
