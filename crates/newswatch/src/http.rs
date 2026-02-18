use std::time::Duration;

use tokio::time::sleep;

use crate::error::NewswatchError;

#[derive(Debug, Clone)]
pub struct HttpClient {
    client: reqwest::Client,
    user_agent: String,
    rate_limit_secs: f64,
    max_retries: u32,
    retry_delay_secs: f64,
}

impl HttpClient {
    pub fn new(
        user_agent: String,
        rate_limit_secs: f64,
        max_retries: u32,
        retry_delay_secs: f64,
    ) -> Result<Self, NewswatchError> {
        let client = reqwest::Client::builder().build()?;
        Ok(Self {
            client,
            user_agent,
            rate_limit_secs,
            max_retries,
            retry_delay_secs,
        })
    }

    pub async fn fetch_text(&self, url: &str) -> Result<String, NewswatchError> {
        let mut attempt: u32 = 0;
        loop {
            if self.rate_limit_secs > 0.0 {
                sleep(Duration::from_secs_f64(self.rate_limit_secs)).await;
            }

            match self
                .client
                .get(url)
                .header(reqwest::header::USER_AGENT, self.user_agent.clone())
                .send()
                .await
            {
                Ok(response) => {
                    if response.status().is_success() {
                        return response.text().await.map_err(NewswatchError::from);
                    }
                    let status = response.status();
                    let body = response.text().await.unwrap_or_default();
                    let message = format!("news fetch failed (status {}): {}", status, body.trim());
                    if attempt >= self.max_retries {
                        return Err(NewswatchError::new(message));
                    }
                }
                Err(err) => {
                    if attempt >= self.max_retries {
                        return Err(NewswatchError::new(err.to_string()));
                    }
                }
            }

            attempt += 1;
            if self.retry_delay_secs > 0.0 {
                sleep(Duration::from_secs_f64(self.retry_delay_secs)).await;
            }
        }
    }
}
