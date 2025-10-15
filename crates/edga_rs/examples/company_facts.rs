//! Example: Fetch company XBRL facts
use edga_rs::{fetch_company_facts, normalize_cik};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cik = normalize_cik("320193"); // Apple

    println!("Fetching XBRL facts for CIK {}...", cik);
    let facts = fetch_company_facts(&cik).await?;

    println!("Company: {}", facts.entity_name);
    println!("\nAvailable taxonomies:");

    for (taxonomy, concepts) in &facts.facts {
        println!("  {}: {} concepts", taxonomy, concepts.concepts.len());
    }

    // Look for revenue data
    if let Some(us_gaap) = facts.facts.get("us-gaap") {
        if let Some(revenues) = us_gaap.concepts.get("Revenues") {
            println!("\nRevenue data:");
            println!("  Label: {}", revenues.label);

            if let Some(usd_data) = revenues.units.get("USD") {
                println!("  Total USD entries: {}", usd_data.len());

                // Show last 3 entries
                for fact in usd_data.iter().rev().take(3) {
                    println!("    {} (FY {}): ${}", fact.form, fact.fy, fact.val);
                }
            }
        }
    }

    Ok(())
}
