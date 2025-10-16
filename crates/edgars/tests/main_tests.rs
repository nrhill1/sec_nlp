// tests/integration_tests.rs - Comprehensive integration tests
use edgars::{
    corp::{fetch_company_facts, fetch_company_filings, normalize_cik},
    parse::{parse_auto, parse_html, parse_json},
    utils::{build_document_url, build_filing_url, build_full_text_url},
    SecClient,
};

// ============================================================================
// Client Tests
// ============================================================================

#[tokio::test]
async fn test_client_fetch_ticker_file() {
    let client = SecClient::new();
    let result = client
        .fetch_text("https://www.sec.gov/files/company_tickers.json")
        .await;

    assert!(result.is_ok(), "Failed to fetch ticker file");
    let text = result.unwrap();
    assert!(text.len() > 1000, "Ticker file too small");
    assert!(text.contains("ticker"), "Missing expected content");
}

#[tokio::test]
async fn test_client_rate_limiting() {
    let client = SecClient::new();
    let url = "https://www.sec.gov/files/company_tickers.json";

    // Make multiple requests - should not panic
    for i in 0..5 {
        let result = client.fetch_text(url).await;
        assert!(result.is_ok(), "Request {} failed", i + 1);
    }
}

#[tokio::test]
async fn test_client_timeout() {
    let client = SecClient::new().with_timeout(std::time::Duration::from_millis(1)); // Very short timeout

    let result = client
        .fetch_text("https://www.sec.gov/files/company_tickers.json")
        .await;

    // Should timeout
    assert!(result.is_err());
}

#[tokio::test]
async fn test_client_invalid_domain() {
    let client = SecClient::new();
    let result = client.fetch_text("https://example.com/test").await;

    assert!(result.is_err(), "Should reject non-SEC URLs");
}

#[tokio::test]
async fn test_client_http_rejected() {
    let client = SecClient::new();
    let result = client.fetch_text("http://www.sec.gov/test").await;

    assert!(result.is_err(), "Should reject HTTP (non-HTTPS) URLs");
}

#[tokio::test]
async fn test_client_json_parsing() {
    let client = SecClient::new();

    #[derive(serde::Deserialize, Debug)]
    #[allow(dead_code)]
    struct TickerEntry {
        ticker: String,
        cik_str: i64,
    }

    let result: Result<std::collections::HashMap<String, TickerEntry>, _> = client
        .fetch_json("https://www.sec.gov/files/company_tickers.json")
        .await;

    assert!(result.is_ok(), "Failed to parse JSON");
    let data = result.unwrap();
    assert!(data.len() > 5000, "Expected thousands of tickers");
}

#[tokio::test]
async fn test_client_404_handling() {
    let client = SecClient::new();
    let result = client
        .fetch_text("https://www.sec.gov/this-does-not-exist-12345.json")
        .await;

    assert!(result.is_err());
}

// ============================================================================
// CIK/Ticker Tests
// ============================================================================

#[test]
fn test_normalize_cik_various_formats() {
    assert_eq!(normalize_cik("320193"), "0000320193");
    assert_eq!(normalize_cik("0000320193"), "0000320193");
    assert_eq!(normalize_cik("1"), "0000000001");
    assert_eq!(normalize_cik("1234567890"), "1234567890");
    assert_eq!(normalize_cik("CIK0000320193"), "0000320193");
    assert_eq!(normalize_cik("0000-320193"), "0000320193");
}

// ============================================================================
// Company Data Tests
// ============================================================================

#[tokio::test]
async fn test_fetch_company_facts_apple() {
    let result = fetch_company_facts("320193").await;

    assert!(result.is_ok(), "Failed to fetch Apple facts");
    let facts = result.unwrap();

    assert_eq!(facts.cik, 320193);
    assert!(facts.entity_name.to_lowercase().contains("apple"));
    assert!(!facts.facts.is_empty(), "No facts found");

    // Should have US-GAAP taxonomy
    assert!(facts.facts.contains_key("us-gaap"), "Missing us-gaap taxonomy");
}

