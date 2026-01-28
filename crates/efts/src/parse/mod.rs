mod cik;
mod company;
mod hit;
mod response;
mod ticker;
mod util;

pub(crate) use response::parse_response;

#[cfg(test)]
mod tests {
    use super::hit::parse_hit;
    use super::response::parse_response;
    use super::ticker::{extract_tickers_from_company, normalize_ticker};
    use serde_json::json;

    #[test]
    fn parse_response_matches_sample() {
        let sample = json!({
            "query": {"from": 0, "size": 10, "q": "warranty accrual"},
            "hits": {
                "total": {"value": 42},
                "hits": [
                    {
                        "_score": 15.5,
                        "_source": {
                            "adsh": "0001234567-24-000001",
                            "cik": "1234567",
                            "display_names": ["Apple Inc."],
                            "form": "10-K",
                            "file_date": "2024-01-15"
                        },
                        "highlight": {"text": ["warranty <em>accrual</em> provisions"]}
                    },
                    {
                        "_score": 12.3,
                        "_source": {
                            "adsh": "0009876543-24-000002",
                            "cik": "9876543",
                            "display_names": ["Microsoft Corporation"],
                            "form": "10-Q",
                            "file_date": "2024-02-20"
                        },
                        "highlight": {"text": ["product <em>warranty</em> reserves"]}
                    }
                ]
            }
        });

        let response = parse_response(&sample, "warranty accrual");

        assert_eq!(response.total, 42);
        assert_eq!(response.hits_vec.len(), 2);
        assert_eq!(response.hits_vec[0].company_name, "Apple Inc.");
        assert_eq!(response.hits_vec[0].form_type, "10-K");
        assert_eq!(response.hits_vec[0].score, 15.5);
    }

    #[test]
    fn parse_response_empty_hits() {
        let sample = json!({
            "query": {"from": 0, "size": 10, "q": "nope"},
            "hits": {"total": {"value": 0}, "hits": []}
        });

        let response = parse_response(&sample, "nope");

        assert_eq!(response.total, 0);
        assert!(response.hits_vec.is_empty());
    }

    #[test]
    fn parse_hit_normalizes_accession_and_ticker() {
        let raw = json!({
            "_score": 15.5,
            "_source": {
                "adsh": "000123456724000001",
                "cik": "1234567",
                "display_names": ["Apple Inc. (AAPL)"],
                "form": "10-K",
                "file_date": "2024-01-15"
            },
            "highlight": {"text": ["warranty <em>accrual</em>"]}
        });

        let hit = parse_hit(&raw);

        assert_eq!(hit.accession_number, "0001234567-24-000001");
        assert_eq!(hit.tickers, vec!["AAPL"]);
        assert!(hit.snippet.contains("warranty"));
    }

    #[test]
    fn parse_hit_prefers_issuer_for_insider_forms() {
        let raw = json!({
            "_score": 12.1,
            "_source": {
                "adsh": "0001801368-24-000123",
                "cik": "0002006182",
                "company": "MP Materials Corp",
                "display_names": [
                    "Dhillon Mannik S. (CIK 0002006182)",
                    "MP Materials Corp (MP)"
                ],
                "form": "4",
                "file_date": "2024-01-15"
            }
        });

        let hit = parse_hit(&raw);

        assert_eq!(hit.company_name, "MP Materials Corp");
    }

    #[test]
    fn extract_tickers_from_company_filters_cik() {
        let tickers = extract_tickers_from_company(
            "Example Corp (CIK 0001234567) (EXM, EXM.A)",
        );

        assert_eq!(tickers, vec!["EXM", "EXM.A"]);
    }

    #[test]
    fn normalize_ticker_rejects_non_alpha() {
        assert_eq!(normalize_ticker("1234"), None);
        assert_eq!(normalize_ticker("NYSE:V"), Some("V".to_string()));
        assert_eq!(normalize_ticker(" (AAPL) "), Some("AAPL".to_string()));
    }
}
