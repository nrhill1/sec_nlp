//! HTTP client for interacting with SEC EDGAR API

use std::{path::Path, sync::Arc, time::Duration};

use async_compression::tokio::bufread::{GzipDecoder, ZlibDecoder};
use hyper::{client::HttpConnector, Body, Method, Request, Response, StatusCode, Uri};
use hyper_tls::HttpsConnector;
use tokio::{
    fs,
    io::{AsyncReadExt, BufReader},
};

use super::{
    filings::{Filing, Submissions},
    rate_limit::RateLimiter,
    retry::RetryPolicy,
};
use crate::{Error, Result};

/// SEC API client with rate limiting, retry support, and async decompression.
///
/// Handles rate limiting and proper User-Agent headers as required by SEC.
/// The SEC requires a descriptive User-Agent header with contact information
/// and enforces a rate limit of 10 requests per second.
///
/// # Examples
///
/// ```no_run
/// use sec_o3::Client;
///
/// #[tokio::main]
/// async fn main() -> sec_o3::Result<()> {
///     let client = Client::new("MyApp/1.0", "contact@example.com");
///     let submissions = client.get_submissions("0000320193").await?;
///     let filings = submissions.recent_filings();
///     println!("Found {} filings for {}", filings.len(), submissions.name);
///     Ok(())
/// }
/// ```
#[derive(Clone)]
pub struct Client {
    inner: Arc<ClientInner>,
}

struct ClientInner {
    client: hyper::Client<HttpsConnector<HttpConnector>>,
    rate_limiter: RateLimiter,
    retry_policy: RetryPolicy,
    user_agent: String,
}

impl Client {
    /// Create a new SEC client with default settings
    ///
    /// # Arguments
    /// * `contact_name` - Name of your application
    /// * `contact_email` - Email address for contact
    ///
    /// # Examples
    ///
    /// ```
    /// use sec_o3::Client;
    ///
    /// let client = Client::new("MyApp/1.0", "contact@example.com");
    /// ```
    pub fn new(contact_name: &str, contact_email: &str) -> Self {
        let https = HttpsConnector::new();
        let client = hyper::Client::builder()
            .pool_idle_timeout(Duration::from_secs(30))
            .http2_keep_alive_interval(Some(Duration::from_secs(15)))
            .http2_keep_alive_timeout(Duration::from_secs(5))
            .build::<_, Body>(https);

        Self {
            inner: Arc::new(ClientInner {
                client,
                rate_limiter: RateLimiter::new(10, Duration::from_secs(1)),
                retry_policy: RetryPolicy::default(),
                user_agent: format!("{} {}", contact_name, contact_email),
            }),
        }
    }

    /// Create client from USER_AGENT environment variable
    pub fn from_env() -> Result<Self> {
        let user_agent = std::env::var("USER_AGENT").map_err(|_| Error::Custom("USER_AGENT not set".into()))?;

        if !user_agent.contains('@') {
            return Err(Error::Custom(
                "USER_AGENT must include email per SEC requirements".into(),
            ));
        }

        let https = HttpsConnector::new();
        let client = hyper::Client::builder()
            .pool_idle_timeout(Duration::from_secs(30))
            .http2_keep_alive_interval(Some(Duration::from_secs(15)))
            .http2_keep_alive_timeout(Duration::from_secs(5))
            .build::<_, Body>(https);

        Ok(Self {
            inner: Arc::new(ClientInner {
                client,
                rate_limiter: RateLimiter::new(10, Duration::from_secs(1)),
                retry_policy: RetryPolicy::default(),
                user_agent,
            }),
        })
    }

    /// Get company submissions metadata and filing history
    ///
    /// Returns comprehensive information about a company including
    /// identifying information and recent filings.
    ///
    /// # Arguments
    /// * `cik` - Company's CIK (Central Index Key), with or without leading zeros
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp/1.0", "contact@example.com");
    ///
    ///     let submissions = client.get_submissions("320193").await?;
    ///
    ///     println!("Company: {}", submissions.name);
    ///     println!("CIK: {}", submissions.cik);
    ///
    ///     let ten_ks = submissions.recent_filings_by_form("10-K");
    ///     println!("Found {} 10-K filings", ten_ks.len());
    ///
    ///     Ok(())
    /// }
    /// ```
    pub async fn get_submissions(&self, cik: &str) -> Result<Submissions> {
        let formatted_cik = format_cik(cik);
        let url = format!("https://data.sec.gov/submissions/CIK{}.json", formatted_cik);

        self.get_json(&url).await
    }