#[tokio::test]
async fn test_fetch_company_filings_apple() {
    let result = fetch_company_filings("320193").await;

    assert!(result.is_ok(), "Failed to fetch Apple filings");
    let subs = result.unwrap();

    assert_eq!(subs.cik, "0000320193");
    assert!(subs.name.to_lowercase().contains("apple"));
    assert!(!subs.filings.recent.form.is_empty(), "No recent filings");

    // Apple should have filed 10-Ks
    let has_10k = subs.filings.recent.form.iter().any(|f| f == "10-K");
    assert!(has_10k, "No 10-K filings found");
}

#[tokio::test]
async fn test_fetch_company_invalid_cik() {
    let result = fetch_company_facts("9999999999").await;

    // Should return an error (likely 404)
    assert!(result.is_err());
}

// ============================================================================
// Parser Tests
// ============================================================================

#[test]
fn test_parse_html_10k() {
    let html = r#"
<!DOCTYPE html>
<html>
<head><title>Apple Inc. 10-K</title></head>
<body>
<div>FORM 10-K</div>
<p>Annual Report</p>
</body>
</html>
    "#;

    let doc = parse_html(html).unwrap();

    assert_eq!(doc.form_type.to_string(), "10-K");
    assert_eq!(doc.title, Some("Apple Inc. 10-K".to_string()));
    assert_eq!(doc.format.to_string(), "HTML");
    assert!(doc.size_bytes > 0);
}

#[test]
fn test_parse_html_8k() {
    let html = r#"
<html>
<head><title>Current Report</title></head>
<body>FORM 8-K</body>
</html>
    "#;

    let doc = parse_html(html).unwrap();
    assert_eq!(doc.form_type.to_string(), "8-K");
}

#[test]
fn test_parse_json_submission() {
    let json = r#"{
        "submissionType": "10-Q",
        "entityName": "Test Company Inc.",
        "cik": "0001234567"
    }"#;

    let doc = parse_json(json).unwrap();

    assert_eq!(doc.form_type.to_string(), "10-Q");
    assert_eq!(doc.format.to_string(), "JSON");
    assert!(doc.title.is_some());
}

#[test]
fn test_parse_auto_detection_json() {
    let json = r#"{"submissionType": "8-K"}"#;

    let doc = parse_auto(json).unwrap();
    assert_eq!(doc.format.to_string(), "JSON");
    assert_eq!(doc.form_type.to_string(), "8-K");
}

#[test]
fn test_parse_auto_detection_html() {
    let html = r#"<!DOCTYPE html><html><body>FORM 10-K</body></html>"#;

    let doc = parse_auto(html).unwrap();
    assert_eq!(doc.format.to_string(), "HTML");
    assert_eq!(doc.form_type.to_string(), "10-K");
}

#[test]
fn test_parse_auto_detection_text() {
    let text = "CONFORMED SUBMISSION TYPE: 10-Q\nPUBLIC DOCUMENT COUNT: 50";

    let doc = parse_auto(text).unwrap();
    assert_eq!(doc.format.to_string(), "Text");
    assert_eq!(doc.form_type.to_string(), "10-Q");
}

#[test]
fn test_parse_invalid_html() {
    let html = "<html><body>No form type here</body></html>";

    let result = parse_html(html);
    assert!(result.is_err(), "Should fail when no form type found");
}

#[test]
fn test_parse_invalid_json() {
    let json = r#"{"invalid": json"#;

    let result = parse_json(json);
    assert!(result.is_err(), "Should fail on malformed JSON");
}

// ============================================================================
// URL Builder Tests
// ============================================================================

#[test]
fn test_build_filing_url() {
    let url = build_filing_url("320193", "0000320193-23-000077");

    assert_eq!(
        url,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077-index.html"
    );
}

