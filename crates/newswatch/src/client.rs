use std::env;
use std::sync::OnceLock;

use futures::stream::{self, StreamExt};
use tokio::runtime::Runtime;

use crate::error::NewswatchError;
use crate::feeds::{json_api, rss};
use crate::filter::apply_keyword_filter;
use crate::http::HttpClient;
use crate::models::{FeedConfig, FeedType, NewsItem};

const DEFAULT_MAX_RETRIES: u32 = 2;
const DEFAULT_RETRY_DELAY_SECS: f64 = 0.5;
const MAX_FEED_CONCURRENCY: usize = 4;
static RUNTIME: OnceLock<Runtime> = OnceLock::new();

fn get_runtime() -> &'static Runtime {
    RUNTIME.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()
            .expect("Failed to create newswatch runtime")
    })
}

#[derive(Debug, Clone)]
pub struct NewsClientCore {
    feeds: Vec<FeedConfig>,
    http: HttpClient,
}

impl NewsClientCore {
    pub fn from_tuples(
        feed_tuples: Vec<(String, String, String)>,
        user_agent: String,
        rate_limit_secs: f64,
    ) -> Result<Self, NewswatchError> {
        let feeds = parse_feed_tuples(feed_tuples)?;
        if feeds.is_empty() {
            return Err(NewswatchError::new("at least one feed is required"));
        }

        Ok(Self {
            feeds,
            http: HttpClient::new(
                user_agent,
                rate_limit_secs,
                DEFAULT_MAX_RETRIES,
                DEFAULT_RETRY_DELAY_SECS,
            )?,
        })
    }

    pub fn fetch_blocking(
        &self,
        keywords: &[String],
        max_results: usize,
    ) -> Result<Vec<NewsItem>, NewswatchError> {
        get_runtime().block_on(self.fetch_async_internal(keywords, max_results))
    }

    pub async fn fetch_async_internal(
        &self,
        keywords: &[String],
        max_results: usize,
    ) -> Result<Vec<NewsItem>, NewswatchError> {
        let http = self.http.clone();
        let mut indexed_items = stream::iter(self.feeds.iter().cloned().enumerate())
            .map(|(index, feed)| {
                let http = http.clone();
                async move {
                    let parsed = fetch_feed(&http, &feed).await?;
                    Ok::<(usize, Vec<NewsItem>), NewswatchError>((index, parsed))
                }
            })
            .buffer_unordered(self.feeds.len().clamp(1, MAX_FEED_CONCURRENCY))
            .collect::<Vec<_>>()
            .await
            .into_iter()
            .collect::<Result<Vec<_>, NewswatchError>>()?;

        indexed_items.sort_by_key(|(index, _)| *index);

        let mut all_items: Vec<NewsItem> = Vec::new();
        for (_index, mut parsed) in indexed_items {
            all_items.append(&mut parsed);
        }

        let mut filtered = apply_keyword_filter(all_items, keywords)?;
        filtered.sort_by(|left, right| right.published_at.cmp(&left.published_at));

        // Preserve source dates and distinct URLs; Python normalizes and deduplicates.
        if max_results > 0 && filtered.len() > max_results {
            filtered.truncate(max_results);
        }

        Ok(filtered)
    }
}

async fn fetch_feed(http: &HttpClient, feed: &FeedConfig) -> Result<Vec<NewsItem>, NewswatchError> {
    let resolved_url = resolve_feed_url(feed)?;
    let response_text = http.fetch_text(&resolved_url).await?;
    match feed.feed_type {
        FeedType::Rss => rss::parse_feed(&response_text, &feed.name, &feed.url),
        FeedType::JsonApi { .. } => json_api::parse_feed(&response_text, &feed.name, &feed.url),
    }
}

fn parse_feed_tuples(
    feed_tuples: Vec<(String, String, String)>,
) -> Result<Vec<FeedConfig>, NewswatchError> {
    let mut feeds: Vec<FeedConfig> = Vec::new();

    for (url, feed_type, name) in feed_tuples {
        let normalized_url = url.trim().to_string();
        let normalized_name = if name.trim().is_empty() {
            normalized_url.clone()
        } else {
            name.trim().to_string()
        };
        if normalized_url.is_empty() {
            continue;
        }

        let parsed_feed_type = match feed_type.trim().to_ascii_lowercase().as_str() {
            "rss" | "atom" => FeedType::Rss,
            "json" | "json_api" | "newsapi" => FeedType::JsonApi {
                api_key_env: Some("NEWSAPI_API_KEY".to_string()),
            },
            "polygon" => FeedType::JsonApi {
                api_key_env: Some("POLYGON_API_KEY".to_string()),
            },
            "json_noauth" => FeedType::JsonApi { api_key_env: None },
            other => {
                return Err(NewswatchError::new(format!(
                    "unsupported feed type '{}' for {}",
                    other, normalized_url
                )))
            }
        };

        feeds.push(FeedConfig {
            url: normalized_url,
            feed_type: parsed_feed_type,
            name: normalized_name,
        });
    }

    Ok(feeds)
}

fn resolve_feed_url(feed: &FeedConfig) -> Result<String, NewswatchError> {
    match &feed.feed_type {
        FeedType::Rss => Ok(feed.url.clone()),
        FeedType::JsonApi { api_key_env } => {
            let Some(api_key_env) = api_key_env else {
                return Ok(feed.url.clone());
            };
            if !feed.url.contains("{api_key}") {
                return Ok(feed.url.clone());
            }
            let api_key = env::var(api_key_env).map_err(|_| {
                NewswatchError::new(format!(
                    "{} is required for feed {}",
                    api_key_env, feed.name
                ))
            })?;
            Ok(feed.url.replace("{api_key}", api_key.trim()))
        }
    }
}