    /// Download the primary HTML document for a filing
    ///
    /// This is typically the main filing document in HTML format
    ///
    /// # Arguments
    /// * `filing` - The filing to download
    ///
    /// # Returns
    /// The HTML document content as a String
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp/1.0", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///     let ten_ks = submissions.recent_filings_by_form("10-K");
    ///
    ///     if let Some(filing) = ten_ks.first() {
    ///         let html = client.download_primary_html(filing).await?;
    ///         println!("Downloaded {} bytes of HTML", html.len());
    ///     }
    ///
    ///     Ok(())
    /// }
    /// ```
    pub async fn download_primary_html(&self, filing: &Filing) -> Result<String> {
        let url = filing.primary_document_url();
        self.get_text(&url).await
    }

    /// Download the full submission text file
    ///
    /// Contains the complete filing including all exhibits in a single text file
    ///
    /// # Arguments
    /// * `filing` - The filing to download
    ///
    /// # Returns
    /// The complete submission text as a String
    pub async fn download_submission_text(&self, filing: &Filing) -> Result<String> {
        let url = filing.submission_text_url();
        self.get_text(&url).await
    }

    /// Download XBRL instance document (XML format)
    ///
    /// For XBRL filings, this downloads the main instance document which contains
    /// the structured financial data. The filename typically ends with `_htm.xml` or `.xml`
    ///
    /// # Arguments
    /// * `filing` - The filing to download XBRL from
    ///
    /// # Returns
    /// The XBRL XML content as a String, or None if filing doesn't have XBRL
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp/1.0", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///
    ///     for filing in submissions.recent_filings() {
    ///         if filing.is_xbrl {
    ///             if let Some(xbrl) = client.download_xbrl_instance(&filing).await? {
    ///                 println!("Downloaded XBRL for {}: {} bytes",
    ///                     filing.accession_number, xbrl.len());
    ///             }
    ///         }
    ///     }
    ///
    ///     Ok(())
    /// }
    /// ```
    pub async fn download_xbrl_instance(&self, filing: &Filing) -> Result<Option<String>> {
        if !filing.is_xbrl {
            return Ok(None);
        }

        let base_url = filing.base_url();
        let acc_no = filing.accession_number.replace("-", "");

        // Try different common XBRL filename patterns
        let patterns = vec![
            format!("{}{}_htm.xml", base_url, acc_no), // Inline XBRL
            format!("{}{}.xml", base_url, acc_no),     // Traditional XBRL
            filing.primary_document_url(),             // Primary document might be XBRL
        ];

        for url in patterns {
            match self.get_text(&url).await {
                Ok(content) => {
                    if content.contains("http://www.xbrl.org")
                        || content.contains("xbrli:")
                        || content.contains("<xbrl")
                    {
                        return Ok(Some(content));
                    }
                },
                Err(_) => continue,
            }
        }

        Ok(None)
    }

