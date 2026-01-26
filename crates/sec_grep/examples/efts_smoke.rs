use std::env;

use serde_json::Value;

fn main() {
    let user_agent = match env::var("SEC_GREP_USER_AGENT") {
        Ok(value) if !value.trim().is_empty() => value,
        _ => {
            eprintln!("SEC_GREP_USER_AGENT must be set and include a contact email.");
            std::process::exit(2);
        }
    };
    let query = env::var("SEC_GREP_QUERY").unwrap_or_else(|_| "warranty accrual".to_string());
    let limit = env::var("SEC_GREP_LIMIT")
        .ok()
        .and_then(|value| value.parse::<u32>().ok())
        .unwrap_or(5);

    let response = match sec_grep::search_raw(&query, &user_agent, limit) {
        Ok(value) => value,
        Err(err) => {
            eprintln!("EFTS request failed: {}", err);
            std::process::exit(1);
        }
    };

    let hits = response
        .get("hits")
        .and_then(Value::as_array)
        .map(|items| items.len())
        .unwrap_or(0);
    if hits == 0 {
        eprintln!("EFTS returned no hits for query '{}'.", query);
        std::process::exit(1);
    }

    let total = response.get("total").and_then(Value::as_u64).unwrap_or(0);
    println!("EFTS smoke check OK: {} hits ({} total)", hits, total);

    if let Some(first) = response
        .get("hits")
        .and_then(Value::as_array)
        .and_then(|items| items.first())
    {
        let accession = first
            .get("accession_number")
            .and_then(Value::as_str)
            .unwrap_or("");
        let cik = first.get("cik").and_then(Value::as_str).unwrap_or("");
        if !accession.is_empty() && !cik.is_empty() {
            let clean_accession = accession.replace('-', "");
            let cik_trimmed = cik.trim_start_matches('0');
            if !cik_trimmed.is_empty() {
                let url = format!(
                    "https://www.sec.gov/Archives/edgar/data/{}/{}/",
                    cik_trimmed, clean_accession
                );
                println!("Example filing: {}", url);
            }
        }
    }
}
