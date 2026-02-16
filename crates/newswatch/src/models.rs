use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[pyclass]
pub struct NewsItem {
    #[pyo3(get)]
    pub title: String,
    #[pyo3(get)]
    pub url: String,
    #[pyo3(get)]
    pub source: String,
    #[pyo3(get)]
    pub published_at: Option<String>,
    #[pyo3(get)]
    pub matched_keywords: Vec<String>,
    #[pyo3(get)]
    pub snippet: Option<String>,
}

#[pymethods]
impl NewsItem {
    #[new]
    #[pyo3(signature = (title, url, source, published_at=None, matched_keywords=None, snippet=None))]
    fn new(
        title: String,
        url: String,
        source: String,
        published_at: Option<String>,
        matched_keywords: Option<Vec<String>>,
        snippet: Option<String>,
    ) -> Self {
        Self {
            title,
            url,
            source,
            published_at,
            matched_keywords: matched_keywords.unwrap_or_default(),
            snippet,
        }
    }
}

impl NewsItem {
    pub fn with_source(mut self, source: impl Into<String>) -> Self {
        self.source = source.into();
        self
    }
}

#[derive(Debug, Clone)]
pub enum FeedType {
    Rss,
    JsonApi { api_key_env: Option<String> },
}

#[derive(Debug, Clone)]
pub struct FeedConfig {
    pub url: String,
    pub feed_type: FeedType,
    pub name: String,
}
