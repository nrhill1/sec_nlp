//! Integration tests for HTTP client
use edga_rs::SecClient;

#[tokio::test]
async fn test_fetch_ticker_file() {
    let client = SecClient::new();
    let result = client
        .fetch_text("https://www.sec.gov/include/ticker.txt")
        .await;

    assert!(result.is_ok());
    let text = result.unwrap();
    assert!(text.contains("aapl"));
}

#[tokio::test]
async fn test_rate_limiting() {
    let client = SecClient::new();

    // Should not panic with rate limiting enabled
    for _ in 0..5 {
        let _ = client
            .fetch_text("https://www.sec.gov/include/ticker.txt")
            .await;
    }
}

#[tokio::test]
async fn test_invalid_url_rejected() {
    let client = SecClient::new();
    let result = client.fetch_text("https://example.com/test").await;

    assert!(result.is_err());
}
