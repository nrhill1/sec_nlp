//! Example: Fetch a 10-K filing
use edga_rs::{fetch_company_filings, normalize_cik, utils, SecClient};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize client
    let client = SecClient::new().user_agent("my-app/1.0 (contact@example.com)");

    // Get Apple's CIK
    let cik = normalize_cik("320193");

    // Fetch company submissions
    println!("Fetching submissions for CIK {}...", cik);
    let submissions = fetch_company_filings(&cik).await?;

    println!("Company: {}", submissions.name);
    println!("Total recent filings: {}", submissions.filings.recent.form.len());

    // Find the latest 10-K
    for (idx, form) in submissions.filings.recent.form.iter().enumerate() {
        if form == "10-K" {
            let accession = &submissions.filings.recent.accession_number[idx];
            let date = &submissions.filings.recent.filing_date[idx];

            println!("\nFound 10-K:");
            println!("  Date: {}", date);
            println!("  Accession: {}", accession);

            // Build URL
            let url = utils::build_full_text_url(&cik, accession);
            println!("  URL: {}", url);

            break;
        }
    }

    Ok(())
}
