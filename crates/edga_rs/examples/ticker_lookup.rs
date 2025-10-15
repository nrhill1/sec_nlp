//! Example: Look up ticker to CIK mapping
use edga_rs::get_ticker_cik_map;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("Fetching ticker-to-CIK map...");
    let map = get_ticker_cik_map().await?;

    println!("Total tickers: {}", map.len());

    // Look up some common tickers
    let tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"];

    println!("\nTicker lookups:");
    for ticker in &tickers {
        if let Some(cik) = map.get(*ticker) {
            println!("  {}: {}", ticker, cik);
        } else {
            println!("  {}: Not found", ticker);
        }
    }

    Ok(())
}
