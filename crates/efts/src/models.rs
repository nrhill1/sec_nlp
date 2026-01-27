use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct SearchHit {
    pub accession_number: String,
    pub cik: String,
    pub company_name: String,
    pub tickers: Vec<String>,
    pub form_type: String,
    pub filed_date: String,
    pub file_number: Option<String>,
    pub film_number: Option<String>,
    pub snippet: String,
    pub score: f64,
    pub filing_url: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct SearchResponse {
    pub query: String,
    pub total: u64,
    pub hits: Vec<SearchHit>,
    pub start: u32,
    pub limit: u32,
}

impl SearchResponse {
    pub fn has_more(&self) -> bool {
        (self.start as u64) + (self.hits.len() as u64) < self.total
    }

    pub fn next_offset(&self) -> u32 {
        self.start + (self.hits.len() as u32)
    }
}