    /// Download all XBRL-related files for a filing
    ///
    /// Returns a vector of (filename, content) tuples for all XBRL files including:
    /// - Instance document (the main data file)
    /// - Schema files (.xsd)
    /// - Linkbase files (.xml - calculation, presentation, definition, label)
    ///
    /// # Arguments
    /// * `filing` - The filing to download XBRL files from
    ///
    /// # Returns
    /// Vector of (filename, content) tuples, or None if filing doesn't have XBRL
    pub async fn download_xbrl_package(&self, filing: &Filing) -> Result<Option<Vec<(String, String)>>> {
        if !filing.is_xbrl {
            return Ok(None);
        }

        let base_url = filing.base_url();
        let acc_no = filing.accession_number.replace("-", "");

        let mut files = Vec::new();

        // Try to download the FilingSummary.xml which lists all XBRL files
        let filing_summary_url = format!("{}FilingSummary.xml", base_url);

        if let Ok(summary) = self.get_text(&filing_summary_url).await {
            files.push(("FilingSummary.xml".to_string(), summary.clone()));

            // Parse FilingSummary to find all XBRL files
            for line in summary.lines() {
                if line.contains("<HtmlFileName>")
                    || line.contains("<XmlFileName>")
                    || line.contains("<OriginalDocument>")
                {
                    if let Some(filename) = extract_filename_from_xml_tag(line) {
                        if filename.ends_with(".xml") || filename.ends_with(".xsd") {
                            let file_url = format!("{}{}", base_url, filename);
                            if let Ok(content) = self.get_text(&file_url).await {
                                files.push((filename, content));
                            }
                        }
                    }
                }
            }
        }

        if files.is_empty() {
            // Fallback: try common XBRL file patterns
            let common_suffixes = vec!["_htm.xml", ".xsd", "_cal.xml", "_def.xml", "_lab.xml", "_pre.xml"];

            for suffix in common_suffixes {
                let url = format!("{}{}{}", base_url, acc_no, suffix);
                if let Ok(content) = self.get_text(&url).await {
                    let filename = format!("{}{}", acc_no, suffix);
                    files.push((filename, content));
                }
            }
        }

        if files.is_empty() {
            Ok(None)
        } else {
            Ok(Some(files))
        }
    }

    /// Download a filing to a local file
    ///
    /// # Arguments
    /// * `filing` - The filing to download
    /// * `path` - Path where the file should be saved
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use sec_o3::Client;
    ///
    /// #[tokio::main]
    /// async fn main() -> sec_o3::Result<()> {
    ///     let client = Client::new("MyApp/1.0", "contact@example.com");
    ///     let submissions = client.get_submissions("0000320193").await?;
    ///     let filings = submissions.recent_filings_by_form("10-K");
    ///
    ///     if let Some(filing) = filings.first() {
    ///         client.download_filing_to_file(filing, "output/filing.html").await?;
    ///     }
    ///
    ///     Ok(())
    /// }
    /// ```
    pub async fn download_filing_to_file(&self, filing: &Filing, path: impl AsRef<Path>) -> Result<()> {
        let url = filing.primary_document_url();
        self.download_text(&url, path).await
    }