#[test]
fn test_build_document_url() {
    let url = build_document_url("320193", "0000320193-23-000077", "aapl-20230930.htm");

    assert_eq!(
        url,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077/aapl-20230930.htm"
    );
}

#[test]
fn test_build_full_text_url() {
    let url = build_full_text_url("320193", "0000320193-23-000077");

    assert_eq!(
        url,
        "https://www.sec.gov/Archives/edgar/data/320193/0000320193-23-000077.txt"
    );
}

#[test]
fn test_url_builders_normalize_cik() {
    // Should work with non-padded CIK
    let url1 = build_filing_url("320193", "0000320193-23-000077");
    let url2 = build_filing_url("0000320193", "0000320193-23-000077");

    assert_eq!(url1, url2);
}

// ============================================================================
// Performance Tests
// ============================================================================

#[tokio::test]
async fn test_concurrent_requests() {
    let client = SecClient::new();

    let handles: Vec<_> = (0..10)
        .map(|_| {
            let client = client.clone();
            tokio::spawn(async move {
                client
                    .fetch_text("https://www.sec.gov/files/company_tickers.json")
                    .await
            })
        })
        .collect();

    for handle in handles {
        let result = handle.await.unwrap();
        assert!(result.is_ok(), "Concurrent request failed");
    }
}

#[test]
fn test_normalize_cik_performance() {
    use std::time::Instant;

    let start = Instant::now();
    for i in 0..10_000 {
        let _ = normalize_cik(&i.to_string());
    }
    let elapsed = start.elapsed();

    assert!(elapsed.as_millis() < 100, "CIK normalization too slow: {:?}", elapsed);
}

// ============================================================================
// Error Handling Tests
// ============================================================================

#[tokio::test]
async fn test_error_types() {
    let client = SecClient::new();

    // Network error (invalid domain)
    let err1 = client.fetch_text("https://example.com/test").await.unwrap_err();
    assert!(err1.to_string().contains("sec.gov"));

    // Not found
    let err2 = client
        .fetch_text("https://www.sec.gov/nonexistent-12345.json")
        .await
        .unwrap_err();
    assert!(err2.to_string().contains("404") || err2.to_string().contains("Not Found"));
}

#[test]
fn test_error_is_retryable() {
    use edgars::errors::EdgarError;

    assert!(EdgarError::Network("test".into()).is_retryable());
    assert!(EdgarError::Timeout(30).is_retryable());
    assert!(EdgarError::http_status(503).is_retryable());
    assert!(!EdgarError::http_status(404).is_retryable());
    assert!(!EdgarError::Validation("test".into()).is_retryable());
}

// ============================================================================
// Edge Cases and Stress Tests
// ============================================================================

#[test]
fn test_empty_input_parsing() {
    let result = parse_auto("");
    assert!(result.is_err(), "Should fail on empty input");
}

#[test]
fn test_very_large_input() {
    let large_html = format!("<html><body>FORM 10-K\n{}</body></html>", "x".repeat(1_000_000));

    let doc = parse_html(&large_html).unwrap();
    assert_eq!(doc.form_type.to_string(), "10-K");
    assert!(doc.size_bytes > 1_000_000);
}

#[test]
fn test_unicode_in_documents() {
    let html = r#"
<html>
<head><title>Test 测试 Company</title></head>
<body>FORM 10-K with unicode: café, naïve, 日本語</body>
</html>
    "#;

    let doc = parse_html(html).unwrap();
    assert_eq!(doc.form_type.to_string(), "10-K");
    assert!(doc.title.unwrap().contains("测试"));
}

#[test]
fn test_special_characters_in_cik() {
    assert_eq!(normalize_cik("CIK-0000320193"), "0000320193");
    assert_eq!(normalize_cik("320,193"), "320193");
    assert_eq!(normalize_cik("320.193"), "320193");
}

#[tokio::test]
async fn test_rate_limiter_accuracy() {
    use edgars::client::RateLimiter;
    use std::time::Instant;

    let limiter = RateLimiter::with_rate(10); // 10 req/s

    let start = Instant::now();
    for _ in 0..20 {
        limiter.wait().await;
    }
    let elapsed = start.elapsed();

    // Should take approximately 2 seconds (20 requests / 10 per second)
    assert!(elapsed.as_secs() >= 1, "Rate limiter too fast");
    assert!(elapsed.as_secs() <= 3, "Rate limiter too slow");
}

// ============================================================================
// Real-world Scenario Tests
// ============================================================================

#[tokio::test]
#[ignore] // Ignore by default due to network dependency
async fn test_full_workflow_parse_filing() {
    let client = SecClient::new();

    // Fetch a known filing
    let cik = "0000320193"; // Apple
    let filings = fetch_company_filings(cik).await.unwrap();

    // Get first filing
    if let Some(accession) = filings.filings.recent.accession_number.first() {
        let url = build_full_text_url(cik, accession);

        // Fetch and parse
        let content = client.fetch_text(&url).await.unwrap();
        let doc = parse_auto(&content).unwrap();

        assert!(doc.size_bytes > 0);
        println!("Parsed {} filing: {:?}", doc.form_type, doc.title);
    }
}

// ============================================================================
// Regression Tests
// ============================================================================

#[test]
fn test_form_type_parsing_regression() {
    // Test various form type formats that have caused issues
    let test_cases = vec![
        ("10-K", "10-K"),
        ("10-Q", "10-Q"),
        ("8-K", "8-K"),
        ("SC 13D", "SC 13D"),
        ("SC 13G", "SC 13G"),
        ("DEF 14A", "DEF 14A"),
    ];

    for (input, expected) in test_cases {
        let html = format!("<html><body>FORM {}</body></html>", input);
        let doc = parse_html(&html).unwrap();
        assert_eq!(doc.form_type.to_string(), expected);
    }
}

#[test]
fn test_accession_number_formats() {
    // Test various accession number formats
    let test_cases = vec![
        ("0000320193-23-000077", "000032019323000077"),
        ("0000320193-23-000077", "000032019323000077"),
    ];

    for (accession, expected_stripped) in test_cases {
        let url = build_filing_url("320193", accession);
        assert!(url.contains(expected_stripped));
    }
}

// ============================================================================
// Documentation Tests
// ============================================================================

#[test]
fn test_readme_examples() {
    // Ensure examples in README work
    let cik = normalize_cik("320193");
    assert_eq!(cik, "0000320193");
}

#[tokio::test]
async fn test_basic_usage_example() {
    // Basic usage that should work
    let client = SecClient::new();
    let result = client
        .fetch_text("https://www.sec.gov/files/company_tickers.json")
        .await;
    assert!(result.is_ok());
}

// ============================================================================
// Security Tests
// ============================================================================

#[test]
fn test_no_sql_injection() {
    // Ensure CIK normalization removes non-numeric chars
    let malicious = "320193; DROP TABLE companies;--";
    let normalized = normalize_cik(malicious);
    assert_eq!(normalized, "0000320193");
    assert!(!normalized.contains(";"));
    assert!(!normalized.contains("DROP"));
}

#[tokio::test]
async fn test_url_validation_prevents_ssrf() {
    let client = SecClient::new();

    // Should reject internal network addresses
    let internal_urls = vec![
        "https://localhost/test",
        "https://127.0.0.1/test",
        "https://10.0.0.1/test",
        "https://192.168.1.1/test",
    ];

    for url in internal_urls {
        let result = client.fetch_text(url).await;
        assert!(result.is_err(), "Should reject internal URL: {}", url);
    }
}

// ============================================================================
// Module Organization Tests
// ============================================================================

#[test]
fn test_public_api_available() {
    // Ensure main exports are accessible
    let _ = SecClient::new();
    let _ = normalize_cik("123");

    use edgars::{corp::normalize_cik, SecClient};

    let _client: SecClient = SecClient::new();
    let _cik: String = normalize_cik("123");
}