    /// Download XBRL instance to a local file
    pub async fn download_xbrl_to_file(&self, filing: &Filing, path: impl AsRef<Path>) -> Result<bool> {
        if let Some(xbrl) = self.download_xbrl_instance(filing).await? {
            fs::write(path, xbrl).await.map_err(Error::IoError)?;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// Make a GET request with automatic retries and rate limiting
    async fn get(&self, url: &str) -> Result<Response<Body>> {
        let uri: Uri = url
            .parse()
            .map_err(|_| Error::Custom(format!("Invalid URL: {}", url)))?;
        self.request(Method::GET, uri).await
    }

    /// Get response body as decompressed bytes
    async fn get_bytes(&self, url: &str) -> Result<bytes::Bytes> {
        let response = self.get(url).await?;
        self.decode_response(response).await
    }

    /// Get response body as UTF-8 string with automatic decompression
    async fn get_text(&self, url: &str) -> Result<String> {
        let bytes = self.get_bytes(url).await?;
        String::from_utf8(bytes.to_vec()).map_err(|e| Error::Custom(format!("Invalid UTF-8: {}", e)))
    }

    /// Fetch and deserialize JSON with automatic decompression
    async fn get_json<T>(&self, url: &str) -> Result<T>
    where
        T: serde::de::DeserializeOwned,
    {
        let bytes = self.get_bytes(url).await?;
        serde_json::from_slice(&bytes).map_err(Error::JsonError)
    }

    /// Download text file with UTF-8 validation and automatic decompression
    async fn download_text(&self, url: &str, path: impl AsRef<Path>) -> Result<()> {
        let bytes = self.get_bytes(url).await?;
        let text = std::str::from_utf8(&bytes).map_err(|e| Error::Custom(format!("Invalid UTF-8: {}", e)))?;
        fs::write(path, text).await.map_err(Error::IoError)?;
        Ok(())
    }

    /// Asynchronously decodes response body based on Content-Encoding header
    async fn decode_response(&self, response: Response<Body>) -> Result<bytes::Bytes> {
        let encoding = response
            .headers()
            .get(hyper::header::CONTENT_ENCODING)
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_lowercase());

        let body = hyper::body::to_bytes(response.into_body())
            .await
            .map_err(Error::HyperError)?;

        match encoding.as_deref() {
            Some("gzip") => {
                let mut decoder = GzipDecoder::new(BufReader::new(&body[..]));
                let mut decoded = Vec::new();
                decoder
                    .read_to_end(&mut decoded)
                    .await
                    .map_err(|e| Error::Custom(format!("Gzip decompression failed: {}", e)))?;
                Ok(bytes::Bytes::from(decoded))
            },
            Some("deflate") => {
                let mut decoder = ZlibDecoder::new(BufReader::new(&body[..]));
                let mut decoded = Vec::new();
                decoder
                    .read_to_end(&mut decoded)
                    .await
                    .map_err(|e| Error::Custom(format!("Deflate decompression failed: {}", e)))?;
                Ok(bytes::Bytes::from(decoded))
            },
            Some("identity") | None => Ok(body),
            Some(other) => Err(Error::Custom(format!("Unsupported encoding: {}", other))),
        }
    }

    /// Internal request method with retry logic
    async fn request(&self, method: Method, uri: Uri) -> Result<Response<Body>> {
        self.inner.rate_limiter.wait().await;

        let inner = Arc::clone(&self.inner);

        self.inner
            .retry_policy
            .execute(|| {
                let uri = uri.clone();
                let method = method.clone();
                let inner = Arc::clone(&inner);

                Box::pin(async move {
                    let req = Request::builder()
                        .method(method)
                        .uri(&uri)
                        .header("User-Agent", &inner.user_agent)
                        .header("Accept", "application/json")
                        .header("Accept-Encoding", "gzip, deflate")
                        .header("Host", uri.host().unwrap_or("data.sec.gov"))
                        .body(Body::empty())
                        .map_err(Error::HttpError)?;

                    let response = inner.client.request(req).await.map_err(Error::HyperError)?;

                    match response.status() {
                        StatusCode::OK => Ok(response),
                        StatusCode::TOO_MANY_REQUESTS => {
                            Err(Error::RateLimitExceeded("SEC rate limit exceeded".into()))
                        },
                        StatusCode::NOT_FOUND => Err(Error::NotFound(format!("Not found: {}", uri))),
                        status => Err(Error::InvalidStatus(status)),
                    }
                })
            })
            .await
    }
}

/// Format CIK with leading zeros to 10 digits as required by SEC
///
/// # Examples
///
/// ```
/// use sec_o3::client::format_cik;
///
/// assert_eq!(format_cik("320193"), "0000320193");
/// assert_eq!(format_cik("0000320193"), "0000320193");
/// ```
pub fn format_cik(cik: &str) -> String {
    format!("{:0>10}", cik)
}

/// Extract filename from XML tag
///
/// Helper function to parse filenames from FilingSummary.xml
fn extract_filename_from_xml_tag(line: &str) -> Option<String> {
    let line = line.trim();

    // Handle tags like <HtmlFileName>file.htm</HtmlFileName>
    if let Some(start) = line.find('>') {
        if let Some(end) = line.rfind('<') {
            if start < end {
                return Some(line[start + 1..end].to_string());
            }
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_cik() {
        assert_eq!(format_cik("320193"), "0000320193");
        assert_eq!(format_cik("0000320193"), "0000320193");
        assert_eq!(format_cik("1"), "0000000001");
    }

    #[test]
    fn test_extract_filename() {
        assert_eq!(
            extract_filename_from_xml_tag("<HtmlFileName>test.htm</HtmlFileName>"),
            Some("test.htm".to_string())
        );
        assert_eq!(
            extract_filename_from_xml_tag("  <XmlFileName>data.xml</XmlFileName>  "),
            Some("data.xml".to_string())
        );
    }

    #[test]
    fn test_client_creation() {
        let client = Client::new("TestApp/1.0", "test@example.com");
        assert!(client.inner.user_agent.contains("TestApp/1.0"));
        assert!(client.inner.user_agent.contains("test@example.com"));
    }
}
